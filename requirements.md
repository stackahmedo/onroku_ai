# 🖥️ Onroku AI V5.5 — Hardware & System Requirements

This document outlines the hardware specifications, operating system requirements, and platform dependencies needed to run **Onroku AI V5.5** locally.

---

## 🎛️ 1. Minimum & Recommended System Specs

Because Onroku AI runs **100% locally and offline**, the performance (speed of transcription) depends directly on your computer's hardware.

| Component | Minimum Specification | Recommended Specification |
| :--- | :--- | :--- |
| **OS** | Windows 10 (64-bit) | Windows 11 (64-bit) |
| **Processor (CPU)** | Intel Core i5 (8th Gen) / AMD Ryzen 5 | Intel Core i7/i9 (10th Gen+) / AMD Ryzen 7/9 |
| **System RAM** | 8 GB DDR4 | 16 GB - 32 GB DDR4/DDR5 |
| **Graphics (GPU)** | Standard Integrated Graphics | NVIDIA GeForce RTX 30/40 Series (8GB+ VRAM) |
| **Storage** | 5 GB available HDD space | 15 GB available SSD space (highly recommended) |

---

## ⚡ 2. Precision Tiers & Memory Footprint

Onroku AI offers three operational tiers tailored to your hardware capacity. Selecting the right tier ensures optimal speed and prevents memory crashes.

### 🟢 Light Tier (Tiny / Base Models)
* **Target Hardware**: Ultra-books, standard office laptops, and older PCs.
* **RAM Requirement**: 4 GB - 8 GB of free system memory.
* **Whisper Model Weight size**: ~150 MB.
* **Performance**: Extremely fast transcription, ideal for clean audio and rapid drafts.

### 🔵 Medium Tier (Small / Medium Models)
* **Target Hardware**: Modern mid-range laptops and standard developer machines.
* **RAM Requirement**: 8 GB - 16 GB of system memory.
* **Whisper Model Weight size**: ~1.5 GB.
* **Performance**: Outstanding balance between processing speed and sentence layout precision. Perfect for multi-speaker discussions.

### 🟣 Heavy Tier (Whisper Large V3 flagship)
* **Target Hardware**: Gaming PCs, high-end workstations, and servers equipped with dedicated GPUs.
* **RAM Requirement**: 16 GB - 32 GB of system memory.
* **Whisper Model Weight size**: ~3.1 GB.
* **Performance**: Maximum state-of-the-art accuracy. Captures overlapping speech, soft voices, technical terms, and multiple languages with top-tier precision.

---

## 🏎️ 3. GPU CUDA Acceleration Requirements

To achieve lightning-fast transcription (e.g., transcribing 1 hour of audio in under 3 minutes), a compatible NVIDIA GPU with CUDA acceleration is highly recommended.

* **GPU Vendor**: NVIDIA only (AMD ROCm and Intel Arc are supported via CPU fallback modes).
* **VRAM Capacity**:
  * For Medium Tier: **4 GB VRAM** minimum.
  * For Heavy Tier (Large V3): **8 GB VRAM** recommended.
* **Software Drivers Required**:
  * NVIDIA Graphics Driver: Version 520.x or newer.
  * CUDA Toolkit: Version 11.8 or 12.1.
  * PyTorch with CUDA enabled.

---

## 📂 4. Supported Audio & Video Formats

The backend engine features automated media stream conversion powered by local FFmpeg libraries. You do not need to convert your files manually before uploading.

### Supported Audio Formats:
* `.mp3` (MPEG Layer 3)
* `.wav` (Waveform Audio)
* `.m4a` / `.aac` (Advanced Audio Coding)
* `.flac` (Free Lossless Audio Codec)
* `.ogg` (Ogg Vorbis)

### Supported Video Formats:
* `.mp4` (MPEG-4 Part 14)
* `.mov` (QuickTime Movie)
* `.mkv` (Matroska Video)
* `.avi` (Audio Video Interleave)

---

## 🔍 5. Registry-Based Diagnostic Diagnostics

Onroku AI features a secure system-aware hardware inspector panel that scans your machine's properties on boot:
* **CPU Model Detection**: Instantaneous scan of the Windows registry brand name under `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0`.
* **RAM Inspector**: Reads total physical memory.
* **GPU Inspector**: Automatically queries PyTorch to check if `cuda.is_available()` is positive. If positive, it unlocks hardware acceleration seamlessly.
