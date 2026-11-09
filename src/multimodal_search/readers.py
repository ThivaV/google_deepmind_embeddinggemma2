"""A document -> EmbeddingGemma 2 inputs, one per embedding, plus what an app needs to show it.

The same readers as the notebook. A document can be a path or its bytes (an upload), and
every reader yields (metadata, model input) pairs. Besides `unit` and its position (page,
lines, seconds, frame), the metadata carries a JPEG `preview` of what was embedded (the
page, the image, the frame, a waveform of the audio) and, where there is text, an `excerpt`.
"""

from __future__ import annotations

import io
import math
from collections.abc import Iterator
from pathlib import Path

import av
import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageOps

PAGE_LONG_SIDE_PX = 1600  # render size; the model then resizes to its own token budget
SEGMENT_S = 30            # 30 frames x 140 tokens + 30 s of audio (750 tokens) fits the 8K context
VIDEO_FPS = 1             # the model's default frame rate
VIDEO_FRAME_WIDTH = 960   # decode size; plenty for 140 tokens a frame
VIDEO_WITH_AUDIO = True   # embed each video segment's soundtrack together with its frames
AUDIO_RATE = 16_000       # the audio encoder expects mono 16 kHz
TEXT_CHUNK_TOKENS = 1024  # text files: tokens per embedding (the model reads up to 8K)
PREVIEW_SIDE_PX = 1000    # previews kept in memory to show matches

Source = bytes | str | Path
Unit = tuple[dict, object]


def _file(source: Source):
    """What PIL and PyAV can open: a path, or the bytes wrapped in a file object."""
    return io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else str(source)


def _preview(image: Image.Image) -> bytes:
    """A JPEG of at most PREVIEW_SIDE_PX a side, transparency flattened onto white."""
    img = image.copy()
    img.thumbnail((PREVIEW_SIDE_PX, PREVIEW_SIDE_PX))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, "white")
        background.paste(img, mask=img.getchannel("A"))
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


