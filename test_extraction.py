import asyncio
import os
from app.backend.extractor import Extractor
from app.backend.validator import Validator
from app.backend.models import Lead

async def test_extraction_logic():
    print("Testing Extractor...")
    extractor = Extractor() # Local only if no API key in env

    sample_text = """
    1. Standard: john.doe@example.com
    2. Obfuscated 1: jane.smith [at] example [dot] com
    3. Obfuscated 2: admin (at) test . org
    4. Obfuscated 3: support at company dot net
    5. Junk: noreply@example.com
    """

    url = "https://example.com/team"
    keywords = ["CTO", "Technology", "Marketing", "VP"]

    leads = await extractor.extract_leads_from_text(sample_text, url, "Team Page", keywords)

    print(f"Found {len(leads)} leads.")
    expected_emails = [
        "john.doe@example.com",
        "jane.smith@example.com",
        "admin@test.org",
        "support@company.net",
        "noreply@example.com" # Should be rejected but found
    ]

    found_emails = [l.email for l in leads]
    print("Found emails:", found_emails)

    # Check if all expected are found (some might be rejected quality)
    for expected in expected_emails:
        assert expected in found_emails, f"Missing {expected}"

    # Check junk
    junk_lead = next(l for l in leads if l.email == "noreply@example.com")
    assert junk_lead.lead_quality == "reject", "Junk email not rejected"

    print("\nExtraction Test Passed!")

if __name__ == "__main__":
    asyncio.run(test_extraction_logic())
