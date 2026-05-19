"""
whisper_cpp.py - Whisper.cpp engine wrapper.
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional
from .base import _progress, check_pause_cancel, is_cancelled

logger = logging.getLogger(__name__)


class WhisperCppEngine:
    def __init__(self, hw: Dict, whisper_cpp_path: Path, threads: int):
        self.hw = hw
        self.whisper_cpp_path = whisper_cpp_path
        self.threads = threads

    def download_ggml_model(self, model_name: str, progress_cb: Optional[Callable] = None) -> str:
        """Download GGML model from Hugging Face if not present."""
        ggml_dir = Path(__file__).parent.parent.parent.parent / "app" / "models" / "ggml"
        ggml_dir.mkdir(parents=True, exist_ok=True)
        
        model_filename = f"ggml-{model_name}.bin"
        model_path = ggml_dir / model_filename
        
        if model_path.exists():
            logger.info(f"GGML model already exists: {model_path}")
            return str(model_path)
            
        url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{model_filename}"
        logger.info(f"Downloading GGML model from {url} to {model_path}...")
        
        import requests
        
        _progress(progress_cb, 8, f"AIモデル({model_name})ダウンロード中... / Downloading AI model ({model_name})...")
        
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download GGML model: HTTP {response.status_code}")
            
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        
        with open(model_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and progress_cb:
                        pct = 8 + int(15 * (downloaded / total_size)) # 8% - 23%
                        _progress(progress_cb, pct, f"AIモデル({model_name})ダウンロード中 ({downloaded//(1024*1024)}MB / {total_size//(1024*1024)}MB)...")
                        
        logger.info(f"GGML model successfully downloaded: {model_path}")
        return str(model_path)

    def transcribe_chunk(
        self,
        chunk_path: str,
        model_path: str,
        language: str,
        offset: float,
        total_duration: float,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        chunk_idx: int = 0,
        n_chunks: int = 1,
        job_id: str = "",
        on_language_detected: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """Transcribe a single WAV chunk with whisper.cpp executable."""
        active_lang = "auto" if language == "auto" else language
        segments_out = []
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                json_prefix = Path(tmpdir) / "output"
                
                cmd = [
                    str(self.whisper_cpp_path),
                    "-m", model_path,
                    "-f", chunk_path,
                    "-oj",
                    "-of", str(json_prefix),
                    "-t", str(self.threads),
                    "-sow",  # Split on word for precise word-timestamps
                ]
                if active_lang and active_lang != "auto":
                    cmd.extend(["-l", active_lang])
                else:
                    cmd.extend(["-l", "auto"])
                
                logger.info(f"Running whisper.cpp command: {' '.join(cmd)}")
                
                kwargs = {}
                if os.name == "nt":
                    kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
                
                result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
                
                if result.returncode != 0:
                    logger.error(f"whisper.cpp process failed with code {result.returncode}:\n{result.stderr}")
                    return []
                
                json_file = Path(tmpdir) / "output.json"
                if not json_file.exists():
                    logger.error(f"whisper.cpp JSON output file not found at {json_file}")
                    return []
                
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                transcription = data.get("transcription", [])
                
                if on_language_detected:
                    detected_lang = data.get("result", {}).get("language", "ja")
                    try:
                        on_language_detected(detected_lang)
                    except Exception as e:
                        logger.warning(f"Failed to call on_language_detected: {e}")
                
                for seg in transcription:
                    check_pause_cancel(job_id)
                    
                    seg_start = round(float(seg["offsets"]["from"]) / 1000.0 + offset, 3)
                    seg_end = round(float(seg["offsets"]["to"]) / 1000.0 + offset, 3)
                    seg_text = seg["text"].strip()
                    
                    words_list = []
                    for w in seg.get("tokens", []):
                        w_text = w.get("text", "").strip()
                        if not w_text or w_text.startswith("[") or w_text.startswith("("):
                            continue
                        w_start = round(float(w["offsets"]["from"]) / 1000.0 + offset, 3)
                        w_end = round(float(w["offsets"]["to"]) / 1000.0 + offset, 3)
                        words_list.append({
                            "start": w_start,
                            "end": w_end,
                            "text": w_text,
                        })
                    
                    segments_out.append({
                        "start": seg_start,
                        "end": seg_end,
                        "speaker": "Speaker 1",
                        "text": seg_text,
                        "words": words_list,
                    })
                    
                    if total_duration > 0 and progress_cb:
                        processed_secs = min(offset + (float(seg["offsets"]["to"]) / 1000.0), total_duration)
                        pct = 10 + int(70 * (processed_secs / total_duration))
                        pct = min(pct, 79)
                        _progress(
                            progress_cb, pct,
                            f"文字起こし中 {chunk_idx+1}/{n_chunks}... / Transcribing chunk {chunk_idx+1}/{n_chunks}..."
                        )
                        
        except Exception as e:
            logger.error(f"whisper.cpp chunk transcription error: {e}")
            raise e
            
        return segments_out
