"""
sherpa.py - Sherpa-ONNX Speaker Diarization engine wrapper.
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from .base import _assign_speaker

logger = logging.getLogger(__name__)


class SherpaDiarizationEngine:
    def __init__(self, hw: Dict):
        self.hw = hw

    def diarize(
        self,
        wav_path: str,
        segments: List[Dict],
        num_speakers: Optional[int] = None,
    ) -> List[Dict]:
        """Perform speaker diarization using Sherpa-ONNX offline engine."""
        try:
            # These will raise ImportError if dependencies are not installed
            import sherpa_onnx
            import soundfile as sf
        except ImportError as e:
            logger.error(f"sherpa_onnx or soundfile library not installed: {e}. Please run pip install sherpa-onnx.")
            raise e

        model_dir = Path(__file__).parent.parent.parent.parent / "app" / "models" / "sherpa-onnx"
        segmentation_model = str(model_dir / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx")
        embedding_model = str(model_dir / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")

        if not os.path.exists(segmentation_model) or not os.path.exists(embedding_model):
            err_msg = f"Sherpa-ONNX model files are missing at {segmentation_model} or {embedding_model}."
            logger.error(err_msg)
            raise FileNotFoundError(err_msg)

        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=segmentation_model
                ),
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=embedding_model
            ),
            clustering=sherpa_onnx.FastClusteringConfig(
                num_clusters=num_speakers if (num_speakers is not None and num_speakers > 0) else -1,
                threshold=0.5
            ),
            min_duration_on=0.3,
            min_duration_off=0.5,
        )

        if not config.validate():
            err_msg = "Sherpa-ONNX config validation failed."
            logger.error(err_msg)
            raise ValueError(err_msg)

        logger.info("Initializing Sherpa-ONNX offline speaker diarizer...")
        sd = sherpa_onnx.OfflineSpeakerDiarization(config)

        logger.info("Reading audio file for diarization...")
        audio, sample_rate = sf.read(wav_path, dtype="float32", always_2d=True)
        audio = audio[:, 0]

        logger.info("Running Sherpa-ONNX diarization process...")
        result = sd.process(audio).sort_by_start_time()

        speaker_segments = []
        for r in result:
            speaker_segments.append({
                "start": r.start,
                "end": r.end,
                "speaker": f"Speaker {r.speaker + 1}"
            })

        if not speaker_segments:
            logger.warning("Sherpa-ONNX diarization failed or returned no speaker tracks.")
            return []

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
                    "start":   block_words[0]["start"],
                    "end":     block_words[-1]["end"],
                    "speaker": spk,
                    "text":    sub_text,
                })
        return final_segments
