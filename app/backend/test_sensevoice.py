import sys
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Ensure app/backend is in sys.path
backend_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(backend_dir))

from transcription_service import TranscriptionService
from hardware_detector import detect_hardware

def main():
    hw = detect_hardware()
    print("Detected hardware:", hw)
    
    # Initialize service
    service = TranscriptionService(hw)
    
    # Test audio file
    # Let's find recording1.wav
    proj_dir = backend_dir.parent.parent
    audio_path = proj_dir / "venv" / "lib" / "python3.13" / "site-packages" / "gradio" / "media_assets" / "audio" / "recording1.wav"
    if not audio_path.exists():
        # fallback to any wav file found
        import glob
        wavs = glob.glob(str(proj_dir / "**" / "*.wav"), recursive=True)
        if wavs:
            audio_path = Path(wavs[0])
        else:
            print("No wav files found to test.")
            sys.exit(1)
            
    print("Testing transcription with audio file:", audio_path)
    
    def progress_callback(pct, msg):
        print(f"[Progress {pct}%]: {msg}")
        
    def on_lang_detected(lang):
        print(f"Language detected: {lang}")
        
    try:
        segments = service.transcribe_file(
            file_path=str(audio_path),
            model_name="sensevoice",
            language="auto",
            diarization_mode="disabled",
            performance_mode="auto",
            progress_cb=progress_callback,
            on_language_detected=on_lang_detected,
            job_id="test_job_1"
        )
        print("\nTranscription completed successfully! Results:")
        for seg in segments:
            print(f"[{seg['start']:.2f}s - {seg['end']:.2f}s] {seg['speaker']}: {seg['text']}")
    except Exception as e:
        print("Transcription failed with error:", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
