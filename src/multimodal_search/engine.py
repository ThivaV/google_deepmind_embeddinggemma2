"""The model, embedding documents and queries, and an in-memory index to search them.

Nothing here writes to disk: documents, their embeddings and their previews live in the
Index for as long as the app keeps it. Torch and sentence-transformers are imported only
inside load_model(), so importing this module stays quick.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

import numpy as np
import pandas as pd

from .formats import describe, doc_type_for
from .readers import READERS, Source, count_units

MODEL_ID = "google/embeddinggemma-2"
MODEL_DIR = Path(__file__).resolve().parents[2] / ".models" / "embeddinggemma-2"
UNITS_PER_CALL = 8  # pages / segments / chunks held in memory and encoded together
BATCH_SIZE = 4      # forward-pass batch; lower it if the GPU runs out of memory
POSITIONS = ["page", "line_start", "line_end", "start_s", "end_s", "frame", "time_s"]

# One model, one GPU: embedding and searching from several threads (the desktop app) or
# browser sessions (Streamlit) take turns rather than running on the GPU at once.
_GPU = threading.Lock()


def load_model(model_dir: Path = MODEL_DIR):
    """EmbeddingGemma 2 from .models/, downloading it there first if it's missing
    (about 1.5 GB, public, no token needed)."""
    import torch
    from sentence_transformers import SentenceTransformer

    if not (model_dir / "model.safetensors").is_file():
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=MODEL_ID, local_dir=model_dir)
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    # Never float16: the model silently returns NaNs (see the model card). bfloat16 on CUDA.
    dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else torch.float32
    model = SentenceTransformer(str(model_dir), device=device, model_kwargs={"dtype": dtype})
    model.max_seq_length = 8192  # the tokenizer sets no limit; cap at the model's 8K context
    return model


@dataclass
class Document:
    """One embedded document. `units` has a row per embedding -- its `unit` (image, page,
    segment, frame or chunk), its position, `preview` (JPEG bytes) and `excerpt` -- and
    `embeddings` the matching (n, 768) unit-length vectors."""

    id: str
    name: str
    doc_type: str
    source: Source  # the path or the uploaded bytes, kept to show and play matches
    units: pd.DataFrame
    embeddings: np.ndarray
    seconds: float

    @property
    def path(self) -> Path | None:
        return None if isinstance(self.source, (bytes, bytearray)) else Path(self.source)

    @property
    def summary(self) -> str:
        """'47 pages', '6 segments · 180 frames', '1 image', ..."""
        counts = self.units["unit"].value_counts()
        parts = [f"{counts[u]} {u}{'' if counts[u] == 1 else 's'}"
                 for u in ("page", "image", "segment", "frame", "chunk") if u in counts]
        return " · ".join(parts)


@dataclass
class Hit:
    """A search result: where in which document the query matched, and how well."""

    score: float
    document: Document
    unit: str
    location: str
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    start_s: float | None = None
    end_s: float | None = None
    frame: int | None = None
    time_s: float | None = None
    preview: bytes | None = None
    excerpt: str | None = None


def embed_document(model, source: Source, name: str, *, doc_type: str | None = None,
                   doc_id: str | None = None,
                   on_progress: Callable[[int, int | None], None] | None = None) -> Document:
    """Embed one document (a path, or bytes plus its file name). on_progress(done, total)
    is called after each batch; total is an estimate and may be None."""
    doc_type = doc_type or doc_type_for(name)
    if doc_type not in READERS:
        raise ValueError(f"unsupported file type: {Path(name).suffix or name}")
    total = count_units(doc_type, source)
    started = time.perf_counter()
    units, metas, vectors = READERS[doc_type](source, model), [], []
    while chunk := list(islice(units, UNITS_PER_CALL)):
        chunk_metas, inputs = zip(*chunk, strict=True)
        with _GPU:
            vectors.append(model.encode(
                list(inputs),
                batch_size=BATCH_SIZE,
                # Video frames are already sampled at VIDEO_FPS -- keep every one of them.
                processing_kwargs={"video": {"do_sample_frames": False}},
                show_progress_bar=False,
            ))
        metas += chunk_metas
        if on_progress:
            on_progress(len(metas), total)
    if not metas:
        raise ValueError("nothing to embed")
    embeddings = np.vstack(vectors).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)  # exact unit length
    return Document(id=doc_id or name, name=name, doc_type=doc_type, source=source,
                    units=pd.DataFrame(metas), embeddings=embeddings,
                    seconds=time.perf_counter() - started)


def embed_text_query(model, text: str) -> np.ndarray:
    """A search query, with the model card's retrieval prefix ("task: search result | query: ")."""
    with _GPU:
        q = model.encode(text, prompt_name="SearchQuery", show_progress_bar=False)
    return (q / np.linalg.norm(q)).astype(np.float32)


