from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import os
import json
import asyncio

from app.backend.crawler import Crawler
from app.backend.processor import BulkProcessor
from app.config import settings
from app.backend.models import Lead

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

class AnalyzeRequest(BaseModel):
    url: str
    keywords: List[str]
    max_depth: Optional[int] = None
    max_pages: Optional[int] = None
    ai_provider: Optional[str] = "openai"
    api_key: Optional[str] = None

# Keep REST endpoints for backward compat or non-interactive usage
@app.post("/api/analyze")
async def analyze_leads(request: AnalyzeRequest):
    try:
        api_key = request.api_key
        if not api_key:
            if request.ai_provider == "openai":
                api_key = settings.OPENAI_API_KEY
            elif request.ai_provider == "gemini":
                api_key = settings.GEMINI_API_KEY

        crawler = Crawler(
            start_url=request.url,
            keywords=request.keywords,
            max_depth=request.max_depth or settings.MAX_DEPTH,
            max_pages=request.max_pages or settings.MAX_PAGES,
            ai_provider=request.ai_provider,
            api_key=api_key
        )

        leads = await crawler.crawl()
        leads.sort(key=lambda x: x.relevance_score, reverse=True)
        return {"summary": _generate_summary(leads), "leads": leads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/enrich")
async def enrich_leads(file: UploadFile = File(...), keywords: str = Form(...), ai_provider: str = Form("openai"), api_key: str = Form(None)):
    try:
        content = await file.read()
        text = content.decode("utf-8")
        emails = [e.strip() for e in text.replace(',', '\n').split('\n') if '@' in e]
        keyword_list = [k.strip() for k in keywords.split(',')]

        used_key = api_key
        if not used_key:
            if ai_provider == "openai":
                used_key = settings.OPENAI_API_KEY
            elif ai_provider == "gemini":
                used_key = settings.GEMINI_API_KEY

        processor = BulkProcessor(keyword_list, ai_provider, used_key)
        leads = await processor.process_emails(emails)
        leads.sort(key=lambda x: x.relevance_score, reverse=True)
        return {"summary": _generate_summary(leads), "leads": leads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _generate_summary(leads):
    return {
        "total_leads_found": len(leads),
        "high_quality": sum(1 for l in leads if l.lead_quality == "high"),
        "medium_quality": sum(1 for l in leads if l.lead_quality == "medium"),
        "low_quality": sum(1 for l in leads if l.lead_quality == "low")
    }

@app.websocket("/ws/analyze")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    crawler_instance = None
    processor_instance = None

    try:
        while True:
            # Wait for a command
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "start_crawl":
                payload = data.get("payload")
                api_key = payload.get("api_key")
                provider = payload.get("ai_provider", "openai")

                if not api_key:
                    if provider == "openai": api_key = settings.OPENAI_API_KEY
                    elif provider == "gemini": api_key = settings.GEMINI_API_KEY

                crawler_instance = Crawler(
                    start_url=payload["url"],
                    keywords=payload["keywords"],
                    max_depth=payload.get("max_depth", 2),
                    max_pages=payload.get("max_pages", 20),
                    ai_provider=provider,
                    api_key=api_key
                )

                await websocket.send_json({"type": "status", "message": "Crawling started..."})

                async for lead in crawler_instance.crawl_stream():
                    await websocket.send_json({
                        "type": "lead",
                        "data": lead.dict()
                    })

                await websocket.send_json({"type": "complete", "message": "Crawling finished."})

            elif action == "start_bulk":
                payload = data.get("payload")
                api_key = payload.get("api_key")
                provider = payload.get("ai_provider", "openai")
                emails = payload.get("emails", [])

                if not api_key:
                    if provider == "openai": api_key = settings.OPENAI_API_KEY
                    elif provider == "gemini": api_key = settings.GEMINI_API_KEY

                processor_instance = BulkProcessor(payload["keywords"], provider, api_key)

                await websocket.send_json({"type": "status", "message": "Bulk processing started..."})

                async for lead in processor_instance.process_stream(emails):
                    await websocket.send_json({
                        "type": "lead",
                        "data": lead.dict()
                    })

                await websocket.send_json({"type": "complete", "message": "Bulk processing finished."})

            elif action == "stop":
                if crawler_instance: crawler_instance.stop()
                if processor_instance: processor_instance.stop()
                await websocket.send_json({"type": "status", "message": "Process stopped by user."})

    except WebSocketDisconnect:
        if crawler_instance: crawler_instance.stop()
        if processor_instance: processor_instance.stop()
        print("Client disconnected")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("app/frontend/static/index.html", "r") as f:
        return f.read()