def _waveform(clip: np.ndarray, size: tuple[int, int] = (1000, 400), bars: int = 96) -> bytes:
    """A picture of an audio clip -- its loudness over time as rounded bars -- as a JPEG."""
    width, height = size
    img = Image.new("RGB", size, "#fff7ed")
    draw = ImageDraw.Draw(img)
    loud = np.abs(clip)
    if len(loud) >= bars:
        loud = loud[: len(loud) // bars * bars].reshape(bars, -1).max(axis=1)
    loud = loud / (loud.max() or 1.0)
    step = width / max(len(loud), 1)
    for i, level in enumerate(loud):
        bar = max(4.0, float(level) * height * 0.8)
        draw.rounded_rectangle([i * step + step * 0.2, (height - bar) / 2, i * step + step * 0.8, (height + bar) / 2],
                               radius=step * 0.3, fill="#f97316")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


def image_units(source: Source, model) -> Iterator[Unit]:
    with Image.open(_file(source)) as img:
        img = ImageOps.exif_transpose(img)  # respect camera rotation
        yield {"unit": "image", "preview": _preview(img)}, img


def pdf_units(source: Source, model) -> Iterator[Unit]:
    pdf = pdfium.PdfDocument(source if isinstance(source, (bytes, bytearray)) else str(source))
    try:
        # Model card format for documents: "title: {title} | text: {content}", "none" if untitled.
        title = (pdf.get_metadata_dict().get("Title") or "").strip() or "none"
        for i in range(len(pdf)):
            page = pdf[i]
            width, height = page.get_size()
            image = page.render(scale=PAGE_LONG_SIDE_PX / max(width, height)).to_pil()
            textpage = page.get_textpage()
            text = " ".join(textpage.get_text_bounded().split())
            textpage.close()
            page.close()
            meta = {"unit": "page", "page": i + 1, "preview": _preview(image), "excerpt": text}
            # The image goes first, so the 8K cap can only ever cut text.
            yield meta, {"text": f"title: {title} | text: <|image|> {text}".rstrip(), "image": image}
    finally:
        pdf.close()


def text_units(source: Source, model) -> Iterator[Unit]:
    if isinstance(source, (bytes, bytearray)):
        text = bytes(source).decode("utf-8", errors="replace")
    else:
        text = Path(source).read_text(encoding="utf-8", errors="replace")
    offsets = model.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
    line, counted_to = 1, 0
    for i in range(0, len(offsets), TEXT_CHUNK_TOKENS):
        start, end = offsets[i][0], offsets[min(i + TEXT_CHUNK_TOKENS, len(offsets)) - 1][1]
        line += text.count("\n", counted_to, start)  # the line `start` is on
        counted_to = start
        last_line = line + text.count("\n", start, max(start, end - 1))
        chunk = text[start:end]
        meta = {"unit": "chunk", "line_start": line, "line_end": last_line, "excerpt": chunk}
        yield meta, f"title: none | text: {' '.join(chunk.split())}"


def load_audio(source: Source) -> tuple[np.ndarray | None, float]:
    """The whole soundtrack as mono 16 kHz float32, and the time it starts at."""
    with av.open(_file(source)) as container:
        if not container.streams.audio:
            return None, 0.0
        resampler = av.AudioResampler(format="flt", layout="mono", rate=AUDIO_RATE)
        chunks, start = [], None
        for frame in container.decode(audio=0):
            start = frame.time if start is None else start
            chunks += [f.to_ndarray().ravel() for f in resampler.resample(frame)]
        chunks += [f.to_ndarray().ravel() for f in resampler.resample(None)]  # flush
    return (np.concatenate(chunks), start or 0.0) if chunks else (None, 0.0)


def audio_units(source: Source, model) -> Iterator[Unit]:
    audio, start = load_audio(source)
    if audio is None:
        raise ValueError("no audio track")
    step = SEGMENT_S * AUDIO_RATE
    for i in range(0, len(audio), step):
        clip = audio[i:i + step]
        if i and len(clip) < AUDIO_RATE:
            break  # drop a sub-second tail: too short to mean anything on its own
        meta = {"unit": "segment", "start_s": round(start + i / AUDIO_RATE, 2),
                "end_s": round(start + (i + len(clip)) / AUDIO_RATE, 2), "preview": _waveform(clip)}
        yield meta, {"audio": {"array": clip, "sampling_rate": AUDIO_RATE}}


def video_units(source: Source, model) -> Iterator[Unit]:
    """Each SEGMENT_S seconds as one embedding (frames + sound), then each of its frames on
    its own, so a search can point at the exact frame inside a matching segment."""
    audio, audio_start = load_audio(source) if VIDEO_WITH_AUDIO else (None, 0.0)

    def segment(frames, times, numbers):
        start, end = times[0], times[0] + len(frames) / VIDEO_FPS
        inputs = {"video": frames}
        if audio is not None:
            a, b = (max(0, int((t - audio_start) * AUDIO_RATE)) for t in (start, end))
            if audio[a:b].size:
                inputs["audio"] = {"array": audio[a:b], "sampling_rate": AUDIO_RATE}
        yield {"unit": "segment", "start_s": round(start, 2), "end_s": round(end, 2)}, inputs
        for image, t, n in zip(frames, times, numbers, strict=True):
            yield {"unit": "frame", "frame": n, "time_s": round(t, 2), "preview": _preview(image)}, image

    with av.open(_file(source)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        width = min(VIDEO_FRAME_WIDTH, stream.width)
        height = round(stream.height * width / stream.width / 2) * 2
        frames, times, numbers, next_t = [], [], [], -math.inf
        for n, frame in enumerate(container.decode(stream)):  # n: the frame's number in the file
            if frame.time is None or frame.time < next_t:
                continue
            next_t = (math.floor(frame.time * VIDEO_FPS) + 1) / VIDEO_FPS  # next whole tick
            frames.append(frame.to_image(width=width, height=height))
            times.append(frame.time)
            numbers.append(n)
            if len(frames) == SEGMENT_S * VIDEO_FPS:
                yield from segment(frames, times, numbers)
                frames, times, numbers = [], [], []
        if frames:
            yield from segment(frames, times, numbers)


READERS = {
    "pdf": pdf_units,
    "image": image_units,
    "video": video_units,
    "audio": audio_units,
    "text": text_units,
}


def count_units(doc_type: str, source: Source) -> int | None:
    """Roughly how many embeddings a document will make, for progress bars (None if unknown)."""
    try:
        if doc_type == "image":
            return 1
        if doc_type == "pdf":
            pdf = pdfium.PdfDocument(source if isinstance(source, (bytes, bytearray)) else str(source))
            try:
                return len(pdf)
            finally:
                pdf.close()
        if doc_type in ("video", "audio"):
            with av.open(_file(source)) as container:
                duration = container.duration / av.time_base if container.duration else None
            if not duration:
                return None
            segments = math.ceil(duration / SEGMENT_S)
            return segments + (math.ceil(duration * VIDEO_FPS) if doc_type == "video" else 0)
    except Exception:  # only a progress estimate: the real reader reports real problems
        return None
    return None
