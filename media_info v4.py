import os
import subprocess
import json
from pathlib import Path
from collections import defaultdict
import math
import html
import sys

# Constants
SCRIPT_DIR = Path(__file__).parent
# Assuming ffprobe.exe is in the same directory, but it's often better to assume it's in PATH
# If it's not in PATH, keep the line below:
# FFPROBE = SCRIPT_DIR / "ffprobe.exe"
FFPROBE = "ffprobe" # Assuming ffprobe is available in the system PATH
HTML_FILE = SCRIPT_DIR / "media_info.html"

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm"} # Use set for faster lookups
LOSSY_CODECS = {"opus", "aac", "mp3", "vorbis", "ac3", "eac3", "dts", "dtshd"} # Use set

# --- Core Functions (kept mostly the same as they are efficient/necessary utility) ---

def run_ffprobe(file_path):
    """Executes ffprobe and returns the output as a parsed JSON dictionary."""
    # Use 'ffprobe' directly, assuming it's in PATH or linked
    cmd = [
        FFPROBE,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(file_path)
    ]
    try:
        # Use a higher timeout for very large or slow-to-analyze files
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True, encoding="utf-8", timeout=60)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"\nError running ffprobe on {file_path.name}: {e.stderr.strip()}")
        return {}
    except subprocess.TimeoutExpired:
        print(f"\nTimeout running ffprobe on {file_path.name}.")
        return {}
    except json.JSONDecodeError:
        print(f"\nError decoding JSON output from ffprobe for {file_path.name}.")
        return {}
    except FileNotFoundError:
        print(f"\nError: ffprobe not found. Please ensure it is in your system PATH or change FFPROBE constant.")
        sys.exit(1)

def clean_bit_depth(value):
    """
    Cleans up bit-depth values, replacing 0 or 'N/A' with 'Unknown / Lossy'.
    """
    if value is None or str(value) == '0' or str(value).upper() == 'N/A' or str(value) == '':
        return "Unknown / Lossy"
    return str(value)

def format_size(size_bytes):
    """
    Formats byte size into MiB or GiB, using GiB if >= 1 GiB.
    """
    try:
        size_bytes = int(size_bytes)
        # Use 1024 for binary units (MiB, GiB) as typically used for file sizes
        mib = size_bytes / (1024 * 1024)
        gib = size_bytes / (1024 * 1024 * 1024)
        if gib >= 1:
            return f"{gib:.2f} GiB"
        elif mib > 0:
            return f"{mib:.2f} MiB"
        return "0 MiB"
    except (TypeError, ValueError):
        return "N/A"

