import asyncio
from typing import List, AsyncGenerator
from app.backend.crawler import Crawler
from app.backend.models import Lead

class BulkProcessor:
    def __init__(self, keywords: List[str], ai_provider: str = "openai", api_key: str = None):
        self.keywords = keywords
        self.ai_provider = ai_provider
        self.api_key = api_key
        self.stopped = False

    def stop(self):
        self.stopped = True

    async def process_stream(self, emails: List[str]) -> AsyncGenerator[Lead, None]:
        # 1. Deduplicate emails
        unique_emails = list(set(emails))

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
            start_url = f"https://{domain}"

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

    async def process_emails(self, emails: List[str]) -> List[Lead]:
        leads = []
        async for lead in self.process_stream(emails):
            leads.append(lead)
        return leads
