import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Set, List, Dict, Tuple, AsyncGenerator, Optional
from app.backend.extractor import Extractor
from app.backend.validator import Validator
from app.backend.models import Lead, PersonInfo, CompanyInfo, SourceInfo, ValidationInfo
import datetime
import re
from abc import ABC, abstractmethod
from playwright.async_api import async_playwright

class BaseCrawler(ABC):
    def __init__(self, start_url: str, keywords: List[str], max_depth: int = 2, max_pages: int = 20, ai_provider: str = "openai", api_key: str = None):
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.keywords = keywords
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.visited: Set[str] = set()
        self.leads: List[Lead] = []
        self.extractor = Extractor(ai_provider, api_key)
        self.validator = Validator()
        self.pages_crawled = 0
        self.stopped = False

    def stop(self):
        self.stopped = True

    @abstractmethod
    async def crawl_stream(self) -> AsyncGenerator[Lead, None]:
        pass

    async def crawl(self) -> List[Lead]:
        leads = []
        async for lead in self.crawl_stream():
            leads.append(lead)
        return leads

    def _priority_score(self, item):
        url, depth = item
        score = 10 - depth
        priority_terms = ['about', 'team', 'contact', 'leadership', 'people', 'staff', 'management']
        for term in priority_terms:
            if term in url.lower():
                score += 5
        return score

    async def _process_leads(self, text_content: str, url: str, page_title: str) -> List[Lead]:
        # Extract Leads
        new_leads = await self.extractor.extract_leads_from_text(
            text_content, url, page_title, self.keywords
        )

        valid_leads = []
        # Validate Leads
        for lead in new_leads:
            if self.stopped: break

            if lead.lead_quality != "reject":
                lead.validation = await self.validator.validate(lead.email)

                # Downgrade if validation fails
                if not lead.validation.mx_records_found:
                    lead.lead_quality = "reject"
                    lead.validation_status = "invalid"
                else:
                    lead.validation_status = "verified"

                # Stream if not rejected and new
                if lead.lead_quality != "reject":
                    # Deduplicate by email
                    if not any(l.email == lead.email for l in self.leads):
                        self.leads.append(lead)
                        valid_leads.append(lead)
        return valid_leads

class FastCrawler(BaseCrawler):
    async def crawl_stream(self) -> AsyncGenerator[Lead, None]:
        queue = [(self.start_url, 0)]

        async with aiohttp.ClientSession() as session:
            while queue and self.pages_crawled < self.max_pages and not self.stopped:
                queue.sort(key=self._priority_score, reverse=True)
                url, depth = queue.pop(0)

                if url in self.visited:
                    continue
                self.visited.add(url)

                try:
                    async with session.get(url, timeout=10) as response:
                        if response.status != 200: continue
                        content_type = response.headers.get('Content-Type', '')
                        if 'text/html' not in content_type: continue

                        html = await response.text()
                        self.pages_crawled += 1
                        print(f"FastCrawling: {url} (Depth: {depth})")

                        soup = BeautifulSoup(html, 'html.parser')
                        text_content = soup.get_text(separator=' ', strip=True)
                        page_title = soup.title.string if soup.title else ""

                        # Process Leads
                        for lead in await self._process_leads(text_content, url, page_title):
                            yield lead

                        # Discovery
                        if depth < self.max_depth:
                            links = self._extract_links(soup, url)
                            for link in links:
                                if link not in self.visited:
                                    queue.append((link, depth + 1))
                except Exception as e:
                    print(f"Error crawling {url}: {e}")

    def _extract_links(self, soup, base_url) -> List[str]:
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.netloc == self.domain:
                clean_url = full_url.split('#')[0]
                links.append(clean_url)
        return links

class DeepCrawler(BaseCrawler):
    async def crawl_stream(self) -> AsyncGenerator[Lead, None]:
        queue = [(self.start_url, 0)]

        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (compatible; LeadBot/1.0)")

            try:
                while queue and self.pages_crawled < self.max_pages and not self.stopped:
                    queue.sort(key=self._priority_score, reverse=True)
                    url, depth = queue.pop(0)

                    if url in self.visited: continue
                    self.visited.add(url)

                    page = await context.new_page()
                    try:
                        print(f"DeepCrawling: {url} (Depth: {depth})")
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                        # Wait a bit for JS to render content if needed
                        await page.wait_for_timeout(2000)

                        content = await page.content()
                        self.pages_crawled += 1

                        # Use BS4 for parsing text as it's robust
                        soup = BeautifulSoup(content, 'html.parser')
                        text_content = soup.get_text(separator=' ', strip=True)
                        page_title = await page.title()

                        # Process Leads
                        for lead in await self._process_leads(text_content, url, page_title):
                            yield lead

                        # Discovery
                        if depth < self.max_depth:
                            links = await self._extract_links(page, url)
                            for link in links:
                                if link not in self.visited:
                                    queue.append((link, depth + 1))

                    except Exception as e:
                        print(f"Error deep crawling {url}: {e}")
                    finally:
                        await page.close()
            finally:
                await browser.close()

    async def _extract_links(self, page, base_url) -> List[str]:
        links = []
        try:
            # Execute JS to get all links
            hrefs = await page.eval_on_selector_all("a[href]", "elements => elements.map(e => e.href)")
            for href in hrefs:
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)
                if parsed.netloc == self.domain:
                    clean_url = full_url.split('#')[0]
                    links.append(clean_url)
        except Exception as e:
            print(f"Error extracting links: {e}")
        return links

def get_crawler(type: str, *args, **kwargs) -> BaseCrawler:
    if type == "deep":
        return DeepCrawler(*args, **kwargs)
    return FastCrawler(*args, **kwargs)

# Alias for backward compatibility if needed, though we should update main.py
Crawler = FastCrawler