def embed_file_query(model, source: Source, name: str) -> np.ndarray:
    """A document used as the query: the mean of its embeddings (video frames left out)."""
    doc = embed_document(model, source, name)
    q = doc.embeddings[(doc.units["unit"] != "frame").to_numpy()].mean(axis=0)
    return (q / np.linalg.norm(q)).astype(np.float32)


class Index:
    """Embedded documents, searchable together. In memory only; safe to use from threads."""

    _COLUMNS = ["doc_id", "doc_type", "unit", *POSITIONS, "preview", "excerpt"]

    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self._lock = threading.RLock()
        self._table: tuple[pd.DataFrame, np.ndarray] | None = None

    def __len__(self) -> int:
        return len(self.documents)

    def __contains__(self, doc_id: str) -> bool:
        return doc_id in self.documents

    @property
    def size(self) -> int:
        """How many embeddings are stored."""
        return sum(len(d.units) for d in list(self.documents.values()))

    def add(self, document: Document) -> None:
        with self._lock:
            self.documents[document.id] = document
            self._table = None

    def remove(self, doc_id: str) -> None:
        with self._lock:
            self.documents.pop(doc_id, None)
            self._table = None

    def clear(self) -> None:
        with self._lock:
            self.documents.clear()
            self._table = None

    def search(self, query: np.ndarray, *, top_k: int = 10,
               doc_types: Iterable[str] | None = None) -> list[Hit]:
        """The top_k best matches, best first. Whole units are ranked (pages, images, video
        and audio segments, text chunks); for a video segment, the frame inside it that
        matches best is reported as where the match is."""
        with self._lock:
            rows, matrix = self._get_table()
            documents = dict(self.documents)
        if rows.empty:
            return []
        wanted = rows["unit"] != "frame"
        if doc_types:
            wanted = wanted & rows["doc_type"].isin(list(doc_types))
        candidates = np.flatnonzero(wanted.to_numpy())
        if not len(candidates):
            return []
        scores = matrix[candidates] @ query
        hits = []
        for i in candidates[np.argsort(-scores)[:top_k]]:
            row = shown = rows.iloc[i]
            if row["doc_type"] == "video" and row["unit"] == "segment":
                frames = np.flatnonzero(((rows["doc_id"] == row["doc_id"]) & (rows["unit"] == "frame")
                                         & rows["time_s"].between(row["start_s"], row["end_s"], inclusive="left"))
                                        .to_numpy())
                if len(frames):
                    shown = rows.iloc[frames[int(np.argmax(matrix[frames] @ query))]]
            position = {c: _value(shown[c] if c in ("frame", "time_s") else row[c]) for c in POSITIONS}
            for c in ("page", "line_start", "line_end", "frame"):  # float columns once NaNs mix in
                if position[c] is not None:
                    position[c] = int(position[c])
            hits.append(Hit(
                score=float(matrix[i] @ query),
                document=documents[row["doc_id"]],
                unit=row["unit"],
                location=describe(row["doc_type"], **position),
                preview=_value(shown["preview"]),
                excerpt=_value(row["excerpt"]),
                **position,
            ))
        return hits

    def _get_table(self) -> tuple[pd.DataFrame, np.ndarray]:
        if self._table is None:
            docs = list(self.documents.values())
            if not docs:
                self._table = (pd.DataFrame(columns=self._COLUMNS), np.zeros((0, 0), np.float32))
            else:
                rows = pd.concat([d.units.assign(doc_id=d.id, doc_type=d.doc_type) for d in docs],
                                 ignore_index=True).reindex(columns=self._COLUMNS)
                self._table = (rows, np.vstack([d.embeddings for d in docs]))
        return self._table


def _value(x):
    """A table cell as a plain Python value, None for missing (NaN, NA)."""
    if isinstance(x, (bytes, str)):
        return x
    if x is None or pd.isna(x):
        return None
    return x.item() if hasattr(x, "item") else x
