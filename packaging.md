# 📦 Packaging Onroku AI V5.5 for Other PCs (.exe / .zip)

Since **Onroku AI V5.5** is an offline-first desktop application combining an Electron/React frontend and a FastAPI/Python backend, you can package it so it runs out-of-the-box on other Windows computers.

Below are the two highly recommended methods to distribute your application: **Method A (Portable ZIP Bundle)** and **Method B (Standalone EXE Compilation)**.

---

## ⚡ Method A: Portable ZIP Bundle (Highly Recommended & Easiest)

This method packages the complete frontend and a portable Python environment into a single `.zip` file. The destination PC **does not need to install Python, Node.js, or any libraries!** They simply unzip and double-click.

### Step 1: Prepare the Portable Directory
1. Compile the latest React frontend production assets:
   ```bash
   npm run build
   ```
2. Create a distribution folder named `Onroku-AI-Portable/`.
3. Copy the following items into `Onroku-AI-Portable/`:
   * `build/` (Compiled React code)
   * `app/` (Backend python & Electron main code)
   * `start_prod.bat` (The startup script)
   * `launcher.py` (The Python execution script)
   * `package.json` (Project config descriptors)

### Step 2: Bundle a Portable Python Virtual Environment
To ensure other PCs don't need to install Python:
1. Include your local virtual environment folder (`.venv/`) directly in the portable directory:
   * Copy the `.venv/` folder into `Onroku-AI-Portable/.venv/`.
2. Edit `start_prod.bat` inside the portable folder to verify it points to this local environment:
   * It will automatically detect the local `.venv` environment, active Python path, and run seamlessly.

### Step 3: Compress to ZIP
1. Right-click the `Onroku-AI-Portable/` folder and choose **Compress to ZIP file**.
2. **Distribution**: Copy this ZIP to a USB drive or upload it. The destination user only needs to:
   * Unzip the folder.
   * Run the desktop shortcut or double-click `start_prod.bat`!

---

## 🛠️ Method B: Compile Standalone Executable (.exe)

You can compile the frontend and backend into independent Windows executable binary files (`.exe`).

### 1. Compile the Electron Frontend to `.exe`
Your project's `package.json` is already fully configured with `electron-builder` to generate both standard installers and single-file portable executables.

Run this command in the project root:
```bash
npm run dist
```
#### What this does:
* Compiles the React build folder.
* Bundles all assets, preload scripts, and Electron packages.
* Generates two files inside the new `dist/` directory:
  1. `Onroku AI Setup 5.5.0.exe` (A fully custom NSIS Windows setup installer).
  2. `Onroku AI 5.5.0.exe` (A standalone, portable double-click executable that runs without installation!).

---

### 2. Compile the FastAPI Python Backend to `.exe`
To run the backend fully standalone without shipping raw Python scripts, you can compile the Python server using `PyInstaller`.

1. Activate your virtual environment and install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Compile the FastAPI launcher into a single executable binary:
   ```bash
   pyinstaller --onefile --name onroku_backend launcher.py
   ```
3. This creates a standalone `onroku_backend.exe` file inside the `dist/` directory.

---

## 🚀 Summary of Best Practices for Distribution

* **For Quick Distribution**: Method A (ZIP) is highly robust because it keeps Whisper model caches and PyTorch libraries instantly accessible, preventing slow initial decompression boots.
* **For Clean Aesthetics**: Method B (EXE) produces standard Windows installers (`Onroku AI Setup.exe`) that look highly professional, creating a clean Start Menu program and system register entry.
