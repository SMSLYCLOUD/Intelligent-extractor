import re
import datetime
from typing import List, Optional
from urllib.parse import urlparse
from app.backend.models import Lead, PersonInfo, CompanyInfo, SourceInfo, ValidationInfo, KeywordMatch
from app.backend.intelligence import LocalIntelligence, RemoteIntelligence

class Extractor:
    def __init__(self, openai_api_key: Optional[str] = None):
        self.local_intel = LocalIntelligence()
        self.remote_intel = RemoteIntelligence(openai_api_key) if openai_api_key else None

        # Regex for emails: Standard + simple obfuscation
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        self.obfuscated_at_pattern = re.compile(r'([a-zA-Z0-9._%+-]+)\s*[\(\[]\s*at\s*[\)\]]\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', re.IGNORECASE)

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
        for match in self.obfuscated_at_pattern.finditer(text):
            email = f"{match.group(1)}@{match.group(2)}"
            if email not in seen_emails:
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
                # "email" is somewhere in "context" (or represented by placeholders if obfuscated)
                # Since we don't have exact offsets mapped to context easily without re-running spacy on full text with offsets,
                # we will trust the order. Usually the person is introduced BEFORE the email.
                # So we pick the last person found in the list (assuming list order roughly matches text order for this simple extraction)
                # Actually, Spacy returns entities in order of appearance.
                # If email is at the end of context, the closest person is likely the last one found.
                # If email is in the middle...
                # Let's try picking the LAST person in the list, as "Contact John Doe at..." -> John Doe is before.
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

            # Relevance Scoring (Remote - Optional)
            if self.remote_intel:
                semantic_data = await self.remote_intel.analyze_relevance_semantic(
                    context, keywords, lead.person.full_name
                )
                if semantic_data:
                    # Blend scores: Remote is authoritative on semantics
                    remote_score = semantic_data.get("relevance_score", 0)
                    base_relevance = (base_relevance + remote_score) / 2 # Simple average for now

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
