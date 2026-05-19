# 🎙️ Onroku AI V5.5 — Deep & Detailed Features

Welcome to **Onroku AI V5.5**, an industry-grade, offline-first speech-to-text (STT) suite featuring advanced multi-speaker diarization and professional report-ready exports. It is designed to run completely locally, ensuring absolute data privacy and security.

Below is an exhaustive breakdown of the technical features, user experience mechanisms, and architectural components of Onroku AI.

---

## 1. Core Transcription Engine (Whisper)

Onroku AI uses state-of-the-art OpenAI Whisper models to generate high-accuracy transcripts fully offline.

* **Multi-Language Speech Recognition**: Seamlessly transcribes Japanese, English, Chinese, Korean, and over 90 other languages. It includes an auto-detection module that samples the first few seconds of audio to predict the language.
* **Flexible Precision Tiers**:
  * **Light Tier**: Uses the `tiny` or `base` models. Ideal for quick drafts and legacy machines.
  * **Medium Tier**: Uses the `small` or `medium` models. The perfect sweet spot of processing speed and accuracy.
  * **Heavy Tier**: Uses the flagship `large-v3` model. Captures nuanced speech, accents, technical jargon, and industry terms with human-like precision.
* **Adaptive Chunk-Based Streaming**:
  * Dynamically cuts long media files into optimized chunks (e.g., 3-minute intervals) for parallel or serialized processing.
  * Prevents memory overflow and thread locks during hours-long recording transcriptions.

---

## 2. Advanced Speaker Diarization

Onroku AI doesn't just write down what was said; it identifies **who** said it.

* **Multi-Speaker Identification**: Uses pyannote.audio pipelines and local clustering models to segment the audio by voice signature.
* **Interactive Speaker Renamer**:
  * Displays a dynamic list of detected speakers (e.g., `Speaker 1`, `Speaker 2`) in the active transcription viewport.
  * Users can type custom names (e.g., `山田さん`, `John Doe`) and save them. The app immediately updates the timeline and all corresponding export documents in real-time.
* **Timeline Segment Visualizer**: Groups text blocks by speaker chronologically with elegant modern avatars and timestamp indicators.

---

## 3. Premium Glassmorphism UI (Onroku UI)

The user interface of Onroku AI is meticulously styled following modern luxury dashboard guidelines.

* **Space-Mesh Backdrop Glow**: Features beautiful, animated gradient auroras that hover gently in the background, creating a responsive space-age atmosphere.
* **Dynamic Dark/Light Themes**:
  * Switch between theme modes instantly using the custom header button (`☀️`/`🌙`).
  * Smooth CSS transitions apply beautiful theme swaps to all panels, select forms, borders, and buttons.
* **Frosted-Glass Dropzone**:
  * Features a gorgeous transparent card with inset high-end lighting highlights and modern dashed borders.
  * Replaces simple emojis with high-resolution, custom vector SVG graphics (cloud upload arrow, document icons, directory icons).
  * **Symmetric Dynamic Buttons**: Highly aesthetic "Files" (sky-blue) and "Folder" (royal-purple) selector buttons with custom glow effects and physical hover elevations.
* **Hardware Specs Panel**:
  * Located in the left sidebar, this panel reads system resources and displays them in a sleek specs grid.
  * Polling retry mechanism queries system status securely without blocking the UI thread on startup.

---

## 4. Hardware-Aware Backend Service

The application runs a lightweight FastAPI Python service that securely connects to the Electron/React client.

* **Windows Registry CPU Detection**: Instantly reads the exact processor brand model string directly from `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0` via Python's standard `winreg` library to avoid sluggish process spawns.
* **Dynamic VRAM/GPU Inspector**: Scans GPU capability, detects NVIDIA CUDA support, and returns available video memory (VRAM) to auto-configure optimal acceleration parameters.
* **EventSource SSE Streaming**: Real-time progress percentage, current time, and operational logs are streamed continuously from the backend to the UI progress bar using Server-Sent Events (SSE).

---

## 5. Advanced A4 PDF & Grid Report Compiler

Transform raw transcripts into publication-grade documents with a single click.

* **10 Luxury PDF Layout Styles**: Includes elegant themes for corporate meetings, academic research, medical notes, legal logs, and minimalist journals.
* **Cost-Saving Density Grid**: Pages are formatted to pack the maximum readable content onto standard A4 pages to save paper during physical printing.
* **Automatic Page breaking**: Allows users to specify a minimum character threshold (e.g., 1000 characters) before generating clean page breaks.
* **Multi-Format Export Matrix**: Instantly export transcripts to standard TXT, detailed CSV, formatted Excel (.xlsx), or high-end report PDFs.

---

## 6. Hybrid Launcher & Windows Desktop Shortcut

* **One-Click Bypass Shortcut**: The root directory contains `create_shortcut.ps1`, which automatically generates a silent Desktop shortcut. Clicking the shortcut launches the backend and frontend simultaneously in a hidden PowerShell session—perfectly seamless for end-users.
* **Self-Healing API Paths**: Converts standard `file://` local React origins to fully compliant `http://` backend endpoints to bypass production browser sandbox blocks.
