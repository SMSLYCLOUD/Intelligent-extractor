from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class PersonInfo(BaseModel):
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None

class CompanyInfo(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None

class KeywordMatch(BaseModel):
    keyword: str
    match_type: str  # "direct", "semantic", "context"
    context: Optional[str] = None

class SourceInfo(BaseModel):
    url: str
    page_title: Optional[str] = None
    discovery_method: str  # "explicit", "inferred", "predicted"
    context_snippet: Optional[str] = None
    extracted_at: str

class ValidationInfo(BaseModel):
    syntax_valid: bool = False
    domain_valid: bool = False
    mx_records_found: bool = False
    smtp_verified: bool = False
    is_corporate_email: bool = False
    is_disposable: bool = False
    is_role_based: bool = False

class Lead(BaseModel):
    email: str
    validation_status: str  # "verified", "valid", "invalid", "unknown"
    confidence_score: int = 0
    relevance_score: int = 0
    lead_quality: str  # "high", "medium", "low", "reject"

    person: PersonInfo = Field(default_factory=PersonInfo)
    company: CompanyInfo = Field(default_factory=CompanyInfo)
    keyword_matches: List[KeywordMatch] = Field(default_factory=list)
    source: SourceInfo
    validation: ValidationInfo = Field(default_factory=ValidationInfo)
