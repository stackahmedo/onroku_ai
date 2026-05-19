"""
pyannote.py - Pyannote Speaker Diarization engine wrapper.
"""

import logging
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional
from .base import _assign_speaker

logger = logging.getLogger(__name__)


def _load_audio_for_pyannote(wav_path: str) -> Dict:
    """
    Load audio in-memory for pyannote.
    Uses stdlib wave + numpy to decode PCM WAV, bypassing torchcodec/torchaudio FFmpeg DLL errors on Windows.
    """
    import wave
    import numpy as np
    import torch

    with wave.open(wav_path, "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if sample_width == 1:
        audio = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
        audio = (audio - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width for diarization: {sample_width} bytes")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    waveform = torch.from_numpy(audio).unsqueeze(0)

    return {
        "waveform": waveform.to(dtype=torch.float32).contiguous(),
        "sample_rate": sample_rate,
    }


def _get_diarization_annotation(diarization):
    """Return a pyannote Annotation from both pyannote 3.x and 4.x outputs."""
    if hasattr(diarization, "itertracks"):
        return diarization
    if hasattr(diarization, "exclusive_speaker_diarization"):
        return diarization.exclusive_speaker_diarization
    if hasattr(diarization, "speaker_diarization"):
        return diarization.speaker_diarization
    raise TypeError(f"Unsupported diarization output type: {type(diarization)!r}")


class PyannoteDiarizationEngine:
    def __init__(self, hw: Dict):
        self.hw = hw
        self.device = hw["device"]
        self._pipeline = None

    def load(self, diarization_mode: str = "accurate") -> bool:
        if self._pipeline is not None:
            try:
                import torch
                device = torch.device(self.device if self.device == "cuda" else "cpu")
                if device.type != "cuda":
                    self._pipeline.embedding_batch_size = 4 if diarization_mode == "fast" else 1
                    logger.info(f"Dynamically updated Pyannote embedding_batch_size = {self._pipeline.embedding_batch_size}")
            except Exception as e:
                logger.warning(f"Could not update Pyannote embedding_batch_size: {e}")
            return True
            
        try:
            # This will raise ImportError if pyannote.audio is not installed
            from pyannote.audio import Pipeline
            import torch

            model_cache = Path(__file__).parent.parent.parent.parent / "app" / "models" / "pyannote"
            model_cache.mkdir(parents=True, exist_ok=True)
            
            root_dir = Path(__file__).parent.parent.parent.parent
            token_candidates = [
                root_dir / "app" / "models" / "hf_token.txt",
                root_dir / "models" / "hf_token.txt",
                root_dir / "hf_token.txt",
            ]
            
            hf_token = None
            for candidate in token_candidates:
                if candidate.exists():
                    try:
                        hf_token = candidate.read_text().strip()
                        if hf_token:
                            logger.info(f"Loaded Hugging Face token from: {candidate.name}")
                            break
                    except Exception as e:
                        logger.warning(f"Error reading token from {candidate}: {e}")

            logger.info("Loading Pyannote speaker diarization pipeline...")
            kwargs = {"token": hf_token} if hf_token else {}
            kwargs["cache_dir"] = str(model_cache)
            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", **kwargs
            )
            
            device = torch.device(self.device if self.device == "cuda" else "cpu")
            if device.type == "cpu":
                torch.set_num_threads(max(2, min(4, self.hw.get("cpu_cores", 4))))
            
            self._pipeline.to(device)

            try:
                if device.type == "cuda":
                    self._pipeline.embedding_batch_size = 16
                else:
                    self._pipeline.embedding_batch_size = 4 if diarization_mode == "fast" else 1
                logger.info(f"Configured Pyannote embedding_batch_size = {self._pipeline.embedding_batch_size}")
            except Exception as e:
                logger.warning(f"Could not set Pyannote embedding_batch_size: {e}")

            logger.info("Pyannote pipeline loaded successfully")
            return True
        except Exception as e:
            logger.warning(f"Pyannote unavailable: {e}. Speaker diarization disabled.")
            self._pipeline = None
            raise e

    def diarize(
        self,
        wav_path: str,
        segments: List[Dict],
        num_speakers: Optional[int] = None,
        diarization_mode: str = "accurate",
        speaker_range: str = "normal",
    ) -> List[Dict]:
        if self._pipeline is None:
            raise RuntimeError("Pyannote pipeline is not loaded. Call load() first.")

        kwargs = {}
        if num_speakers is not None and num_speakers > 0:
            kwargs["num_speakers"] = num_speakers
        else:
            if speaker_range == "large":
                kwargs["min_speakers"] = 2
                kwargs["max_speakers"] = 15
            else:
                kwargs["min_speakers"] = 2
                kwargs["max_speakers"] = 7
        
        if diarization_mode == "fast":
            kwargs["segmentation_step"] = 0.25
            logger.info("Applying fast speaker detection optimization: segmentation_step = 0.25")

        diarization_input = _load_audio_for_pyannote(wav_path)
        diarization = self._pipeline(diarization_input, **kwargs)
        diarization_tracks = _get_diarization_annotation(diarization)
        
        speaker_segments = [
            {"start": turn.start, "end": turn.end, "speaker": spk}
            for turn, _, spk in diarization_tracks.itertracks(yield_label=True)
        ]
        logger.info(
            "Diarization produced %s speaker turn(s), %s unique speaker(s).",
            len(speaker_segments),
            len({sp["speaker"] for sp in speaker_segments}),
        )

        first_text = segments[0]["text"] if segments else ""
        is_english = bool(re.search(r'[a-zA-Z]', first_text))
        join_char = " " if is_english else ""

        final_segments = []
        for seg in segments:
            words = seg.get("words", [])
            if not words:
                seg["speaker"] = _assign_speaker(seg, speaker_segments)
                seg.pop("words", None)
                final_segments.append(seg)
                continue

            word_speaker_pairs = []
            for w in words:
                spk = _assign_speaker(w, speaker_segments)
                word_speaker_pairs.append((w, spk))

            blocks = []
            current_block = []
            current_speaker = None

            for w, spk in word_speaker_pairs:
                if current_speaker is None:
                    current_speaker = spk
                    current_block.append(w)
                elif spk == current_speaker:
                    current_block.append(w)
                else:
                    blocks.append((current_speaker, current_block))
                    current_speaker = spk
                    current_block = [w]
            if current_block:
                blocks.append((current_speaker, current_block))

            for spk, block_words in blocks:
                sub_text = join_char.join([w["text"] for w in block_words]).strip()
                if not sub_text:
                    continue
                final_segments.append({
                    "start": block_words[0]["start"],
                    "end":   block_words[-1]["end"],
                    "speaker": spk,
                    "text":  sub_text,
                })
        return final_segments
