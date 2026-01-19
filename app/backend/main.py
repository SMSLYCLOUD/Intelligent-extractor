from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os
import asyncio

from app.backend.crawler import Crawler
from app.backend.models import Lead

app = FastAPI()

# Mount frontend directory to serve static files if needed
# But for simplicity, we will serve index.html at root
# app.mount("/static", StaticFiles(directory="app/frontend"), name="static")

class AnalyzeRequest(BaseModel):
    url: str
    keywords: List[str]
    max_depth: int = 2
    max_pages: int = 20
    openai_key: Optional[str] = None

@app.post("/api/analyze")
async def analyze_leads(request: AnalyzeRequest):
    try:
        crawler = Crawler(
            start_url=request.url,
            keywords=request.keywords,
            max_depth=request.max_depth,
            max_pages=request.max_pages,
            openai_key=request.openai_key
        )

        leads = await crawler.crawl()

        # Sort leads by relevance score (descending)
        leads.sort(key=lambda x: x.relevance_score, reverse=True)

        # Executive Summary
        total = len(leads)
        high_quality = sum(1 for l in leads if l.lead_quality == "high")
        medium_quality = sum(1 for l in leads if l.lead_quality == "medium")
        low_quality = sum(1 for l in leads if l.lead_quality == "low")

        return {
            "summary": {
                "total_leads_found": total,
                "high_quality": high_quality,
                "medium_quality": medium_quality,
                "low_quality": low_quality
            },
            "leads": leads
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def read_root():
    # Serve the frontend HTML
    with open("app/frontend/index.html", "r") as f:
        return f.read()

if __name__ == "__main__":
    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=True)
