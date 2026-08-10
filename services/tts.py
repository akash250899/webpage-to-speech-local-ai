"""
XTTSv2 Speech Synthesis Engine
"""

import asyncio
import os
import re
import shutil
import torch
from pydub import AudioSegment

# Coqui TOS agreement
os.environ["COQUI_TOS_AGREED"] = "1"

# PyTorch 2.6+ checkpoint compatibility patch
try:
    from TTS.tts.configs.xtts_config import XttsConfig
    torch.serialization.add_safe_globals([XttsConfig])
except Exception:
    pass

_orig_torch_load = torch.load
def _safe_torch_load(*args, **kwargs):
    if "weights_only" not in kwargs:
        kwargs["weights_only"] = False
    return _orig_torch_load(*args, **kwargs)
torch.load = _safe_torch_load

# Ensure output directory exists
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global XTTSv2 model initialization in Apple Silicon unified memory
print("[Global Model Loader] Loading Coqui XTTSv2 model globally into M5 unified memory...")
from TTS.api import TTS
global_tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)
print("[Global Model Loader] Coqui XTTSv2 model loaded successfully!")


def get_tts_model():
    return global_tts_model


REF_DIR = "references"
os.makedirs(REF_DIR, exist_ok=True)


def ensure_reference_audio(voice: str = "female") -> str:
    """
    Ensures female voice is cloned from references/reference_voice.wav (female_ref.wav)
    and male voice is cloned from references/male_sample_voice.mp3 (male_ref.wav).
    """
    os.makedirs(REF_DIR, exist_ok=True)

    if voice and voice.lower() == "male":
        target_wav = os.path.join(REF_DIR, "male_ref.wav")
        mp3_source = None
        for candidate in ["male_sample_voice.mp3", "male_sample_voive.mp3", "male_voice.mp3"]:
            c_path = os.path.join(REF_DIR, candidate)
            if os.path.exists(c_path):
                mp3_source = c_path
                break
            elif os.path.exists(candidate):
                mp3_source = candidate
                break

        if mp3_source:
            try:
                if not os.path.exists(target_wav) or os.path.getmtime(mp3_source) > os.path.getmtime(target_wav):
                    import librosa, soundfile as sf
                    print(f"[Audio Generator] Converting '{mp3_source}' -> '{target_wav}' for male voice cloning...")
                    data, sr = librosa.load(mp3_source, sr=None)
                    sf.write(target_wav, data, sr)
            except Exception as e:
                print(f"[Audio Generator] Librosa MP3 conversion error: {e}")

        if os.path.exists(target_wav):
            return target_wav
        elif os.path.exists(os.path.join(REF_DIR, "reference_voice.wav")):
            return os.path.join(REF_DIR, "reference_voice.wav")
    else:
        # Female Voice
        fem_target = os.path.join(REF_DIR, "female_ref.wav")
        ref_source = os.path.join(REF_DIR, "reference_voice.wav")

        if os.path.exists(fem_target):
            return fem_target
        elif os.path.exists(ref_source):
            shutil.copy(ref_source, fem_target)
            return fem_target

    for fallback in [os.path.join(REF_DIR, "female_ref.wav"), os.path.join(REF_DIR, "reference_voice.wav"), "female_ref.wav", "reference_voice.wav"]:
        if os.path.exists(fallback):
            return fallback

    raise FileNotFoundError(f"No reference audio file found in '{REF_DIR}' directory.")


async def generate_audio(
    paragraphs: list[str],
    voice: str = "female",
    reference_speaker_wav: str = None,
    output_filename: str = None
) -> str:
    if not paragraphs:
        return ""

    if reference_speaker_wav is None:
        reference_speaker_wav = ensure_reference_audio(voice)

    if not os.path.exists(reference_speaker_wav):
        raise FileNotFoundError(f"Reference speaker audio file '{reference_speaker_wav}' not found.")

    if not output_filename:
        output_filename = os.path.join(OUTPUT_DIR, f"audio_{os.urandom(4).hex()}.wav")

    # Ensure output directory path
    if not os.path.isabs(output_filename) and not output_filename.startswith(OUTPUT_DIR):
        output_filename = os.path.join(OUTPUT_DIR, os.path.basename(output_filename))

    sentence_chunks = []
    for p in paragraphs:
        raw_sentences = re.split(r"(?<=[.!?])\s+", p.strip())
        for s in raw_sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            if len(s_clean) > 220:
                clauses = re.split(r"(?<=[,;—–])\s+", s_clean)
                current_clause = ""
                for c in clauses:
                    if len(current_clause) + len(c) < 220:
                        current_clause = f"{current_clause} {c}".strip()
                    else:
                        if current_clause:
                            sentence_chunks.append(current_clause)
                        current_clause = c
                if current_clause:
                    sentence_chunks.append(current_clause)
            else:
                sentence_chunks.append(s_clean)

    tts = get_tts_model()
    loop = asyncio.get_event_loop()

    temp_files = []
    for idx, sentence in enumerate(sentence_chunks):
        temp_file = os.path.join(OUTPUT_DIR, f"temp_{idx}.wav")
        await loop.run_in_executor(
            None,
            lambda s=sentence, tf=temp_file: tts.tts_to_file(
                text=s,
                speaker_wav=reference_speaker_wav,
                language="en",
                speed=1.2,
                file_path=tf
            )
        )
        temp_files.append(temp_file)

    combined_audio = AudioSegment.empty()
    silence = AudioSegment.silent(duration=400)

    for idx, temp_file in enumerate(temp_files):
        if os.path.exists(temp_file):
            segment = AudioSegment.from_wav(temp_file)
            if idx > 0:
                combined_audio += silence
            combined_audio += segment

    combined_audio.export(output_filename, format="wav")

    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

    return output_filename
