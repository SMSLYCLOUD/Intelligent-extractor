from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import os
import json
import asyncio
import io
import csv
import datetime

from app.backend.crawler import get_crawler
from app.backend.processor import BulkProcessor
from app.config import settings
from app.backend.models import Lead
from app.backend.database import engine, Base, get_db
from app.backend.db_models import DBExtractionJob, DBLead

# Initialize DB
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

class AnalyzeRequest(BaseModel):
    url: str
    keywords: List[str]
    max_depth: Optional[int] = None
    max_pages: Optional[int] = None
    ai_provider: Optional[str] = "openai"
    api_key: Optional[str] = None
    crawler_type: Optional[str] = "fast" # "fast" or "deep"

def _get_api_key(provider, user_key):
    if user_key: return user_key
    if provider == "openai": return settings.OPENAI_API_KEY
    if provider == "gemini": return settings.GEMINI_API_KEY
    if provider == "anthropic": return os.getenv("ANTHROPIC_API_KEY") # Ensure this is loaded if used
    return None

def _save_lead_to_db(db: Session, job_id: int, lead: Lead):
    db_lead = DBLead(
        job_id=job_id,
        email=lead.email,
        first_name=lead.person.first_name,
        last_name=lead.person.last_name,
        job_title=lead.person.job_title,
        company_name=lead.company.name,
        lead_quality=lead.lead_quality,
        relevance_score=lead.relevance_score,
        confidence_score=lead.confidence_score,
        source_url=lead.source.url,
        raw_data=lead.model_dump()
    )
    db.add(db_lead)
    db.commit()

