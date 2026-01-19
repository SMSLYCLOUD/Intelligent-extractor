import dns.resolver
import smtplib
import re
from email_validator import validate_email, EmailNotValidError
from app.backend.models import ValidationInfo

class Validator:
    @staticmethod
    async def validate(email: str) -> ValidationInfo:
        info = ValidationInfo()

        # 1. Syntax Check
        try:
            v = validate_email(email, check_deliverability=False)
            info.syntax_valid = True
            email = v.normalized
        except EmailNotValidError:
            info.syntax_valid = False
            return info # Fail early

        domain = email.split('@')[1]

        # 2. Domain & MX Check
        try:
            records = dns.resolver.resolve(domain, 'MX')
            if records:
                info.mx_records_found = True
                info.domain_valid = True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, dns.resolver.Timeout):
            info.mx_records_found = False
            info.domain_valid = False
            return info # Fail if no domain/MX

        # 3. Role-based check
        user_part = email.split('@')[0].lower()
        role_prefixes = ['admin', 'support', 'info', 'sales', 'contact', 'help', 'jobs', 'careers']
        if user_part in role_prefixes:
            info.is_role_based = True

        # 4. Disposable check (Simple list)
        disposable_domains = {'mailinator.com', 'yopmail.com', 'tempmail.com', 'guerrillamail.com'}
        if domain in disposable_domains:
            info.is_disposable = True
            info.is_corporate_email = False
        else:
            # Assume corporate if not disposable and has MX
            # (In a real system, we'd check against a list of free providers like gmail.com)
            free_providers = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com'}
            info.is_corporate_email = domain not in free_providers

        # 5. SMTP Verification (Best Effort / Risky in some envs)
        # We will skip active SMTP handshake in this sandbox to avoid timeouts/bans
        # but mark verified if MX is solid.
        info.smtp_verified = False

        return info
