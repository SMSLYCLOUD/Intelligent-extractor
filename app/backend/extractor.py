import re
import datetime
from typing import List, Optional
from urllib.parse import urlparse
from app.backend.models import Lead, PersonInfo, CompanyInfo, SourceInfo, ValidationInfo, KeywordMatch
from app.backend.intelligence import LocalIntelligence, RemoteIntelligence

class Extractor:
    def __init__(self, ai_provider: str = "openai", api_key: Optional[str] = None):
        self.local_intel = LocalIntelligence()
        # Initialize remote intel. If api_key is missing for some providers, it might be None effectively.
        self.remote_intel = RemoteIntelligence(ai_provider, api_key)

        # Regex for emails
        # 1. Standard: user@domain.com
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

        # 2. Obfuscated: user [at] domain [dot] com, user (at) domain . com, user at domain dot com
        # We capture (user) ... (domain) ... (tld)
        # This is complex, let's break it down or use multiple patterns.

        # Pattern for "at" symbol variations
        at_pattern = r'\s*(?:@|\[at\]|\(at\)|at)\s*'
        # Pattern for "dot" symbol variations
        dot_pattern = r'\s*(?:\.|\[dot\]|\(dot\)|dot)\s*'

        # Combined pattern: (user) (at) (domain) (dot) (tld)
        self.obfuscated_pattern = re.compile(
            r'([a-zA-Z0-9._%+-]+)' + at_pattern + r'([a-zA-Z0-9.-]+)' + dot_pattern + r'([a-zA-Z]{2,})',
            re.IGNORECASE
        )

    async def extract_leads_from_text(self, text: str, url: str, page_title: str, keywords: List[str]) -> List[Lead]:
        leads = []
        seen_emails = set()

        # 1. Find matches
        matches = []

        # Standard emails
        for match in self.email_pattern.finditer(text):
            email = match.group()
            if email not in seen_emails:
                matches.append((email, match.start(), match.end(), "explicit"))
                seen_emails.add(email)

        # Obfuscated emails
        for match in self.obfuscated_pattern.finditer(text):
            # Reconstruct email
            user = match.group(1)
            domain = match.group(2)
            tld = match.group(3)
            email = f"{user}@{domain}.{tld}"

            # Avoid duplicates if regex caught the same thing (though standard usually catches first)
            if email not in seen_emails:
                # Check if it's a valid looking email (no spaces in parts)
                if ' ' not in email:
                    matches.append((email, match.start(), match.end(), "obfuscated"))
                    seen_emails.add(email)

        # 2. Process each match
        for email, start, end, method in matches:
            # Context window (±200 chars)
            ctx_start = max(0, start - 200)
            ctx_end = min(len(text), end + 200)
            context = text[ctx_start:ctx_end].replace("\n", " ").strip()

            # Initial Lead Object
            lead = Lead(
                email=email,
                validation_status="unknown",
                confidence_score=50, # Baseline
                relevance_score=0,
                lead_quality="low",
                source=SourceInfo(
                    url=url,
                    page_title=page_title,
                    discovery_method=method,
                    context_snippet=context,
                    extracted_at=datetime.datetime.now().isoformat()
                ),
                validation=ValidationInfo(), # Filled later by validator
                person=PersonInfo(),
                company=CompanyInfo(domain=email.split('@')[-1])
            )

            # Local Intelligence (Spacy)
            entities = self.local_intel.extract_entities(context)
            if entities["PERSON"]:
                # Improvement: Find person closest to the email in context
                # For now, just take the last one found before the email or first after?
                # Taking the last one is a reasonable heuristic for "Contact X at ..."
                lead.person.full_name = entities["PERSON"][-1]
                names = lead.person.full_name.split()
                if len(names) > 0: lead.person.first_name = names[0]
                if len(names) > 1: lead.person.last_name = " ".join(names[1:])

            if entities["ORG"]:
                lead.company.name = entities["ORG"][0]

            # Relevance Scoring (Local)
            local_analysis = self.local_intel.analyze_relevance_local(context, keywords)
            base_relevance = local_analysis["score"]
            for m in local_analysis["matches"]:
                lead.keyword_matches.append(KeywordMatch(**m))

            # Relevance Scoring (Remote)
            # Only call if we have a provider instance
            if self.remote_intel.provider_instance:
                semantic_data = await self.remote_intel.analyze_relevance_semantic(
                    context, keywords, lead.person.full_name
                )
                if semantic_data:
                    # Blend scores: Remote is authoritative on semantics
                    remote_score = semantic_data.get("relevance_score", 0)
                    base_relevance = (base_relevance + remote_score) / 2 # Simple average

                    if semantic_data.get("job_title"):
                        lead.person.job_title = semantic_data["job_title"]
                    if semantic_data.get("company_name"):
                        lead.company.name = semantic_data["company_name"]

                    for sm in semantic_data.get("semantic_matches", []):
                        lead.keyword_matches.append(KeywordMatch(keyword=sm, match_type="semantic", context=context))

            lead.relevance_score = int(base_relevance)

            # Determine Quality
            if lead.relevance_score >= 80:
                lead.lead_quality = "high"
            elif lead.relevance_score >= 60:
                lead.lead_quality = "medium"
            elif lead.relevance_score >= 40:
                lead.lead_quality = "low"
            else:
                lead.lead_quality = "reject"

            # Filter basic junk
            if self.is_junk_email(email):
                lead.lead_quality = "reject"
                lead.relevance_score = 0

            leads.append(lead)

        return leads

    def is_junk_email(self, email: str) -> bool:
        user_part = email.split('@')[0].lower()
        junk_users = {'noreply', 'no-reply', 'donotreply', 'test', 'example', 'sample', 'support', 'info', 'contact', 'admin', 'webmaster'}
        if user_part in junk_users:
            return True
        return False
