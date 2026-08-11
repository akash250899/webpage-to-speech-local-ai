# Local Web-to-Speech AI

A production-grade, fully local API that scrapes web articles, cleans them using a local LLM, and synthesizes natural audio using XTTSv2.

## Prerequisites
* macOS
* Native Python 3.10+
* [LM Studio](https://lmstudio.ai/) running locally with an 8B instruct model on port 1234.
* `male_ref.wav` and `female_ref.wav` (3-5 second clear voice samples) in the root directory.

## Setup
1. `python -m venv ai_voice_env`
2. `source ai_voice_env/bin/activate`
3. `pip install -r requirements.txt`

## Run
`python main.py`

Navigate to `http://localhost:8000` to access the UI.
