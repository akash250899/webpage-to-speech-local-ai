"""
Local WebToSpeech AI Server Entry Point
"""

import asyncio
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.logging import setup_logging

# Configure logging first so module-level model loads are captured
setup_logging()

from api.routes import router, process_queue

logger = logging.getLogger(__name__)

app = FastAPI(
    title="WebToSpeech AI Pipeline",
    description="Native Python API for web scraping and text-to-speech audio synthesis",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logger.info("Spawning asyncio queue worker task...")
    asyncio.create_task(process_queue())


# Include API routes
app.include_router(router)


# Mount static frontend directory
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    logger.info("Starting WebToSpeech AI Pipeline on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
