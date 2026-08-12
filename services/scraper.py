"""
Web Scraping Service using Trafilatura for heuristic article extraction
"""

import asyncio
import logging
import re
from urllib.parse import urlparse

import trafilatura

logger = logging.getLogger(__name__)


def get_filename_from_url(url: str, voice: str = "female") -> str:
    """
    Extracts the URL slug, strips file extensions, sanitizes OS filename characters,
    and appends the voice choice (e.g. multi-die-multiphysics-co-design-female.wav).
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    segments = [s for s in path.split("/") if s]

    if not segments:
        slug = "article"
    else:
        last = segments[-1]
        slug = re.sub(r"\.(html|htm|php|asp|aspx)$", "", last, flags=re.IGNORECASE)
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "", slug)
        if not slug:
            slug = "article"

    voice_suffix = voice.lower() if voice else "female"
    return f"{slug}-{voice_suffix}.wav"


async def scrape_article(url: str) -> str:
    """
    Downloads and extracts clean article text using Trafilatura heuristic extraction.
    """
    logger.info("Fetching URL via Trafilatura | url=%s", url)

    loop = asyncio.get_running_loop()

    try:
        downloaded = await loop.run_in_executor(None, lambda: trafilatura.fetch_url(url))
    except Exception as e:
        logger.error("Trafilatura failed to fetch URL | url=%s | error=%s", url, e)
        raise RuntimeError(f"Failed to download article content: {e}") from e

    if not downloaded:
        logger.error("Trafilatura returned empty download response | url=%s", url)
        raise RuntimeError("Unable to download content from the specified URL")

    try:
        extracted_text = await loop.run_in_executor(
            None, lambda: trafilatura.extract(downloaded, include_comments=False, include_tables=True)
        )
    except Exception as e:
        logger.error("Trafilatura extraction exception | url=%s | error=%s", url, e)
        raise RuntimeError(f"Failed to extract text from page: {e}") from e

    if not extracted_text or not extracted_text.strip():
        logger.warning("Trafilatura extracted no text | url=%s", url)
        raise RuntimeError("No readable article text could be extracted from the specified URL")

    logger.info("Extracted article content | url=%s | chars=%s", url, len(extracted_text))
    return extracted_text
