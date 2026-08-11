"""
API Route Handlers and Orchestration
"""

import json
import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from core.state import jobs, get_task_queue
from api.models import RequestPayload
from services.scraper import scrape_article, get_filename_from_url
from services.llm import process_text_for_speech
from services.tts import generate_audio

logger = logging.getLogger(__name__)

router = APIRouter()

GLOSSARY_PATH = os.path.join("core", "glossary.json")


async def process_queue():
    """
    Background worker loop that sequentially processes audio generation tasks from task_queue.
    Limits execution to one task at a time to prevent high RAM/memory usage crashes.
    """
    logger.info("Asyncio queue worker started and awaiting tasks...")
    task_queue = get_task_queue()
    while True:
        job_id, url, voice = await task_queue.get()
        try:
            logger.info("Worker processing job | job_id=%s | url=%s | voice=%s", job_id, url, voice)
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["started_at"] = datetime.now().isoformat()

            max_chunks = jobs[job_id].get("max_chunks")
            use_llm = jobs[job_id].get("use_llm", False)

            extracted_text = await scrape_article(url)
            logger.info("Pipeline stage=scrape | job_id=%s | chars=%s", job_id, len(extracted_text))

            paragraphs = await process_text_for_speech(extracted_text, max_chunks=max_chunks, use_llm=use_llm)
            logger.info("Pipeline stage=process | job_id=%s | paragraphs=%s", job_id, len(paragraphs))

            filename = get_filename_from_url(url, voice)
            output_filename = os.path.join("output", filename)
            file_path = await generate_audio(paragraphs, voice=voice, output_filename=output_filename)
            logger.info("Pipeline stage=tts | job_id=%s | file_path=%s", job_id, file_path)

            jobs[job_id]["status"] = "completed"
            jobs[job_id]["file_path"] = file_path
            jobs[job_id]["completed_at"] = datetime.now().isoformat()
            jobs[job_id]["paragraph_count"] = len(paragraphs)
            jobs[job_id]["character_count"] = len(extracted_text)
            jobs[job_id]["voice"] = voice
            logger.info("Pipeline completed | job_id=%s | file_path=%s", job_id, file_path)

        except Exception as err:
            logger.exception("Pipeline failed | job_id=%s | error=%s", job_id, err)
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(err)
            jobs[job_id]["failed_at"] = datetime.now().isoformat()
        finally:
            task_queue.task_done()



@router.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "Local TTS & Web Scraping Pipeline",
        "environment": "Native Python"
    }


@router.get("/glossary")
def get_glossary_endpoint():
    """Returns the current pronunciation glossary JSON dictionary."""
    if os.path.exists(GLOSSARY_PATH):
        try:
            with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.exception("Failed to read glossary at %s", GLOSSARY_PATH)
            raise HTTPException(status_code=500, detail=f"Failed to read glossary: {e}")
    logger.debug("Glossary file not found at %s, returning defaults", GLOSSARY_PATH)
    return {
        "EDA": "Electronic Design Automation",
        "CPU": "Central Processing Unit",
        "SaaS": "sass",
        "GUI": "gooey",
        "IEEE": "I triple E"
    }


@router.post("/glossary")
def update_glossary_endpoint(payload: dict[str, str]):
    """Accepts a JSON payload and overwrites core/glossary.json."""
    try:
        os.makedirs("core", exist_ok=True)
        with open(GLOSSARY_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info("Glossary updated | entries=%s | path=%s", len(payload), GLOSSARY_PATH)
        return {"status": "success", "message": "Glossary updated successfully", "glossary": payload}
    except Exception as e:
        logger.exception("Failed to save glossary to %s", GLOSSARY_PATH)
        raise HTTPException(status_code=400, detail=f"Failed to save glossary: {e}")


@router.get("/scrape")
async def scrape_endpoint(url: str = Query(..., description="URL of article to scrape")):
    logger.info("Scrape requested | url=%s", url)
    try:
        text = await scrape_article(url)
        logger.info("Scrape succeeded | url=%s | chars=%s", url, len(text))
        return {"url": url, "character_count": len(text), "content": text}
    except Exception as e:
        logger.exception("Scrape failed | url=%s", url)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/process-speech")
async def process_speech_endpoint(text: str, use_llm: bool = False):
    logger.info("Process-speech requested | use_llm=%s | chars=%s", use_llm, len(text))
    try:
        paragraphs = await process_text_for_speech(text, use_llm=use_llm)
        logger.info("Process-speech succeeded | paragraphs=%s", len(paragraphs))
        return {"original_paragraph_count": len(text.split("\n\n")), "processed_paragraphs": paragraphs}
    except Exception as e:
        logger.exception("Process-speech failed | use_llm=%s", use_llm)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate")
async def generate_endpoint(payload: RequestPayload):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "url": payload.url,
        "voice": payload.voice,
        "max_chunks": payload.max_chunks,
        "use_llm": payload.use_llm,
        "created_at": datetime.now().isoformat(),
        "file_path": None,
        "error": None
    }

    await get_task_queue().put((job_id, payload.url, payload.voice))

    logger.info(
        "Job queued | job_id=%s | url=%s | voice=%s | max_chunks=%s | use_llm=%s",
        job_id, payload.url, payload.voice, payload.max_chunks, payload.use_llm
    )

    return {"job_id": job_id, "status": "queued", "voice": payload.voice, "message": "Pipeline execution queued"}



@router.get("/status/{job_id}")
def get_status(job_id: str):
    if job_id not in jobs:
        logger.warning("Status requested for unknown job | job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job ID not found")
    return jobs[job_id]


@router.get("/audio/{job_id}")
def get_audio(job_id: str):
    if job_id not in jobs:
        logger.warning("Audio requested for unknown job | job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job ID not found")

    job = jobs[job_id]
    if job["status"] != "completed":
        logger.warning("Audio requested for non-completed job | job_id=%s | status=%s", job_id, job["status"])
        raise HTTPException(status_code=400, detail=f"Job status is '{job['status']}'. Audio is not ready.")

    file_path = job.get("file_path")
    if not file_path or not os.path.exists(file_path):
        logger.error("Audio file missing | job_id=%s | file_path=%s", job_id, file_path)
        raise HTTPException(status_code=404, detail="Audio file not found on server")

    logger.info("Serving audio | job_id=%s | file_path=%s", job_id, file_path)
    return FileResponse(
        path=file_path,
        media_type="audio/wav",
        filename=os.path.basename(file_path)
    )
