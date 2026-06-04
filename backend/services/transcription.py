"""Audio transcription using a modern speech-to-text model (gpt-4o-transcribe).

Large files (> ~24 MB) are split into time-based chunks with ffmpeg and the
transcripts are concatenated, replacing the old hard 25 MB rejection.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import litellm

from core.config import get_settings
from services.llm import LLMError

logger = logging.getLogger(__name__)

MAX_BYTES = 24 * 1024 * 1024  # stay under the 25 MB API limit
CHUNK_SECONDS = 600  # 10-minute chunks when splitting

FINANCIAL_PROMPT = (
    "Financial news broadcast discussing stocks, earnings, IPO, merger, acquisition, "
    "Federal Reserve, interest rates, inflation, GDP, cryptocurrency, Bitcoin, forex, "
    "commodities, banking, quarterly reports, market analysis."
)


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


async def _transcribe_file(path: Path, model: str, api_key: str, language: str | None) -> str:
    with path.open("rb") as fh:
        resp = await litellm.atranscription(
            model=model,
            file=fh,
            api_key=api_key,
            language=language,
            prompt=FINANCIAL_PROMPT,
        )
    return getattr(resp, "text", "") or ""


def _split_audio(path: Path, out_dir: Path) -> list[Path]:
    pattern = str(out_dir / "chunk_%03d.mp3")
    subprocess.run(
        [
            "ffmpeg", "-i", str(path), "-f", "segment",
            "-segment_time", str(CHUNK_SECONDS),
            "-c:a", "libmp3lame", "-q:a", "5", pattern,
        ],
        check=True,
        capture_output=True,
    )
    return sorted(out_dir.glob("chunk_*.mp3"))


async def transcribe(
    audio_path: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    language: str | None = None,
) -> str:
    """Transcribe an audio file to text, chunking large files when needed."""
    settings = get_settings()
    model = model or settings.transcription_model
    provider = model.split("/", 1)[0] if "/" in model else "openai"
    key = api_key or settings.default_key_for(provider)
    if not key:
        raise LLMError(f"No API key for transcription provider '{provider}'.")

    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    size = path.stat().st_size
    if size <= MAX_BYTES:
        return await _transcribe_file(path, model, key, language)

    if not _has_ffmpeg():
        raise LLMError(
            f"Audio file is {size / 1e6:.1f} MB (> {MAX_BYTES / 1e6:.0f} MB) and ffmpeg "
            "is not installed for chunking."
        )

    logger.info("Splitting %.1f MB audio into chunks", size / 1e6)
    with tempfile.TemporaryDirectory() as tmp:
        chunks = await asyncio.to_thread(_split_audio, path, Path(tmp))
        parts = await asyncio.gather(
            *[_transcribe_file(c, model, key, language) for c in chunks]
        )
    return " ".join(p.strip() for p in parts if p.strip())
