"""Read embedded metadata from originals, never from converted previews."""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path


def _text(value) -> str:
    if isinstance(value, bytes):
        return f"Binary data ({len(value)} bytes)"
    if isinstance(value, dict):
        return json.dumps({str(k): _text(v) for k, v in value.items()}, ensure_ascii=False)
    if isinstance(value, (tuple, list)):
        return ", ".join(_text(v) for v in value)
    return str(value)


def _label(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ")


def extract_metadata(path: Path) -> dict:
    groups: dict[str, dict[str, str]] = {}
    notes: list[str] = []

    def add(group: str, key: str, value):
        if value is not None and value != "":
            groups.setdefault(group, {})[key] = _text(value)

    # ExifTool covers EXIF, GPS, maker notes, XMP, IPTC and QuickTime tags.
    # System fields describe the temporary USB copy, not the original.
    if shutil.which("exiftool"):
        try:
            result = subprocess.run(
                ["exiftool", "-j", "-G1", "-a", "-s", str(path)],
                capture_output=True, text=True, timeout=30, check=True)
            for key, value in json.loads(result.stdout)[0].items():
                group, _, tag = key.partition(":")
                if group in {"SourceFile", "System", "ExifTool"}:
                    continue
                add(group, tag or key, value)
        except (OSError, subprocess.SubprocessError, ValueError, IndexError, TypeError):
            notes.append("Some embedded tags could not be read by ExifTool.")
    else:
        notes.append("ExifTool is unavailable; extended camera, XMP and QuickTime tags may be missing.")

    if path.suffix.lower() in {".mov", ".mp4", ".m4v", ".avi", ".mkv"}:
        if shutil.which("ffprobe"):
            try:
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                    capture_output=True, text=True, timeout=30, check=True)
                data = json.loads(result.stdout)
                for key, value in data.get("format", {}).items():
                    if key == "filename":
                        continue
                    if key == "tags":
                        for tag, v in value.items():
                            add("Container tags", tag, v)
                    else:
                        add("Container", key, value)
                for i, stream in enumerate(data.get("streams", [])):
                    group = f"Stream {i + 1} ({stream.get('codec_type', 'media')})"
                    for key, value in stream.items():
                        if key == "tags":
                            for tag, v in value.items():
                                add(group + " tags", tag, v)
                        else:
                            add(group, key, value)
            except (OSError, subprocess.SubprocessError, ValueError, TypeError):
                notes.append("Video stream metadata could not be read.")
        else:
            notes.append("FFprobe is unavailable; video stream details may be missing.")
    elif not groups:
        try:
            from PIL import ExifTags, Image
            if path.suffix.lower() in {".heic", ".heif"}:
                try:
                    from pillow_heif import register_heif_opener
                    register_heif_opener()
                except ImportError:
                    pass
            with Image.open(path) as im:
                add("Image", "ImageWidth", im.width)
                add("Image", "ImageHeight", im.height)
                add("Image", "ColorMode", im.mode)
                add("Image", "Format", im.format)
                for key, value in im.info.items():
                    if key != "exif":
                        add("Image", key, value)
                exif = im.getexif()
                for key, value in exif.items():
                    if key not in {34665, 34853}:
                        add("EXIF", ExifTags.TAGS.get(key, str(key)), value)
                for key, value in exif.get_ifd(34665).items():
                    add("EXIF", ExifTags.TAGS.get(key, str(key)), value)
                gps = exif.get_ifd(34853)
                for key, value in gps.items():
                    add("GPS", ExifTags.GPSTAGS.get(key, str(key)), value)
                if all(k in gps for k in (1, 2, 3, 4)):
                    def degrees(parts, ref):
                        val = float(parts[0]) + float(parts[1]) / 60 + float(parts[2]) / 3600
                        return -val if ref in ("S", "W", b"S", b"W") else val
                    lat, lon = degrees(gps[2], gps[1]), degrees(gps[4], gps[3])
                    if math.isfinite(lat) and math.isfinite(lon):
                        add("GPS", "GPSPosition", f"{lat:.6f}, {lon:.6f}")
        except Exception:
            notes.append("Image metadata could not be decoded from this original.")

    def first(*tags):
        for tag in tags:
            for entries in groups.values():
                if tag in entries:
                    return entries[tag]
        return None

    summary = []
    for label, tags in [
        ("Captured", ("SubSecDateTimeOriginal", "DateTimeOriginal", "CreationDate", "CreateDate", "creation_time")),
        ("Time zone", ("OffsetTimeOriginal", "OffsetTime")),
        ("Modified (embedded)", ("ModifyDate", "DateTime")),
        ("Location", ("GPSPosition", "GPSCoordinates", "com.apple.quicktime.location.ISO6709", "location")),
        ("Latitude", ("GPSLatitude",)), ("Longitude", ("GPSLongitude",)),
        ("Altitude", ("GPSAltitude",)),
        ("Camera make", ("Make", "com.apple.quicktime.make")),
        ("Camera model", ("Model", "com.apple.quicktime.model")),
        ("Lens", ("LensModel", "LensID")),
        ("Width", ("ImageWidth", "ExifImageWidth", "width")),
        ("Height", ("ImageHeight", "ExifImageHeight", "height")),
        ("Duration", ("Duration", "duration")),
        ("Frame rate", ("VideoFrameRate", "avg_frame_rate", "r_frame_rate")),
        ("Codec", ("CompressorName", "codec_long_name", "codec_name")),
        ("Aperture", ("FNumber", "Aperture")),
        ("Exposure", ("ExposureTime", "ShutterSpeed")),
        ("ISO", ("ISO", "ISOSpeedRatings")),
        ("Focal length", ("FocalLength",)),
        ("Orientation", ("Orientation", "Rotation")),
        ("Color space", ("ColorSpace", "color_space")),
        ("Software", ("Software", "com.apple.quicktime.software")),
    ]:
        value = first(*tags)
        if value is not None:
            summary.append({"label": label, "value": value})
    return {
        "summary": summary,
        "sections": [{"name": group, "fields": [{"label": _label(k), "value": v} for k, v in entries.items()]}
                     for group, entries in groups.items()],
        "notes": notes,
    }
