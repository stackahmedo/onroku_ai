"""
whisper.py - Faster-Whisper engine wrapper.
"""

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional
from .base import _progress, check_pause_cancel, is_cancelled

# We perform the import inside load/execution to isolate import errors if dependencies are missing.
logger = logging.getLogger(__name__)


class WhisperEngine:
    def __init__(self, hw: Dict):
        self.hw = hw
        self.device = hw["device"]
        self.compute_type = hw["compute_type"]
        self._model = None
        self._current_model_name = None

    def load(self, requested_model_name: str):
        if self._model is not None and self._current_model_name == requested_model_name:
            return
        
        logger.info(
            f"Loading faster-whisper model: {requested_model_name} "
            f"on {self.device} ({self.compute_type})"
        )
        
        # This will raise ImportError if faster-whisper is not installed
        from faster_whisper import WhisperModel
        
        model_dir = Path(__file__).parent.parent.parent.parent / "app" / "models" / "whisper"
        model_dir.mkdir(parents=True, exist_ok=True)

        kwargs = {
            "device": self.device,
            "compute_type": self.compute_type,
            "download_root": str(model_dir),
        }
        if self.device == "cpu":
            kwargs["cpu_threads"] = max(2, min(4, self.hw.get("cpu_cores", 4)))
            kwargs["num_workers"] = 1
        else:
            kwargs["num_workers"] = 1

        self._model = WhisperModel(
            requested_model_name,
            **kwargs
        )
        self._current_model_name = requested_model_name
        logger.info("Whisper model loaded successfully")

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
        beam_size: Optional[int] = None,
    ) -> List[Dict]:
        """Transcribe a single WAV chunk with faster-whisper."""
        if self._model is None:
            raise RuntimeError("Whisper model is not loaded. Call load() first.")

        if beam_size is None:
            is_large = self._current_model_name and "large" in self._current_model_name.lower()
            beam_size = 3 if is_large else 1

        active_lang = None if language == "auto" else language
        segments_out = []
        
        try:
            segments, info = self._model.transcribe(
                chunk_path,
                language=active_lang,
                beam_size=beam_size,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                word_timestamps=True,  # Mandatory for speaker label merging
                condition_on_previous_text=False,  # Prevent hallucination loops & speed boost
            )
            logger.info(
                f"  Detected language: {info.language} "
                f"(prob={info.language_probability:.2f})"
            )
            if on_language_detected:
                try:
                    on_language_detected(info.language)
                except Exception as e:
                    logger.warning(f"Failed to call on_language_detected callback: {e}")
            
            for seg in segments:
                check_pause_cancel(job_id)
                words_list = []
                if seg.words:
                    for w in seg.words:
                        words_list.append({
                            "start": round(w.start + offset, 3),
                            "end":   round(w.end + offset, 3),
                            "text":  w.word,
                        })
                segments_out.append({
                    "start": round(seg.start + offset, 3),
                    "end":   round(seg.end   + offset, 3),
                    "speaker": "Speaker 1",
                    "text": seg.text.strip(),
                    "words": words_list,
                })
                if total_duration > 0 and progress_cb:
                    processed_secs = min(offset + seg.end, total_duration)
                    pct = 10 + int(70 * (processed_secs / total_duration))
                    pct = min(pct, 79)
                    _progress(
                        progress_cb, pct,
                        f"文字起こし中 {chunk_idx+1}/{n_chunks}... / Transcribing chunk {chunk_idx+1}/{n_chunks}..."
                    )
        except Exception as e:
            logger.error(f"Chunk transcription error: {e}")
            raise e
            
        return segments_out
