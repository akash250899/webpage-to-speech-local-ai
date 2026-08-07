"""
Web Scraping Service
"""

import asyncio
import re
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup


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
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: requests.get(url, headers=headers, timeout=10)
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch content from URL: {e}") from e

    soup = BeautifulSoup(response.text, "html.parser")

    # Decompose structural non-content tags
    unwanted_tags = [
        "nav", "header", "footer", "aside", "script",
        "style", "noscript", "iframe", "form", "svg"
    ]
    for tag in soup(unwanted_tags):
        tag.decompose()

    # Decompose ARIA UI roles
    for tag in soup.find_all(attrs={"role": ["navigation", "banner", "contentinfo", "search", "companion", "dialog", "alertdialog"]}):
        tag.decompose()

    # Decompose noise classes (dialogs, chatbots, related blogs, modals, sidebars)
    noise_class_keywords = [
        "confirm-dialog", "confirm-dialog__text", "dialog", "modal", "popup",
        "cookie", "disclaimer", "chatbot", "chat-window", "chat-dialog",
        "sidebar", "ad", "ads", "advertisement", "nav-menu", "byline",
        "continue-reading", "related-content", "related-articles", "related-blogs",
        "recommended-articles", "more-blogs", "card-grid", "teaser-grid"
    ]
    for tag in soup.find_all(class_=lambda c: c and any(w in " ".join(c).lower() for w in noise_class_keywords)):
        tag.decompose()

    # Decompose p & metadata tags (author, date-time, confirm-dialog__text, etc.)
    for tag in soup.find_all(["p", "div", "span"], class_=lambda c: c and any(k in " ".join(c).lower() for k in ["author", "authors", "date-time", "confirm-dialog", "confirm-dialog__text"])):
        tag.decompose()

    # Locate primary article container
    article_container = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", attrs={"role": "main"})
        or soup.find("div", id="content")
        or soup.find("div", class_=lambda c: c and "article" in c.lower())
        or soup.body
        or soup
    )

    h1_tag = article_container.find("h1") or soup.find("h1")

    heading_tags = ["h1", "h2", "h3", "h4", "h5", "h6"]
    target_tags = heading_tags + ["p"]

    extracted_chunks = []
    found_start = False if h1_tag else True

    for elem in article_container.find_all(target_tags):
        if elem == h1_tag:
            found_start = True

        if found_start:
            text = elem.get_text(strip=True)
            if not text:
                continue

            # Skip headings containing links (e.g. h4 with <a> for related blog cards)
            if elem.name in heading_tags:
                if elem.find("a") or elem.find_parent(class_=lambda c: c and any(k in " ".join(c).lower() for k in ["card", "teaser", "related", "link"])):
                    continue

            if elem.name == "p":
                if len(text) < 15:
                    continue
                elem_classes = " ".join(elem.get("class", [])).lower()
                if any(k in elem_classes for k in ["author", "authors", "date-time", "confirm-dialog", "confirm-dialog__text", "disclaimer", "chatbot"]):
                    continue

            # Skip trailing noise phrases
            text_lower = text.lower()
            if any(phrase in text_lower for phrase in ["continue reading", "end chat", "legal disclaimer", "closing this window clears", "notice: you are interacting"]):
                continue

            extracted_chunks.append(text)

    if not extracted_chunks:
        for elem in article_container.find_all(target_tags):
            text = elem.get_text(strip=True)
            if text and len(text) > 15:
                extracted_chunks.append(text)

    return "\n\n".join(extracted_chunks)
