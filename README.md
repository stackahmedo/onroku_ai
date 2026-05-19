# 🎙️ Onroku AI V5.5

**Onroku AI** is a local-first speech transcription desktop app built with Electron, React, Python, and FastAPI.

It supports offline Whisper transcription, speaker diarization with pyannote, multi-format export, and hardware-aware GPU acceleration for faster local processing.

---

## 🚀 Overview

This repository contains:

* `app/frontend/` — Electron + React UI and preload integration
* `app/backend/` — FastAPI backend service for transcription, job management, and export
* `app/models/` — local model cache for Whisper and pyannote weights
* `app/storage/` — settings, transcript data, and export caches
* `start.bat` / `start_prod.bat` — launch scripts for development and production
* `launcher.py` — Python launcher for the backend service

---

## ✨ Key Features

* Offline transcription with local Whisper-compatible models
* Speaker diarization and speaker renaming support
* Hardware-aware backend for CUDA / Vulkan / CPU execution
* Export to TXT, CSV, XLSX, and PDF
* Supports audio and video uploads
* Works offline after model cache is downloaded

---

## 🧰 Requirements

* Windows 10/11 (64-bit) or macOS/Linux with compatible GPU support
* Python 3.11+ or Python 3.10
* Node.js 18+ and npm
* Git for repository operations

---

## 🏁 Quick Start

### 1. Install dependencies

```powershell
npm install
python -m pip install -r requirements.txt
```

### 2. Start the backend

```powershell
cd app/backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Start the frontend

```powershell
npm run start
```

### 4. Launch production-ready app

```powershell
start_prod.bat
```

---

## 🧩 Recommended Setup

For the best local performance:

* Cache models before running offline
* Install GPU-accelerated `whisper-cli` for Vulkan support
* Keep `hf_token.txt` in the root folder for Hugging Face access

---

## 📦 Packaging

### Build frontend assets

```powershell
npm run build
```

### Create a portable distribution

1. Build frontend
2. Copy `build/`, `app/`, `start_prod.bat`, `launcher.py`, and `package.json`
3. Package into a `.zip`

### Create an executable

```powershell
npm run dist
```

---

## 🔒 Offline Usage

To run offline:

1. Add your Hugging Face token to `hf_token.txt` in the project root.
2. Cache the required Whisper and pyannote models in `app/models/`.
3. Start the app once while connected so all dependencies download.

---

## 📝 Notes

* The repository is configured for local-first transcription and privacy.
* Use `app/storage/` to preserve transcripts, settings, and logs.
* Do not commit large model files or binary caches if you want a lightweight repo.

---

## License

MIT
