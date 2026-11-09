"""Multimodal search with EmbeddingGemma 2, shared by the Streamlit and CustomTkinter apps.

The same readers and search as notebooks/google_deepmind_embeddinggemma2.ipynb, kept in
memory instead of Milvus, and taking documents as bytes as well as paths so uploads never
have to touch the disk.

    formats  which files are supported and how to describe where a match is (no heavy imports)
    readers  a document -> EmbeddingGemma 2 inputs, plus a preview of every part
    engine   the model, embedding documents and queries, and the in-memory Index
"""

from .formats import ALL_EXTENSIONS, EXTENSIONS, ICONS, LABELS, LOGO_PNG, LOGO_SVG, clock, describe, doc_type_for

__all__ = ["ALL_EXTENSIONS", "EXTENSIONS", "ICONS", "LABELS", "LOGO_PNG", "LOGO_SVG", "clock", "describe",
           "doc_type_for"]
