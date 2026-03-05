import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import List, AsyncGenerator
from app.backend.crawler import Crawler
from app.backend.models import Lead
from app.backend.intelligence import RemoteIntelligence

class BulkProcessor:
    def __init__(self, keywords: List[str], ai_provider: str = "openai", api_key: str = None):
        self.keywords = keywords
        self.ai_provider = ai_provider
        self.api_key = api_key
        self.stopped = False
        self.domain_cache = {}  # Cache to store domain liveliness and industry info

    def stop(self):
        self.stopped = True

    async def _check_domain_alive(self, domain: str) -> tuple[bool, str, str]:
        if domain in self.domain_cache and 'alive' in self.domain_cache[domain]:
            return self.domain_cache[domain]['alive'], self.domain_cache[domain].get('start_url'), self.domain_cache[domain].get('content', '')

        urls_to_try = [f"https://{domain}", f"http://{domain}"]
        async with aiohttp.ClientSession() as session:
            for url in urls_to_try:
                try:
                    async with session.get(url, timeout=10) as response:
                        if response.status < 400:
                            content_type = response.headers.get('Content-Type', '')
                            html_content = ""
                            if 'text/html' in content_type:
                                html = await response.text()
                                soup = BeautifulSoup(html, 'html.parser')
                                html_content = soup.get_text(separator=' ', strip=True)[:5000] # take first 5000 chars for analysis

                            if domain not in self.domain_cache:
                                self.domain_cache[domain] = {}
                            self.domain_cache[domain]['alive'] = True
                            self.domain_cache[domain]['start_url'] = url
                            self.domain_cache[domain]['content'] = html_content
                            return True, url, html_content
                except Exception:
                    continue

        if domain not in self.domain_cache:
            self.domain_cache[domain] = {}
        self.domain_cache[domain]['alive'] = False
        self.domain_cache[domain]['start_url'] = None
        self.domain_cache[domain]['content'] = ""
        return False, None, ""

    async def _check_industry_match(self, domain: str, text_content: str) -> bool:
        if not text_content or not self.keywords:
            return True # If no content or no keywords, allow it

        if domain in self.domain_cache and 'industry_match' in self.domain_cache[domain]:
            return self.domain_cache[domain]['industry_match']

        # Simple fast check
        text_lower = text_content.lower()
        for kw in self.keywords:
            if kw.lower() in text_lower:
                self.domain_cache[domain]['industry_match'] = True
                return True

        # If fast check fails, try remote intelligence
        remote = RemoteIntelligence(self.ai_provider, self.api_key)
        try:
            res = await remote.analyze_relevance_semantic(text_content, self.keywords)
            if res and res.get('relevance_score', 0) > 30: # arbitrary threshold for industry match
                self.domain_cache[domain]['industry_match'] = True
                return True
        except Exception as e:
            print(f"Error checking industry for {domain}: {e}")

        self.domain_cache[domain]['industry_match'] = False
        return False

    async def process_stream(self, raw_input: List[str]) -> AsyncGenerator[Lead, None]:
        import re

        # 1. Extract and deduplicate emails using regex on raw text input
        # Convert list of strings into a single text block if needed
        text_content = " ".join(raw_input) if isinstance(raw_input, list) else str(raw_input)

        email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        unique_emails = list(set(email_pattern.findall(text_content)))

        # 2. Group by domain
        domain_map = {}
        for email in unique_emails:
            try:
                domain = email.split('@')[1]
                if domain not in domain_map:
                    domain_map[domain] = []
                domain_map[domain].append(email)
            except IndexError:
                continue

        # 3. Process each domain
        for domain, domain_emails in domain_map.items():
            if self.stopped: break

            print(f"Processing domain: {domain} for {len(domain_emails)} emails...")

            is_alive, start_url, homepage_content = await self._check_domain_alive(domain)
            if not is_alive:
                print(f"Domain {domain} is not reachable. Skipping...")
                continue

            is_industry_match = await self._check_industry_match(domain, homepage_content)
            if not is_industry_match:
                print(f"Domain {domain} does not match target industries. Skipping...")
                continue

            crawler = Crawler(
                start_url=start_url,
                keywords=self.keywords,
                max_depth=1,
                max_pages=5,
                ai_provider=self.ai_provider,
                api_key=self.api_key
            )

            # Collect discovered leads to verify input emails
            discovered_leads = []
            async for lead in crawler.crawl_stream():
                if self.stopped: break
                discovered_leads.append(lead)
                # Yield discovered leads too if desired?
                # For bulk enrichment, users primarily want their input list verified/enriched.
                # But seeing extra leads is a bonus. Let's yield them with a special flag if we modify the model,
                # or just as is.
                yield lead

            # 4. Cross-reference
            discovered_email_map = {l.email: l for l in discovered_leads}

            for email in domain_emails:
                if self.stopped: break

                if email in discovered_email_map:
                    # Already yielded above as "verified_bulk" equivalent (it was found on site)
                    # We might want to tag it?
                    pass
                else:
                    # Not found on site, infer quality
                    domain_relevance = 0
                    if discovered_leads:
                        domain_relevance = sum(l.relevance_score for l in discovered_leads) / len(discovered_leads)

                    from app.backend.validator import Validator
                    from app.backend.models import Lead, PersonInfo, CompanyInfo, SourceInfo, ValidationInfo
                    import datetime

                    val_info = await Validator.validate(email)

                    relevance = int(domain_relevance * 0.8)

                    lead = Lead(
                        email=email,
                        validation_status="verified" if val_info.mx_records_found else "invalid",
                        confidence_score=50,
                        relevance_score=relevance,
                        lead_quality="medium" if relevance > 50 else "low",
                        source=SourceInfo(
                            url=start_url,
                            page_title="Bulk Import",
                            discovery_method="bulk_inferred",
                            extracted_at=datetime.datetime.now().isoformat()
                        ),
                        validation=val_info,
                        person=PersonInfo(),
                        company=CompanyInfo(domain=domain, name=domain)
                    )

                    if not val_info.mx_records_found:
                         lead.lead_quality = "reject"

                    yield lead

    async def process_emails(self, raw_input: List[str]) -> List[Lead]:
        leads = []
        async for lead in self.process_stream(raw_input):
            leads.append(lead)
        return leads
