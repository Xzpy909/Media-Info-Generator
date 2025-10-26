# 🎬 Media Info Generator (Python/FFprobe)

A powerful Python script that utilizes **FFprobe** to scan video files recursively within a directory, extract detailed media information (video, audio, subtitles, bitrate, HDR/Dolby Vision flags), and generate a single, responsive, searchable, dark-themed **HTML report**.

---

## ✨ Features

* **Recursive Scanning:** Automatically finds video files (`.mp4`, `.mkv`, `.avi`, etc.) in the main folder and all subfolders.
* **Detailed Stream Analysis:** Extracts codec, resolution, FPS, bit-depth (including 10-bit/12-bit detection), channels, sample rate, and bitrates.
* **HDR/Dolby Vision Detection:** Flags streams containing **HDR (BT.2020)** and **Dolby Vision** metadata.
* **Bitrate Percentage:** Calculates each video/audio stream's bitrate as a percentage of the overall file bitrate.
* **Organized HTML Output:** Groups media information by their respective folder paths and provides a search bar for quick filtering.
* **Progress Tracking:** Displays an in-terminal progress bar during the media scanning process.

---

## 🛠️ Prerequisites

To run this script, you must have the following installed and accessible:

1.  **Python 3:** The script requires Python 3.6+ and uses standard libraries (`pathlib`, `subprocess`, `json`, etc.).
2.  FFprobe in the same folder as script

---

## 🚀 Setup and Usage

### 1. Download the Script

Save the Python code `media_info_v4.py` in the root folder you wish to scan along with `FFprobe.exe`

### 2. Run the Script

Open your terminal or command prompt, navigate to the directory where you saved the script and your media files, and execute the following command:

```bash
python media_info_v4.py
