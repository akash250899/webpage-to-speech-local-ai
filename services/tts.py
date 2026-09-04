"""
Kokoro Speech Synthesis Engine
"""

import asyncio
import logging
import os
import re

import numpy as np
import soundfile as sf
from num2words import num2words
from pydub import AudioSegment
from kokoro import KPipeline

logger = logging.getLogger(__name__)

# Ensure output directory exists
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global Kokoro TTS pipeline initialization (American English 'a')
logger.info("Loading Kokoro TTS pipeline globally (lang_code='a')...")
pipeline = KPipeline(lang_code='a')
logger.info("Kokoro TTS pipeline loaded successfully!")


def get_tts_pipeline():
    return pipeline


VOICE_MAPPING = {
    "female": "af_heart",
    "male": "am_michael",
}


def resolve_voice(voice: str = "female") -> str:
    if not voice:
        return "af_heart"
    v_lower = voice.lower()
    return VOICE_MAPPING.get(v_lower, voice)


def _synthesize_chunk_sync(text: str, voice_name: str, temp_file_path: str) -> bool:
    """
    Synchronous chunk synthesis worker using Kokoro pipeline.
    Saves audio numpy array to temp_file_path using soundfile.write at 24000Hz.
    """
    try:
        generator = pipeline(text, voice=voice_name, speed=1.2)
        audio_segments = []
        for gs, ps, audio in generator:
            if audio is not None:
                if hasattr(audio, "numpy"):
                    audio = audio.numpy()
                audio_segments.append(audio)

        if not audio_segments:
            logger.warning("Kokoro pipeline produced no audio segments for text: %s", text[:30])
            return False

        full_audio = np.concatenate(audio_segments) if len(audio_segments) > 1 else audio_segments[0]
        sf.write(temp_file_path, full_audio, 24000)
        return True
    except Exception as e:
        logger.exception("Failed synthesizing chunk with Kokoro | text=%s | error=%s", text[:30], e)
        return False


async def generate_audio(
    paragraphs: list[str],
    voice: str = "female",
    reference_speaker_wav: str = None,
    output_filename: str = None
) -> str:
    if not paragraphs:
        logger.warning("generate_audio called with no paragraphs")
        return ""

    kokoro_voice = resolve_voice(voice)

    if not output_filename:
        output_filename = os.path.join(OUTPUT_DIR, f"audio_{os.urandom(4).hex()}.wav")

    # Ensure output directory path
    if not os.path.isabs(output_filename) and not output_filename.startswith(OUTPUT_DIR):
        output_filename = os.path.join(OUTPUT_DIR, os.path.basename(output_filename))

    sentence_chunks = []
    for paragraph in paragraphs:
        text_chunks = re.split(r"(?<=[.!?])\s+", paragraph.strip())
        for s in text_chunks:
            s_clean = s.strip()
            if s_clean:
                sentence_chunks.append(s_clean)

    logger.info(
        "Audio generation started | requested_voice=%s | kokoro_voice=%s | sentence_chunks=%s | output=%s",
        voice, kokoro_voice, len(sentence_chunks), output_filename
    )

    loop = asyncio.get_running_loop()
    temp_files = []

    for idx, sentence in enumerate(sentence_chunks):
        # 1. Clean hidden unicode artifacts and strip leading/trailing spaces
        clean_chunk = re.sub(r'[^\x00-\x7F]+', '', sentence)
        clean_chunk = clean_chunk.strip()

        # 2. Convert basic standalone numbers to spoken words
        clean_chunk = re.sub(r'\b\d+\b', lambda m: num2words(int(m.group())), clean_chunk)

        # 3. Skip micro-chunks that cause acoustic hallucinations
        if len(clean_chunk) < 5:
            continue

        temp_file = os.path.join(OUTPUT_DIR, f"temp_{idx}.wav")
        logger.debug("Synthesizing chunk | idx=%s/%s | chars=%s", idx + 1, len(sentence_chunks), len(clean_chunk))

        success = await loop.run_in_executor(
            None,
            _synthesize_chunk_sync,
            clean_chunk,
            kokoro_voice,
            temp_file
        )

        if success:
            temp_files.append(temp_file)

    combined_audio = AudioSegment.empty()

    for idx, temp_file_path in enumerate(temp_files):
        if os.path.exists(temp_file_path):
            tts_chunk = AudioSegment.from_wav(temp_file_path)
            dynamic_silence = AudioSegment.silent(duration=400, frame_rate=tts_chunk.frame_rate)

            if idx > 0:
                combined_audio += dynamic_silence + tts_chunk
            else:
                combined_audio += tts_chunk
        else:
            logger.warning("Temp chunk missing during assembly | idx=%s | path=%s", idx, temp_file_path)

    combined_audio.export(output_filename, format="wav")
    logger.info(
        "Audio assembled | output=%s | duration_s=%s | chunks=%s",
        output_filename, round(combined_audio.duration_seconds, 2), len(temp_files)
    )

    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as e:
                logger.warning("Failed to remove temp file | path=%s | error=%s", temp_file, e)

    return output_filename
