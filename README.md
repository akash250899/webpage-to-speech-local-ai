---
title: Web-to-Speech AI
emoji: 🔊
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
---

# Web-to-Speech AI

Fully local API that scrapes web articles and synthesizes natural audio using Kokoro TTS.

## Features
- Web scraping via BeautifulSoup (article extraction with noise filtering)
- Kokoro TTS voice synthesis (`af_heart` female / `am_michael` male) at 24kHz WAV
- FastAPI backend with async job queue
- Static HTML/JS frontend at `http://localhost:8000`

## Local Setup
```bash
python -m venv ai_voice_env
source ai_voice_env/bin/activate
pip install -r requirements.txt
python main.py
```

## API
| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check |
| `/scrape?url=...` | GET | Scrape article text |
| `/process-speech?text=...&use_llm=false` | POST | Preprocess text for TTS |
| `/generate` | POST | Queue full pipeline (JSON body: `url`, `voice`) |
| `/status/{job_id}` | GET | Job status |
| `/audio/{job_id}` | GET | Download generated WAV |