@app.post("/api/analyze")
async def analyze_leads(request: AnalyzeRequest, db: Session = Depends(get_db)):
    try:
        api_key = _get_api_key(request.ai_provider, request.api_key)

        # Create Job
        job = DBExtractionJob(
            target_url=request.url,
            keywords=json.dumps(request.keywords),
            ai_provider=request.ai_provider,
            crawler_type=request.crawler_type,
            status="running"
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        crawler = get_crawler(
            type=request.crawler_type,
            start_url=request.url,
            keywords=request.keywords,
            max_depth=request.max_depth or settings.MAX_DEPTH,
            max_pages=request.max_pages or settings.MAX_PAGES,
            ai_provider=request.ai_provider,
            api_key=api_key
        )

        leads = []
        async for lead in crawler.crawl_stream():
            leads.append(lead)
            _save_lead_to_db(db, job.id, lead)

        leads.sort(key=lambda x: x.relevance_score, reverse=True)

        job.status = "completed"
        job.end_time = datetime.datetime.utcnow()
        job.lead_count = len(leads)
        db.commit()

        return {"summary": _generate_summary(leads), "leads": leads, "job_id": job.id}
    except Exception as e:
        # Update job status if possible
        # job.status = "failed" ... (hard to do without reference in except block cleanly without nesting)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/enrich")
async def enrich_leads(
    file: UploadFile = File(...),
    keywords: str = Form(...),
    ai_provider: str = Form("openai"),
    api_key: str = Form(None),
    db: Session = Depends(get_db)
):
    try:
        content = await file.read()
        text = content.decode("utf-8")
        keyword_list = [k.strip() for k in keywords.split(',')]

        used_key = _get_api_key(ai_provider, api_key)

        # Create Job
        job = DBExtractionJob(
            target_url="Bulk Upload",
            keywords=json.dumps(keyword_list),
            ai_provider=ai_provider,
            crawler_type="bulk",
            status="running"
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        processor = BulkProcessor(keyword_list, ai_provider, used_key)
        leads = []
        async for lead in processor.process_stream([text]):
            leads.append(lead)
            _save_lead_to_db(db, job.id, lead)

        leads.sort(key=lambda x: x.relevance_score, reverse=True)

        job.status = "completed"
        job.end_time = datetime.datetime.utcnow()
        job.lead_count = len(leads)
        db.commit()

        return {"summary": _generate_summary(leads), "leads": leads, "job_id": job.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
def get_history(db: Session = Depends(get_db)):
    jobs = db.query(DBExtractionJob).order_by(DBExtractionJob.start_time.desc()).limit(50).all()
    return jobs

@app.get("/api/history/{job_id}")
def get_job_details(job_id: int, db: Session = Depends(get_db)):
    job = db.query(DBExtractionJob).filter(DBExtractionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    leads = db.query(DBLead).filter(DBLead.job_id == job_id).all()
    # Convert raw_data back to list
    return {"job": job, "leads": [lead.raw_data for lead in leads]}

@app.get("/api/export/{job_id}")
def export_leads_csv(job_id: int, db: Session = Depends(get_db)):
    job = db.query(DBExtractionJob).filter(DBExtractionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    leads = db.query(DBLead).filter(DBLead.job_id == job_id).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Email', 'First Name', 'Last Name', 'Job Title', 'Company', 'Quality', 'Score', 'Source', 'Validation'])

    for lead in leads:
        writer.writerow([
            lead.email,
            lead.first_name,
            lead.last_name,
            lead.job_title,
            lead.company_name,
            lead.lead_quality,
            lead.relevance_score,
            lead.source_url,
            "Valid" if lead.raw_data.get('validation', {}).get('mx_records_found') else "Invalid"
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=leads_job_{job_id}.csv"}
    )

def _generate_summary(leads):
    return {
        "total_leads_found": len(leads),
        "high_quality": sum(1 for l in leads if l.lead_quality == "high"),
        "medium_quality": sum(1 for l in leads if l.lead_quality == "medium"),
        "low_quality": sum(1 for l in leads if l.lead_quality == "low")
    }

@app.websocket("/ws/analyze")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    crawler_instance = None
    processor_instance = None
    current_job = None

    try:
        while True:
            # Wait for a command
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "start_crawl":
                payload = data.get("payload")
                api_key = payload.get("api_key")
                provider = payload.get("ai_provider", "openai")
                crawler_type = payload.get("crawler_type", "fast")

                used_key = _get_api_key(provider, api_key)

                # Create Job
                current_job = DBExtractionJob(
                    target_url=payload["url"],
                    keywords=json.dumps(payload["keywords"]),
                    ai_provider=provider,
                    crawler_type=crawler_type,
                    status="running"
                )
                db.add(current_job)
                db.commit()
                db.refresh(current_job)

                crawler_instance = get_crawler(
                    type=crawler_type,
                    start_url=payload["url"],
                    keywords=payload["keywords"],
                    max_depth=payload.get("max_depth", 2),
                    max_pages=payload.get("max_pages", 20),
                    ai_provider=provider,
                    api_key=used_key
                )

                await websocket.send_json({"type": "status", "message": "Crawling started...", "job_id": current_job.id})

                lead_count = 0
                async for lead in crawler_instance.crawl_stream():
                    # Save to DB
                    _save_lead_to_db(db, current_job.id, lead)
                    lead_count += 1

                    await websocket.send_json({
                        "type": "lead",
                        "data": lead.model_dump()
                    })

                current_job.status = "completed"
                current_job.end_time = datetime.datetime.utcnow()
                current_job.lead_count = lead_count
                db.commit()

                await websocket.send_json({"type": "complete", "message": "Crawling finished.", "job_id": current_job.id})

            elif action == "start_bulk":
                # Similar logic for bulk...
                payload = data.get("payload")
                api_key = payload.get("api_key")
                provider = payload.get("ai_provider", "openai")
                emails = payload.get("emails", [])

                used_key = _get_api_key(provider, api_key)

                current_job = DBExtractionJob(
                    target_url="Bulk Upload",
                    keywords=json.dumps(payload["keywords"]),
                    ai_provider=provider,
                    crawler_type="bulk",
                    status="running"
                )
                db.add(current_job)
                db.commit()
                db.refresh(current_job)

                processor_instance = BulkProcessor(payload["keywords"], provider, used_key)

                await websocket.send_json({"type": "status", "message": "Bulk processing started...", "job_id": current_job.id})

                lead_count = 0
                async for lead in processor_instance.process_stream(emails):
                    _save_lead_to_db(db, current_job.id, lead)
                    lead_count += 1
                    await websocket.send_json({
                        "type": "lead",
                        "data": lead.model_dump()
                    })

                current_job.status = "completed"
                current_job.end_time = datetime.datetime.utcnow()
                current_job.lead_count = lead_count
                db.commit()

                await websocket.send_json({"type": "complete", "message": "Bulk processing finished.", "job_id": current_job.id})

            elif action == "stop":
                if crawler_instance: crawler_instance.stop()
                if processor_instance: processor_instance.stop()
                if current_job:
                    current_job.status = "stopped"
                    db.commit()
                await websocket.send_json({"type": "status", "message": "Process stopped by user."})

    except WebSocketDisconnect:
        if crawler_instance: crawler_instance.stop()
        if processor_instance: processor_instance.stop()
        print("Client disconnected")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("app/frontend/static/index.html", "r") as f:
        return f.read()