def format_duration(duration_seconds):
    """
    Formats duration in seconds to HH:MM:SS string.
    """
    try:
        duration_seconds = float(duration_seconds)
        h = int(duration_seconds // 3600)
        m = int((duration_seconds % 3600) // 60)
        s = int(duration_seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    except (TypeError, ValueError):
        return "N/A"

def get_video_bit_depth(codec, stream):
    """
    Handles video bit depth, prioritizing pix_fmt for high bit depth streams.
    """
    # ... (function body remains the same) ...
    pix_fmt = stream.get("pix_fmt", "").lower()
    if '12' in pix_fmt:
        return "12-bit"
    if '10' in pix_fmt:
        return "10-bit"
    raw_depth = stream.get("bits_per_raw_sample", stream.get("bits_per_sample"))
    return clean_bit_depth(raw_depth)

def parse_audio_sample_fmt(fmt, bits_per_sample, codec):
    """
    Prioritizes sample_fmt and includes special handling for 24-bit FLAC in s32 containers.
    """
    # ... (function body remains the same) ...
    if not fmt:
        return clean_bit_depth(bits_per_sample)
    fmt = fmt.lower().replace('p', '').replace('i', '')
    if 's8' in fmt:
        return "8-bit"
    if 's16' in fmt:
        return "16-bit"
    if 's24' in fmt:
        return "24-bit"
    if 's32' in fmt:
        if codec.lower() == 'flac':
            return "24-bit (32-bit container)"
        return "32-bit Integer"
    if 'flt' in fmt:
        return "32-bit Float"
    if 'dbl' in fmt:
        return "64-bit Float"
    return clean_bit_depth(bits_per_sample)

def format_bitrate(bps_value):
    """Converts a bitrate in bits/s (BPS) to a human-readable kb/s string."""
    try:
        bps = int(bps_value)
        if bps > 0:
            # Use 1000 for metric prefix (kilo, mega) in bitrates (kb/s, Mb/s)
            kbps = round(bps / 1000, 0)
            return f"{kbps:.0f} kb/s"
    except (TypeError, ValueError):
        pass
    return None

def calculate_fps(rate_str):
    """Calculates the FPS from a string like 'num/den' and outputs as integer if no decimals are needed."""
    # ... (function body remains the same) ...
    if not rate_str or '/' not in rate_str:
        return rate_str
    try:
        num, den = map(int, rate_str.split('/'))
        if den > 0:
            fps = num / den
            if fps == int(fps):
                return f"{int(fps)}"
            return f"{fps:.3f}"
        return rate_str
    except (ValueError, ZeroDivisionError):
        return rate_str

def calculate_aspect_ratio(width, height):
    """
    Calculates the simplified aspect ratio (e.g., 16:9) from pixel width and height.
    """
    # ... (function body remains the same) ...
    if width is None or height is None or width == 0 or height == 0:
        return "N/A"
    try:
        width = int(width)
        height = int(height)
        common = math.gcd(width, height)
        ar_w = width // common
        ar_h = height // common
        return f"{ar_w}:{ar_h}"
    except (ValueError, TypeError):
        return "N/A"

def parse_dar(dar):
    """Safely parses display aspect ratio (e.g., '16:9') to a float."""
    # ... (function body remains the same) ...
    if not dar or ':' not in dar:
        return None
    try:
        w, h = map(int, dar.split(':'))
        return w / h if h else None
    except (ValueError, ZeroDivisionError):
        return None

def extract_info(data):
    """Extracts key media information from the ffprobe JSON data, including Dolby Vision and HDR detection and calculates bitrate percentage."""
    # ... (function body remains the same, it's already well-optimized) ...
    temp_video_streams = []
    audio_info = []
    subtitle_info = []
    format_data = data.get("format", {})

    # --- General Info & Overall Bitrate Calculation ---
    general_info = {}
    general_info["Filesize"] = format_size(format_data.get('size'))
    container_name = format_data.get("format_long_name", format_data.get("format_name", "N/A")).split(',')[0].replace("Matroska / WebM", "Matroska")
    general_info["Container"] = container_name
    general_info["Duration"] = format_duration(format_data.get('duration'))

    overall_bitrate_int = 0
    overall_bitrate_display = "N/A"
    try:
        bit_rate_format = format_data.get("bit_rate")
        if bit_rate_format:
            overall_bitrate_int = int(bit_rate_format)
        else:
            size_bits = int(format_data.get('size')) * 8
            duration = float(format_data.get('duration'))
            if size_bits and duration > 0:
                overall_bitrate_int = int(size_bits / duration)
        if overall_bitrate_int > 0:
            overall_bitrate_display = format_bitrate(overall_bitrate_int)
    except (TypeError, ValueError, AttributeError):
        pass
    general_info["Overall Bitrate"] = overall_bitrate_display

    for stream in data.get("streams", []):
        codec = stream.get("codec_name", "N/A")
        codec_type = stream.get("codec_type", "unknown")

        # --- Stream Bitrate Logic with Percentage ---
        tags = stream.get("tags", {})
        bitrate_int = 0
        bitrate_display = None
        if codec_type in ["video", "audio"]:
            try:
                bps_tagged = tags.get("BPS")
                bps_stream = stream.get("bit_rate")
                if bps_tagged:
                    bitrate_int = int(bps_tagged)
                elif bps_stream:
                    bitrate_int = int(bps_stream)
            except (TypeError, ValueError):
                pass
            if bitrate_int > 0:
                percentage_display = ""
                if overall_bitrate_int > 0:
                    percentage = min((bitrate_int / overall_bitrate_int) * 100, 100)
                    percentage_display = f" ({percentage:.0f}%)" if percentage > 0 else ""
                bitrate_display = f"{format_bitrate(bitrate_int)}{percentage_display}"

        if codec_type == "video":
            fps_value = calculate_fps(stream.get("r_frame_rate", "N/A"))
            bit_depth = get_video_bit_depth(codec, stream)
            width = stream.get('width')
            height = stream.get('height')
            dar = stream.get("display_aspect_ratio", "N/A")

            if dar != "N/A" and dar is not None:
                dar_ratio = parse_dar(dar)
                if dar_ratio:
                    if 1.77 <= dar_ratio <= 1.78:
                        display_ar = "16:9"
                    elif 2.3 <= dar_ratio <= 2.4:
                        display_ar = "21:9"
                    elif 1.33 <= dar_ratio <= 1.34:
                        display_ar = "4:3"
                    else:
                        display_ar = dar
                else:
                    display_ar = calculate_aspect_ratio(width, height)
            else:
                display_ar = calculate_aspect_ratio(width, height)

            resolution_display = f"{width}x{height} ({display_ar})"
            is_dovi = False
            is_hdr = False
            side_data = stream.get("side_data_list", [])
            for item in side_data:
                if item.get("side_data_type") == "DOVI configuration record":
                    is_dovi = True
                    break
            if stream.get("color_primaries") == "bt2020" or stream.get("color_space") == "bt2020nc":
                is_hdr = True
            display_codec = codec
            if is_dovi:
                display_codec = f"{codec} + Dolby Vision"
            elif is_hdr:
                display_codec = f"{codec} + HDR"

            video_data = {
                "Codec": display_codec,
                "Bit-depth": bit_depth,
                "Resolution": resolution_display,
                "FPS": fps_value,
                "_is_dovi_metadata_legacy": stream.get('width', 0) < 1000 and codec.lower() in ['mjpeg', 'h264', 'avc'],
                "_width": stream.get("width"),
            }
            if bitrate_display:
                video_data["Bitrate"] = bitrate_display
            temp_video_streams.append(video_data)

        elif codec_type == "audio":
            sample_fmt = stream.get("sample_fmt", "")
            raw_bits = stream.get("bits_per_sample")
            display_codec = codec
            if codec.lower() in ["truehd", "eac3"]:
                profile = stream.get("profile", "")
                if profile:
                    display_codec = profile
            audio_data = {
                "ID": stream.get("index", "N/A"),
                "Language": stream.get("tags", {}).get("language", "N/A"),
                "Codec": display_codec,
                "Channels": stream.get("channels", "N/A"),
                "Sample Rate": stream.get("sample_rate", "N/A"),
            }
            if bitrate_display:
                audio_data["Bitrate"] = bitrate_display
            if codec.lower() not in LOSSY_CODECS:
                bit_depth = parse_audio_sample_fmt(sample_fmt, raw_bits, codec)
                audio_data["Bit-depth"] = bit_depth
            audio_info.append(audio_data)

        elif codec_type == "subtitle":
            subtitle_info.append({
                "Language": stream.get("tags", {}).get("language", "N/A"),
                "Type": codec,
                "ID": stream.get("index", "N/A")
            })

    # Filter out low-resolution "legacy" DOVI metadata streams if a main stream exists
    final_video_streams = []
    has_main_stream = any(v.get('_width', 0) >= 1000 for v in temp_video_streams)
    for v in temp_video_streams:
        if has_main_stream and v.get('_is_dovi_metadata_legacy', False):
            continue
        v.pop('_is_dovi_metadata_legacy', None)
        v.pop('_width', None)
        final_video_streams.append(v)

    return final_video_streams, audio_info, subtitle_info, general_info

def generate_html(info_dict_by_folder):
    """Generates responsive, dark-themed HTML content with vanilla CSS, grouped by folder."""
    # ... (function body remains the same, as the HTML structure is already good) ...
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Media Info Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Public Sans', sans-serif;
            background-color: #0a0a0a;
            color: #e5e7eb;
            padding: 24px;
            min-height: 100vh;
            margin: 0;
        }
        .container-wrapper {
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            text-align: center;
            margin-bottom: 40px;
        }
        h1 {
            font-size: 36px;
            font-weight: 800;
            color: #2dd4bf;
            border-bottom: 2px solid #2dd4bf;
            display: inline-block;
            padding-bottom: 8px;
        }
        #search {
            background-color: #1f2937;
            color: #e5e7eb;
            padding: 8px;
            border-radius: 4px;
            border: none;
            width: 100%;
            margin-bottom: 24px;
            font-size: 16px;
        }
        #search:focus {
            outline: none;
            box-shadow: 0 0 0 2px #2dd4bf;
        }
        .info-card {
            background-color: #1c1c1e;
            border-radius: 12px;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.6);
            padding: 24px;
            margin: 16px 0;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .info-card:hover, .info-card:focus-within {
            transform: translateY(-2px);
            box-shadow: 0 6px 15px rgba(0, 0, 0, 0.8);
        }
        .stream-container {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }
        .stream-block {
            padding: 16px;
            border-radius: 8px;
            background-color: #1a1a1a;
            border: 1px solid #2d2d2d;
        }
        .stream-block[aria-label="General Info"] {
            border-left: 4px solid #9ca3af;
        }
        .stream-block[aria-label="Video Stream Information"] {
            border-left: 4px solid #3b82f6;
        }
        .stream-block[aria-label="Audio Stream Information"] {
            border-left: 4px solid #22c55e;
        }
        .stream-block[aria-label="Subtitle Stream Information"] {
            border-left: 4px solid #a78bfa;
        }
        .info-tag {
            font-weight: 600;
            margin-right: 8px;
            color: #d1d5db;
        }
        .info-pill {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 9999px;
            font-size: 14px;
            font-weight: 600;
            margin-right: 8px;
            margin-top: 4px;
            white-space: nowrap;
        }
        .info-pill.codec-dolby {
            background-color: #6b21a8;
            color: #f3e8ff;
        }
        .info-pill.codec-hdr {
            background-color: #115e59;
            color: #ccfbf1;
        }
        .info-pill.codec-lossy {
            background-color: #7f1d1d;
            color: #fee2e2;
        }
        .info-pill.codec {
            background-color: #1e40af;
            color: #dbeafe;
        }
        .info-pill.language, .info-pill.type {
            background-color: #4b5563;
            color: #e5e7eb;
        }
        .stream-block [data-value="N/A"] {
            color: #6b7280;
        }
        .stream-block .empty-state {
            background-color: #2d2d2d;
            padding: 8px;
            border-radius: 4px;
            font-style: italic;
            color: #9ca3af;
        }
        details {
            background-color: #101010;
            padding: 16px;
            border-radius: 8px;
            border: 1px solid #1f2937;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.6);
        }
        details summary {
            font-size: 20px;
            font-weight: 700;
            color: #e5e7eb;
            cursor: pointer;
            transition: color 0.15s;
        }
        details summary:hover {
            color: #2dd4bf;
        }
        details summary::marker {
            content: '';
            display: none;
        }
        details summary:before {
            content: '▶ ';
            display: inline-block;
            color: #a78bfa;
            margin-right: 8px;
        }
        details[open] summary:before {
            content: '▼ ';
        }
        h2 {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 24px;
            border-bottom: 2px solid rgba(45, 212, 191, 0.5);
            padding-bottom: 12px;
            color: #ffffff;
        }
        h3 {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 12px;
            padding-bottom: 8px;
        }
        .stream-block[aria-label="General Info"] h3 {
            color: #9ca3af;
            border-bottom: 1px solid #4b5563;
        }
        .stream-block[aria-label="Video Stream Information"] h3 {
            color: #3b82f6;
            border-bottom: 1px solid #60a5fa;
        }
        .stream-block[aria-label="Audio Stream Information"] h3 {
            color: #22c55e;
            border-bottom: 1px solid #4ade80;
        }
        .stream-block[aria-label="Subtitle Stream Information"] h3 {
            color: #a78bfa;
            border-bottom: 1px solid #c4b5fd;
        }
        .stream-block ul {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        .stream-block li {
            padding-top: 8px;
            border-top: 1px solid #374151;
        }
        .stream-block li:first-child {
            border-top: none;
        }
        .stream-block li > div {
            margin: 4px 0;
        }
        details > div {
            margin-top: 16px;
            padding-left: 16px;
            border-left: 2px solid #374151;
        }
        .space-y-10 > * + * {
            margin-top: 40px;
        }
        @media (min-width: 480px) {
            .stream-container {
                display: flex;
                flex-wrap: wrap;
                gap: 24px;
            }
            .stream-block {
                flex: 1 1 23%;
                min-width: 200px;
            }
        }
    </style>
</head>
<body>
<div class="container-wrapper">
    <header>
        <h1>🎬 Media Info Report</h1>
        <input type="text" id="search" placeholder="Search files..." aria-label="Search media files">
    </header>
    <div class="space-y-10">
"""
    for folder_name, info_list in info_dict_by_folder.items():
        is_root = folder_name == "."
        if not is_root:
            html_content += f"""
        <details aria-expanded="false">
            <summary>📂 {html.escape(folder_name)} ({len(info_list)} files)</summary>
            <div>
            """

        for filename, (video, audio, subs, general) in info_list:
            filename_escaped = html.escape(filename)
            html_content += f"""
        <div class="info-card">
            <h2>{filename_escaped}</h2>
            <div class="stream-container">
                <div class="stream-block" role="region" aria-label="General Info">
                    <h3>📦 General Info</h3>
                    <ul>
            """
            for k, val in general.items():
                html_content += f"<li><div><span class='info-tag'>{k}:</span> <span data-value='{html.escape(str(val))}'>{html.escape(str(val))}</span></div></li>"
            html_content += "</ul></div>"

            html_content += """
                <div class="stream-block" role="region" aria-label="Video Stream Information">
                    <h3>📹 Video Stream</h3>
                    <ul>
            """
            if not video:
                html_content += '<li class="empty-state">No video stream found.</li>'
            for v in video:
                html_content += '<li>'
                bit_depth_val = v.pop("Bit-depth", "N/A")
                codec_val = v.pop("Codec", "N/A")
                if "Lossy" in bit_depth_val or "Unknown" in bit_depth_val:
                    simplified_depth = "Lossy"
                elif "12-bit" in bit_depth_val:
                    simplified_depth = "12-bit"
                elif "10-bit" in bit_depth_val:
                    simplified_depth = "10-bit"
                elif "24-bit" in bit_depth_val:
                    simplified_depth = "24-bit"
                elif bit_depth_val.isdigit():
                    simplified_depth = f"{bit_depth_val}-bit"
                else:
                    simplified_depth = bit_depth_val.split(' ')[0]
                combined_codec = f"{codec_val} {simplified_depth}"
                pill_class = "codec"
                if "Dolby Vision" in combined_codec:
                    pill_class = "codec-dolby"
                elif "HDR" in combined_codec or "10-bit" in combined_codec or "12-bit" in combined_codec:
                    pill_class = "codec-hdr"
                elif "Lossy" in simplified_depth:
                    pill_class = "codec-lossy"
                html_content += f"<div><span class='info-tag'>Codec:</span> <span class='info-pill {pill_class}' data-value='{html.escape(combined_codec)}'>{html.escape(combined_codec)}</span></div>"
                for k, val in v.items():
                    html_content += f"<div><span class='info-tag'>{k}:</span> <span data-value='{html.escape(str(val))}'>{html.escape(str(val))}</span></div>"
                html_content += '</li>'
            html_content += "</ul></div>"

            html_content += """
                <div class="stream-block" role="region" aria-label="Audio Stream Information">
                    <h3>🔊 Audio Stream(s)</h3>
                    <ul>
            """
            if not audio:
                html_content += '<li class="empty-state">No audio stream(s) found.</li>'
            for a in audio:
                html_content += '<li>'
                for k, val in a.items():
                    if k == "Codec":
                        html_content += f"<div><span class='info-tag'>{k}:</span> <span class='info-pill codec' data-value='{html.escape(str(val))}'>{html.escape(str(val))}</span></div>"
                    elif k == "Language":
                        html_content += f"<div><span class='info-tag'>{k}:</span> <span class='info-pill language' data-value='{html.escape(str(val))}'>{html.escape(str(val))}</span></div>"
                    else:
                        html_content += f"<div><span class='info-tag'>{k}:</span> <span data-value='{html.escape(str(val))}'>{html.escape(str(val))}</span></div>"
                html_content += '</li>'
            html_content += "</ul></div>"

            html_content += """
                <div class="stream-block" role="region" aria-label="Subtitle Stream Information">
                    <h3>💬 Subtitle Stream(s)</h3>
            """
            if not subs:
                html_content += '<ul><li class="empty-state">No subtitle stream(s) found.</li></ul></div>'
            else:
                if len(subs) > 3:
                    html_content += f'<details aria-expanded="false"><summary>Show {len(subs)} Streams</summary><ul>'
                else:
                    html_content += '<ul>'
                for s in subs:
                    html_content += '<li>'
                    for k, val in s.items():
                        if k == "Type":
                            html_content += f"<div><span class='info-tag'>{k}:</span> <span class='info-pill type' data-value='{html.escape(str(val))}'>{html.escape(str(val))}</span></div>"
                        else:
                            html_content += f"<div><span class='info-tag'>{k}:</span> <span data-value='{html.escape(str(val))}'>{html.escape(str(val))}</span></div>"
                    html_content += '</li>'
                html_content += "</ul>"
                if len(subs) > 3:
                    html_content += "</details>"
                html_content += "</div>"
            html_content += "</div></div>"

        if not is_root:
            html_content += "</div></details>"

    html_content += """
    </div>
    <script>
        document.getElementById('search').addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            document.querySelectorAll('.info-card').forEach(card => {
                const text = card.textContent.toLowerCase();
                card.style.display = text.includes(term) ? '' : 'none';
            });
        });
    </script>
