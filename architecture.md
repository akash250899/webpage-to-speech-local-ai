# WebToSpeech AI Architecture

## System Flow
1. **Client:** User submits a URL and Voice preference via the static HTML/JS UI.
2. **API Layer (`api/routes.py`):** FastAPI receives the request, generates a `job_id`, updates state (`core/state.py`), and triggers a Background Task.
3. **Scraper (`services/scraper.py`):** Fetches HTML and extracts raw article text.
4. **LLM Processor (`services/llm.py`):** Sends chunks to local LM Studio to expand abbreviations, numbers, and clean text for speech.
5. **TTS Engine (`services/tts.py`):** Kokoro synthesizes `.wav` files per sentence chunk, inserting 400ms silence between chunks via PyDub, and saves to the `output/` directory.

## Hardware Context
* **LLM:** Runs via LM Studio (MPS/Metal acceleration).
* **TTS:** Runs natively in Python to access unified memory (avoiding Docker/macOS virtualization bottlenecks).
