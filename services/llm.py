"""
Local LLM Text Processing Service with Dynamic Pronunciation Glossary
"""

import asyncio
import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

LLM_ENDPOINT = "http://localhost:1234/v1/chat/completions"
LLM_MODELS_ENDPOINT = "http://localhost:1234/v1/models"
GLOSSARY_PATH = os.path.join("core", "glossary.json")


def load_glossary() -> dict:
    """Reads core/glossary.json dynamically."""
    if os.path.exists(GLOSSARY_PATH):
        try:
            with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
                glossary = json.load(f)
                logger.debug("Loaded glossary | entries=%s | path=%s", len(glossary), GLOSSARY_PATH)
                return glossary
        except Exception:
            logger.exception("Failed to load glossary from %s, using defaults", GLOSSARY_PATH)
    logger.debug("Glossary file missing, using defaults | path=%s", GLOSSARY_PATH)
    return {
        "EDA": "Electronic Design Automation",
        "CPU": "Central Processing Unit",
        "SaaS": "sass",
        "GUI": "gooey",
        "IEEE": "I triple E"
    }


def get_active_llm_model() -> str:
    try:
        r = requests.get(LLM_MODELS_ENDPOINT, timeout=3)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return data[0]["id"]
    except Exception:
        logger.warning("Could not reach LLM models endpoint %s", LLM_MODELS_ENDPOINT)
    return "local-model"


async def process_text_for_speech(text: str, max_chunks: int = None, use_llm: bool = False) -> list[str]:
    if not text or not text.strip():
        logger.warning("process_text_for_speech called with empty text")
        return []

    glossary = load_glossary()
    glossary_json_string = json.dumps(glossary, indent=2)

    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    paragraphs = [p for p in raw_paragraphs if len(p) >= 15] or raw_paragraphs

    if max_chunks is not None and len(paragraphs) > max_chunks:
        logger.debug("Limiting paragraphs | before=%s | max_chunks=%s", len(paragraphs), max_chunks)
        paragraphs = paragraphs[:max_chunks]

    # Phase 1: Deterministic Glossary Replacement & Surface Normalization
    preprocessed_paragraphs = []
    for chunk in paragraphs:
        cleaned = re.sub(r"\[\d+\]", "", chunk)
        cleaned = re.sub(r"\[citation needed\]", "", cleaned, flags=re.IGNORECASE)

        # Apply Glossary String Replacements
        for key, value in glossary.items():
            pattern = re.compile(r"\b" + re.escape(key) + r"\b")
            cleaned = pattern.sub(value, cleaned)

        # Default surface normalizations
        cleaned = re.sub(r"\bAI\b", "artificial intelligence", cleaned)
        cleaned = re.sub(r"\b2\u202fGHz\b", "two gigahertz", cleaned)
        cleaned = re.sub(r"\b2 GHz\b", "two gigahertz", cleaned)
        cleaned = re.sub(r"\be\.g\.\b", "for example", cleaned)
        preprocessed_paragraphs.append(cleaned.strip())

    if not use_llm:
        logger.info(
            "Text processed without LLM | paragraphs=%s | chars=%s",
            len(preprocessed_paragraphs), sum(len(p) for p in preprocessed_paragraphs)
        )
        return preprocessed_paragraphs

    # Phase 2: System Prompt Injection with Technical Glossary
    system_prompt = (
        "You are a text-to-speech scriptwriter. Rewrite the text for spoken word.\n"
        f"Adhere to this technical glossary:\n{glossary_json_string}\n\n"
        "CRITICAL DIRECTIVE: DO NOT PARAPHRASE, DO NOT REWRITE SENTENCES, AND DO NOT ALTER THE IDEAS.\n"
        "Output ONLY the expanded verbatim text with no introductory commentary or quotes."
    )

    model_name = get_active_llm_model()
    logger.info(
        "Processing text with LLM | model=%s | endpoint=%s | paragraphs=%s",
        model_name, LLM_ENDPOINT, len(preprocessed_paragraphs)
    )
    processed_paragraphs = []
    fallback_count = 0
    loop = asyncio.get_running_loop()

    for idx, chunk in enumerate(preprocessed_paragraphs):
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": chunk}
            ],
            "temperature": 0.0
        }

        try:
            res = await loop.run_in_executor(
                None, lambda: requests.post(LLM_ENDPOINT, json=payload, timeout=45)
            )
            res.raise_for_status()
            data = res.json()
            cleaned_paragraph = data["choices"][0]["message"]["content"].strip()
            if cleaned_paragraph:
                processed_paragraphs.append(cleaned_paragraph)
            else:
                logger.warning("LLM returned empty content for paragraph | idx=%s | falling back to raw chunk", idx)
                fallback_count += 1
                processed_paragraphs.append(chunk)
        except Exception as exc:
            logger.exception("LLM request failed | idx=%s | error=%s", idx, exc)
            fallback_count += 1
            processed_paragraphs.append(chunk)

    logger.info(
        "Text processed with LLM | paragraphs=%s | fallbacks=%s",
        len(processed_paragraphs), fallback_count
    )
    return processed_paragraphs