</div></body></html>
"""
    return html_content

def print_progress_bar(current, total, width=40):
    """Prints a non-emoji-based progress bar to reduce I/O overhead on different terminals."""
    if total == 0:
        return
    percent = current / total
    filled = int(width * percent)
    empty = width - filled
    bar = '█' * filled + '░' * empty
    sys.stdout.write(f"\rScanning files: [{bar}] {int(percent * 100)}% ({current}/{total})")
    sys.stdout.flush()

def main():
    info_dict_by_folder = defaultdict(list)
    
    # 1. Collect all eligible files first
    all_files = [f for f in SCRIPT_DIR.rglob('*') if f.is_file() and f.suffix.lower() in VIDEO_EXTS and f != HTML_FILE]
    total_files = len(all_files)
    processed_files = 0

    if total_files == 0:
        print("No media files found with extensions:", ", ".join(VIDEO_EXTS))
        return

    # 2. Process files with progress bar
    print(f"Total files to process: {total_files}")
    for file in all_files:
        processed_files += 1
        print_progress_bar(processed_files, total_files)
        
        # This will be printed *before* the progress bar line if an error/timeout occurs.
        # Otherwise, the progress bar will update smoothly.
        # print(f"\nProcessing: {file.relative_to(SCRIPT_DIR)}") 

        data = run_ffprobe(file)
        
        if data:
            video, audio, subs, general = extract_info(data)
            relative_path = file.relative_to(SCRIPT_DIR)
            
            # Optimized logic for folder grouping:
            # If path parts > 1, the folder is everything up to the file name.
            if len(relative_path.parts) > 1:
                # Joins the directory components (handles subfolders inside subfolders)
                folder_name = str(relative_path.parent) 
                filename_display = file.name
            else:
                folder_name = "." # Root directory
                filename_display = file.name
            
            info_dict_by_folder[folder_name].append((filename_display, (video, audio, subs, general)))

    # Print final progress status/newline
    if processed_files > 0:
        print_progress_bar(total_files, total_files)
        print() # Ensure the next message starts on a new line

    # 3. Generate Report
    if info_dict_by_folder:
        for folder_name in info_dict_by_folder:
            info_dict_by_folder[folder_name].sort(key=lambda x: x[0])

        html_content = generate_html(info_dict_by_folder)

        # Use atomic write to prevent partial file writes if the script is interrupted
        temp_file = HTML_FILE.with_suffix('.tmp')
        temp_file.write_text(html_content, encoding="utf-8")
        temp_file.replace(HTML_FILE)
        print(f"✅ HTML Report generated: {HTML_FILE}")
    else:
        print("⚠️ No media information extracted. HTML report skipped.")

if __name__ == "__main__":
    main()