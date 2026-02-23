from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.backend.database import Base

class DBExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    id = Column(Integer, primary_key=True, index=True)
    target_url = Column(String, nullable=True) # URL or "Bulk Upload"
    keywords = Column(String, nullable=True) # Comma separated
    ai_provider = Column(String, default="openai")
    crawler_type = Column(String, default="fast")
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    status = Column(String, default="running") # running, completed, failed
    lead_count = Column(Integer, default=0)

    leads = relationship("DBLead", back_populates="job")

class DBLead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("extraction_jobs.id"))

    email = Column(String, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    job_title = Column(String, nullable=True)
    company_name = Column(String, nullable=True)

    lead_quality = Column(String) # high, medium, low, reject
    relevance_score = Column(Integer)
    confidence_score = Column(Integer)

    source_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Store the full JSON blob to easily reconstruct the Pydantic model
    raw_data = Column(JSON)

    job = relationship("DBExtractionJob", back_populates="leads")
