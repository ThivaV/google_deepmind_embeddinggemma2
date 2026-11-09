"""Which files can be embedded, and how to say where in a document a match is.

Deliberately free of heavy imports, so an app can use it before the model has loaded.
"""

from __future__ import annotations

from pathlib import Path

EXTENSIONS: dict[str, tuple[str, ...]] = {
    "pdf": (".pdf",),
    "image": (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"),
    "video": (".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"),
    "audio": (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"),
    "text": (".txt", ".md", ".markdown", ".rst"),
}
TYPE_BY_EXTENSION = {ext: doc_type for doc_type, exts in EXTENSIONS.items() for ext in exts}
ALL_EXTENSIONS = sorted(TYPE_BY_EXTENSION)

LABELS = {"pdf": "PDF", "image": "Image", "video": "Video", "audio": "Audio", "text": "Text"}
ICONS = {"pdf": "📄", "image": "🖼️", "video": "🎬", "audio": "🎧", "text": "📝"}

# The apps' logo: a magnifying glass over one space where every kind of document lives.
ASSETS = Path(__file__).resolve().parent / "assets"
LOGO_SVG = ASSETS / "logo.svg"  # the source -- edit this one
LOGO_PNG = ASSETS / "logo.png"  # a 512 px render of it, for the Dock and the browser tab


def doc_type_for(name: str | Path) -> str | None:
    """The document type a file name's extension means, or None if it isn't supported."""
    return TYPE_BY_EXTENSION.get(Path(name).suffix.lower())


def clock(seconds: float) -> str:
    """174.0 -> '2:54'; 3725 -> '1:02:05'."""
    minutes, s = divmod(int(round(float(seconds))), 60)
    h, m = divmod(minutes, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def describe(doc_type: str, *, page=None, line_start=None, line_end=None,
             start_s=None, end_s=None, frame=None, time_s=None) -> str:
    """Where in its document a match is, in words: 'page 14', 'frame 1260 at 0:42', ..."""
    if doc_type == "pdf":
        return f"page {page}"
    if doc_type == "image":
        return "whole image"
    if doc_type == "text":
        return f"lines {line_start}–{line_end}"
    span = f"{clock(start_s)}–{clock(end_s)}"
    if doc_type == "video" and frame is not None:
        return f"frame {frame} at {clock(time_s)} (segment {span})"
    return span
