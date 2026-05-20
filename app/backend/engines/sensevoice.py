"""
sensevoice.py - Sherpa-ONNX SenseVoice engine wrapper.
"""

import logging
import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional
from .base import _progress, check_pause_cancel, is_cancelled

logger = logging.getLogger(__name__)


class SenseVoiceEngine:
    def __init__(self, hw: Dict):
        self.hw = hw
        self._recognizer = None
        self._current_model_name = None

    def download_models(self, progress_cb: Optional[Callable] = None):
        """Download SenseVoice models from Hugging Face if not present."""
        model_dir = Path(__file__).parent.parent.parent.parent / "app" / "models" / "sensevoice"
        model_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "model.int8.onnx"
        tokens_path = model_dir / "tokens.txt"

        import requests

        # 1. Download model.int8.onnx if missing (~228MB)
        if not model_path.exists():
            url_model = "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/model.int8.onnx"
            logger.info(f"Downloading SenseVoice model from {url_model}...")
            _progress(progress_cb, 8, "SenseVoice INT8モデルダウンロード中... / Downloading SenseVoice INT8 model...")

            response = requests.get(url_model, stream=True)
            if response.status_code != 200:
                raise RuntimeError(f"Failed to download SenseVoice model: HTTP {response.status_code}")

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            with open(model_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_cb:
                            pct = 8 + int(67 * (downloaded / total_size))
                            _progress(progress_cb, pct, f"SenseVoiceモデルダウンロード中 ({downloaded//(1024*1024)}MB / {total_size//(1024*1024)}MB)...")
            logger.info("SenseVoice model downloaded successfully.")

        # 2. Download tokens.txt if missing
        if not tokens_path.exists():
            url_tokens = "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/tokens.txt"
            logger.info(f"Downloading SenseVoice tokens from {url_tokens}...")
            _progress(progress_cb, 75, "SenseVoiceトークンダウンロード中... / Downloading SenseVoice tokens...")

            response = requests.get(url_tokens, stream=True)
            if response.status_code != 200:
                raise RuntimeError(f"Failed to download SenseVoice tokens: HTTP {response.status_code}")

            with open(tokens_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            logger.info("SenseVoice tokens downloaded successfully.")

    def load(self, model_name: str, progress_cb: Optional[Callable] = None):
        """Initialize the Sherpa-ONNX SenseVoice OfflineRecognizer."""
        if self._recognizer is not None:
            return

        import sherpa_onnx

        self.download_models(progress_cb)

        model_dir = Path(__file__).parent.parent.parent.parent / "app" / "models" / "sensevoice"
        model_path = model_dir / "model.int8.onnx"
        tokens_path = model_dir / "tokens.txt"

        if not model_path.exists() or not tokens_path.exists():
            raise FileNotFoundError("SenseVoice model files are missing.")

        # Use CPU threads based on hardware profile
        num_threads = max(2, min(4, self.hw.get("cpu_cores", 4)))

        logger.info(f"Initializing Sherpa-ONNX SenseVoice recognizer with {num_threads} threads...")
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_path),
            tokens=str(tokens_path),
            use_itn=True,
            debug=False,
            num_threads=num_threads
        )
        self._current_model_name = "sensevoice"
        logger.info("SenseVoice INT8 engine loaded successfully.")

    def transcribe_chunk(
        self,
        chunk_path: str,
        language: str,
        offset: float,
        total_duration: float,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        chunk_idx: int = 0,
        n_chunks: int = 1,
        job_id: str = "",
        on_language_detected: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """Transcribe a single WAV chunk with SenseVoice."""
        if self._recognizer is None:
            raise RuntimeError("SenseVoice engine is not loaded. Call load() first.")

        import soundfile as sf

        # Read the wav file
        audio, sample_rate = sf.read(chunk_path, dtype="float32", always_2d=True)
        audio = audio[:, 0]  # First channel

        # SenseVoice accepts float32 numpy array normalized to [-1, 1]
        stream = self._recognizer.create_stream()
        stream.accept_waveform(sample_rate, audio)

        self._recognizer.decode_stream(stream)

        raw_text = stream.result.text
        # Post-process raw_text to strip SenseVoice specific tags
        cleaned_text = re.sub(r'<\|.*?\|>', '', raw_text).strip()

        # Detect language tag if present in raw_text (e.g. <|zh|>, <|en|>, <|ja|>, etc.)
        detected_lang = "ja"
        lang_match = re.search(r'<\|(zh|en|ja|ko|yue)\|>', raw_text)
        if lang_match:
            detected_lang = lang_match.group(1)
            if on_language_detected:
                try:
                    on_language_detected(detected_lang)
                except Exception as e:
                    logger.warning(f"Failed to call on_language_detected callback: {e}")

        # Return segment list
        segments_out = []
        if cleaned_text:
            segments_out.append({
                "start": round(offset, 3),
                "end": round(offset + len(audio)/sample_rate, 3),
                "speaker": "Speaker 1",
                "text": cleaned_text,
            })

        if total_duration > 0 and progress_cb:
            processed_secs = min(offset + len(audio)/sample_rate, total_duration)
            pct = 10 + int(70 * (processed_secs / total_duration))
            pct = min(pct, 79)
            _progress(
                progress_cb, pct,
                f"文字起こし中 {chunk_idx+1}/{n_chunks}... / Transcribing chunk {chunk_idx+1}/{n_chunks}..."
            )

        return segments_out
