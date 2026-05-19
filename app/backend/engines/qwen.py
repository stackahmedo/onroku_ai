"""
qwen.py - Qwen3-ASR engine wrapper.
"""

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional
from .base import _progress, _get_duration, check_pause_cancel, is_cancelled

logger = logging.getLogger(__name__)


class QwenEngine:
    def __init__(self, hw: Dict):
        self.hw = hw
        self.device = hw["device"]
        self._model = None
        self._current_model_name = None

    def load(self, model_name: str):
        """Lazy-load the Qwen3-ASR model on CPU or CUDA GPU."""
        if self._model is not None and self._current_model_name == model_name:
            return
            
        import torch
        
        # This will raise ImportError if qwen_asr is not installed
        from qwen_asr import Qwen3ASRModel
            
        model_dir = Path(__file__).parent.parent.parent.parent / "app" / "models" / "qwen3-asr"
        if "0.6b" in model_name.lower():
            local_model_path = model_dir / "Qwen3-ASR-0.6B"
            repo_id = "Qwen/Qwen3-ASR-0.6B"
        else:
            local_model_path = model_dir / "Qwen3-ASR-1.7B"
            repo_id = "Qwen/Qwen3-ASR-1.7B"
            
        model_path_to_load = str(local_model_path) if local_model_path.exists() and any(local_model_path.iterdir()) else repo_id
        
        # Optimize dtype and device mapping
        if self.device == "cuda":
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            device_map = self.device
        else:
            dtype = torch.float32
            device_map = "cpu"
            torch.set_num_threads(max(2, min(4, self.hw.get("cpu_cores", 4))))
            
        logger.info(f"Loading Qwen3-ASR model: {model_name} from {model_path_to_load} on {device_map} with dtype {dtype}...")
        
        try:
            self._model = Qwen3ASRModel.from_pretrained(
                model_path_to_load,
                dtype=dtype,
                device_map=device_map
            )
            self._current_model_name = model_name
            logger.info("Qwen3-ASR model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Qwen3-ASR model: {e}", exc_info=True)
            raise e

    def transcribe_chunk(
        self,
        chunk_path: str,
        offset: float,
        total_duration: float,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        chunk_idx: int = 0,
        n_chunks: int = 1,
        job_id: str = "",
        on_language_detected: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """Transcribe a single WAV chunk with Qwen3-ASR."""
        if self._model is None:
            raise RuntimeError("Qwen3-ASR model is not loaded. Call load() first.")

        try:
            logger.info(f"Running Qwen3-ASR transcription on chunk {chunk_idx+1}/{n_chunks} (offset={offset:.1f}s)...")
            results = self._model.transcribe(chunk_path)
            
            # Handle return format robustly
            if isinstance(results, list):
                result = results[0]
            else:
                result = results
                
            text = ""
            if hasattr(result, "text"):
                text = result.text
            elif isinstance(result, dict) and "text" in result:
                text = result["text"]
            else:
                text = str(result)
                
            text = text.strip()
            if not text:
                return []
                
            if on_language_detected:
                try:
                    lang = "ja"
                    if hasattr(result, "language") and result.language:
                        lang = "ja" if "ja" in result.language.lower() or "japanese" in result.language.lower() else "en"
                    on_language_detected(lang)
                except Exception as e:
                    logger.warning(f"Failed to call on_language_detected in Qwen3-ASR runner: {e}")
                    
            chunk_duration = _get_duration(chunk_path)
            if chunk_duration <= 0:
                chunk_duration = 30.0
                
            segments_out = [{
                "start": round(offset, 3),
                "end":   round(offset + chunk_duration, 3),
                "speaker": "Speaker 1",
                "text": text,
                "words": [],
            }]
            
            if total_duration > 0 and progress_cb:
                processed_secs = min(offset + chunk_duration, total_duration)
                pct = 10 + int(70 * (processed_secs / total_duration))
                pct = min(pct, 79)
                _progress(
                    progress_cb, pct,
                    f"文字起こし中 {chunk_idx+1}/{n_chunks}... / Transcribing chunk {chunk_idx+1}/{n_chunks}..."
                )
                
            return segments_out
        except Exception as e:
            logger.error(f"Qwen3-ASR chunk transcription error: {e}", exc_info=True)
            raise e
