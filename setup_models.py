"""
setup_models.py  –  V2
One-time model download script.
Run this before launching the app for the first time.

Usage:
    python setup_models.py
"""

import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR    = Path(__file__).parent
MODELS_DIR  = BASE_DIR / "app" / "models"
WHISPER_DIR = MODELS_DIR / "whisper"
PYANNOTE_DIR= MODELS_DIR / "pyannote"
TOKEN_FILE  = MODELS_DIR / "hf_token.txt"

for d in [WHISPER_DIR, PYANNOTE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def banner(msg):
    print("\n" + "=" * 60)
    print(f"  {msg}")
    print("=" * 60)


def check_python_deps():
    banner("Checking Python dependencies")
    missing = []
    for pkg in ["faster_whisper", "torch", "pyannote.audio", "psutil", "fastapi", "uvicorn", "pydub", "openpyxl", "sse_starlette"]:
        try:
            __import__(pkg.replace("-", "_").replace(".", "_") if pkg != "pyannote.audio" else "pyannote")
            print(f"  ✅ {pkg}")
        except ImportError:
            print(f"  ❌ {pkg} — MISSING")
            missing.append(pkg)

    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print("   Run:  pip install -r requirements.txt")
        return False
    return True


def check_ffmpeg():
    banner("Checking FFmpeg")
    import shutil
    if shutil.which("ffmpeg"):
        print("  ✅ ffmpeg found in PATH")
        return True
    else:
        print("  ❌ ffmpeg NOT found")
        print("  Please install FFmpeg and add it to PATH:")
        print("  https://ffmpeg.org/download.html")
        return False


def download_whisper(model_name: str):
    banner(f"Downloading Whisper model: {model_name}")
    try:
        from faster_whisper import WhisperModel
        print(f"  Downloading '{model_name}' to {WHISPER_DIR} ...")
        print("  (This may take several minutes on first run)")
        model = WhisperModel(model_name, device="cpu", compute_type="int8",
                             download_root=str(WHISPER_DIR))
        print(f"  ✅ Whisper model '{model_name}' ready")
        return True
    except Exception as e:
        print(f"  ❌ Whisper download failed: {e}")
        return False


def setup_pyannote():
    banner("Setting up Pyannote speaker diarization")

    # Check for existing token
    hf_token = None
    if TOKEN_FILE.exists():
        hf_token = TOKEN_FILE.read_text().strip()
        print(f"  Found saved HuggingFace token in {TOKEN_FILE}")
    else:
        print("""
  Pyannote speaker diarization requires a HuggingFace token (free).
  Steps:
    1. Go to https://huggingface.co and create a free account
    2. Accept the model terms at:
       https://huggingface.co/pyannote/speaker-diarization-3.1
    3. Create an access token at:
       https://huggingface.co/settings/tokens
    4. Paste the token below (or press Enter to skip — diarization disabled)
""")
        try:
            hf_token = input("  HuggingFace token: ").strip()
        except EOFError:
            hf_token = ""

    if not hf_token:
        print("  ⚠️  No token provided — speaker diarization will be disabled.")
        print("      Single-speaker transcription will still work fully.")
        return False

    # Save token
    TOKEN_FILE.write_text(hf_token)
    print(f"  Token saved to {TOKEN_FILE}")

    # Download model
    try:
        from pyannote.audio import Pipeline
        print("  Downloading pyannote/speaker-diarization-3.1 ...")
        print("  (This may take several minutes on first run)")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        print("  ✅ Pyannote pipeline ready")
        return True
    except Exception as e:
        print(f"  ❌ Pyannote setup failed: {e}")
        print("  You can still use the app without speaker diarization.")
        return False


def create_storage_dirs():
    banner("Creating storage directories")
    dirs = [
        BASE_DIR / "app" / "storage" / "uploads",
        BASE_DIR / "app" / "storage" / "chunks",
        BASE_DIR / "app" / "storage" / "transcripts",
        BASE_DIR / "app" / "storage" / "exports",
        BASE_DIR / "app" / "database",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ {d}")


def detect_and_report_hardware():
    banner("Hardware Detection")
    try:
        sys.path.insert(0, str(BASE_DIR / "app" / "backend"))
        from hardware_detector import detect_hardware
        hw = detect_hardware()
        print(f"  Tier:        {hw['tier'].upper()}")
        print(f"  Device:      {hw['device'].upper()}")
        print(f"  Model:       {hw['model_name']}")
        print(f"  RAM:         {hw['ram_gb']} GB")
        print(f"  CPU cores:   {hw['cpu_cores']}")
        print(f"  Chunk size:  {hw['chunk_seconds'] // 60} minutes")
        if hw['gpu_available']:
            print(f"  GPU:         {hw['gpu_name']} ({hw['gpu_vram_gb']} GB VRAM)")
        return hw
    except Exception as e:
        print(f"  ⚠️  Hardware detection error: {e}")
        return {"model_name": "small"}


def main():
    print("\n" + "🎙️  " * 3)
    print("  TRANSCRIPT AI V2  —  Setup Script")
    print("🎙️  " * 3)

    ok_deps   = check_python_deps()
    ok_ffmpeg = check_ffmpeg()

    if not ok_deps:
        print("\n❌ Install missing packages first, then re-run setup.")
        sys.exit(1)

    hw = detect_and_report_hardware()
    create_storage_dirs()
    download_whisper(hw.get("model_name", "small"))
    setup_pyannote()

    print("\n" + "=" * 60)
    print("  ✅ Setup complete!")
    print("  Run the app with:  start.bat")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
