import asyncio
import os
from app.backend.extractor import Extractor
from app.backend.validator import Validator

async def test_extraction_logic():
    print("Testing Extractor...")
    extractor = Extractor()

    sample_text = """
    Our team is led by John Doe, Chief Technology Officer. You can reach him at john.doe@example.com for technical inquiries.
    Also contact marketing at jane.smith [at] example.com. She is our VP of Marketing.
    """

    url = "https://example.com/team"
    keywords = ["CTO", "Technology", "Marketing", "VP"]

    leads = await extractor.extract_leads_from_text(sample_text, url, "Team Page", keywords)

    print(f"Found {len(leads)} leads.")
    for lead in leads:
        print(f"Lead: {lead.email}, Quality: {lead.lead_quality}, Relevance: {lead.relevance_score}")
        print(f"  Person: {lead.person.full_name}, Role: {lead.person.job_title}")
        print(f"  Matches: {[m.keyword for m in lead.keyword_matches]}")

    assert len(leads) == 2
    assert leads[0].email == "john.doe@example.com"
    assert leads[0].person.first_name == "John"
    # Note: Job title extraction in Local Intelligence is basic (NER doesn't always get titles perfectly without a specific model),
    # but keyword matching should work.

    print("\nTesting Validator (Mock)...")
    # We can't easily test real DNS in some sandboxes without network, but let's try the syntax check
    val_info = await Validator.validate("test@example.com")
    print(f"Syntax Valid: {val_info.syntax_valid}")
    # example.com actually has MX records usually, let's see if it passes
    print(f"MX Found: {val_info.mx_records_found}")

if __name__ == "__main__":
    asyncio.run(test_extraction_logic())
