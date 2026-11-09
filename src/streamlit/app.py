"""Multimodal search with EmbeddingGemma 2, in the browser.

Upload PDFs, images, videos, audio and text files. They are embedded in memory for this
browser session -- nothing is written to disk -- and searched by meaning. Every match says
where it is: the page, the video frame and moment, the time range, the lines.

    cd src/streamlit
    streamlit run app.py
"""

from __future__ import annotations

import io
import mimetypes
import re
import sys
from pathlib import Path

import streamlit as st
from PIL import Image

sys.path.append(str(Path(__file__).resolve().parents[1]))  # src/, for the shared package
from multimodal_search import ALL_EXTENSIONS, EXTENSIONS, ICONS, LABELS, LOGO_PNG, LOGO_SVG, clock  # noqa: E402
from multimodal_search.engine import (  # noqa: E402
    Hit,
    Index,
    embed_document,
    embed_file_query,
    embed_text_query,
    load_model,
)

MAX_UPLOAD_MB = 4096   # per file; Streamlit's default of 200 MB is too small for a big PDF or video
PER_ROW = 3
CARD = (800, 520)      # every card's preview fits this box, so the grid lines up
CARD_TEXT_PX = 214     # a text match's excerpt box: about the height of a preview in a card
UPLOAD_TYPES = [ext.lstrip(".") for ext in ALL_EXTENSIONS]
WHERE = {"pdf": "the page", "image": "the image", "video": "the frame and the moment",
         "audio": "the time range", "text": "the lines"}
BADGE = {"pdf": "red", "image": "blue", "video": "violet", "audio": "orange", "text": "green"}


@st.cache_resource(show_spinner="Loading EmbeddingGemma 2 -- the first run downloads it (1.5 GB)…")
def get_model():
    return load_model()


def main() -> None:
    st.set_page_config(page_title="Multimodal search · EmbeddingGemma 2", page_icon=str(LOGO_PNG), layout="wide")
    st.logo(str(LOGO_SVG), size="large")
    state = st.session_state
    state.setdefault("index", Index())
    state.setdefault("failed", {})          # upload file_id -> (file name, error)
    state.setdefault("uploader", 0)         # bumping it empties the uploader
    state.setdefault("query_vectors", {})   # query-file file_id -> its embedding

    with st.sidebar:
        st.header("📚 Documents")
        uploads = st.file_uploader(
            "Add documents", type=UPLOAD_TYPES, accept_multiple_files=True, max_upload_size=MAX_UPLOAD_MB,
            key=f"uploads-{state.uploader}",
            help="PDFs, images, videos, audio and text files. They stay in memory for this browser session only.",
        )
        document_list = st.container()

    logo, heading = st.columns([1, 13], vertical_alignment="center")
    logo.image(str(LOGO_SVG), width="stretch")
    with heading:
        st.title("Multimodal search")
        st.caption("Search PDFs, images, videos, audio and text by meaning with Google DeepMind's "
                   "EmbeddingGemma 2. Every match says where it is.")
    model = get_model()
    sync(model, state.index, uploads or [])
    with document_list:
        show_documents(model, state.index)

    if len(state.index):
        search(model, state.index)
    else:
        welcome()


# --- documents ---------------------------------------------------------------

def sync(model, index: Index, uploads) -> None:
    """Make the index match the uploader: embed new files, forget removed ones."""
    failed = st.session_state.failed
    current = {upload.file_id: upload for upload in uploads}
    for doc_id in [d for d in index.documents if d not in current]:
        index.remove(doc_id)
    for file_id in [f for f in failed if f not in current]:
        del failed[file_id]
    new = [u for file_id, u in current.items() if file_id not in index and file_id not in failed]
    if not new:
        return

    plural = "s" if len(new) > 1 else ""
    with st.status(f"Embedding {len(new)} document{plural}…", expanded=True) as status:
        for upload in new:
            bar = st.progress(0.0, text=f"{upload.name} — reading…")

            def progress(done, total, bar=bar, name=upload.name):
                fraction = min(done / total, 1.0) if total else 0.5
                bar.progress(fraction, text=f"{name} — {done}{f' of {total}' if total else ''} embeddings")

            try:
                doc = embed_document(model, upload.getvalue(), upload.name, doc_id=upload.file_id,
                                     on_progress=progress)
            except Exception as err:  # one bad file shouldn't stop the others
                failed[upload.file_id] = (upload.name, str(err) or type(err).__name__)
                bar.empty()
                st.error(f"**{md(upload.name)}** — {md(str(err) or type(err).__name__)}")
            else:
                index.add(doc)
                bar.progress(1.0, text=f"{ICONS[doc.doc_type]} {upload.name} — {doc.summary} in {doc.seconds:.0f} s")
        done = sum(u.file_id in index for u in new)
        status.update(label=f"Embedded {done} of {len(new)} document{plural}",
                      state="complete" if done == len(new) else "error", expanded=False)


def show_documents(model, index: Index) -> None:
    state = st.session_state
    if len(index) or state.failed:
        left, right = st.columns(2)
        left.metric("Documents", len(index), border=True)
        right.metric("Embeddings", f"{index.size:,}", border=True)
        for name, error in state.failed.values():
            st.markdown(f"⚠️ **{md(name)}**  \n:red[{md(error)}]")
        if len(index):
            with st.expander(f"What was embedded ({len(index)})", expanded=len(index) <= 4):
                for doc in index.documents.values():
                    st.markdown(f"{ICONS[doc.doc_type]} **{md(doc.name)}**  \n"
                                f":gray[{doc.summary} · {doc.seconds:.0f} s]")
        if st.button("Clear all", icon=":material/delete_sweep:", width="stretch"):
            index.clear()
            state.failed.clear()
            state.query_vectors.clear()
            state.uploader += 1
            st.rerun()
    st.divider()
    st.caption(f"EmbeddingGemma 2 on {model.device.type.upper()} · in memory only, nothing is saved")
    if st.get_option("server.address") in ("localhost", "127.0.0.1", "::1"):
        st.caption("🔒 Only this computer can open this app.")
    else:
        st.caption("⚠️ Other computers on your network can open this app. Start it from "
                   "`src/streamlit` to keep it on this computer only.")


def welcome() -> None:
    st.info("Add documents in the sidebar to start. They stay in this app's memory; nothing is written to disk.",
            icon=":material/upload_file:")
    for col, doc_type in zip(st.columns(len(LABELS)), LABELS, strict=True):
        with col.container(border=True):
            st.markdown(f"## {ICONS[doc_type]}\n**{LABELS[doc_type]}**")
            st.caption(" ".join(EXTENSIONS[doc_type]))
            st.caption(f"A match points at {WHERE[doc_type]}.")


# --- search ------------------------------------------------------------------

def search(model, index: Index) -> None:
    present = [t for t in LABELS if any(d.doc_type == t for d in index.documents.values())]
    mode_col, types_col, k_col = st.columns([1.3, 3, 1.2], vertical_alignment="bottom")
    mode = mode_col.segmented_control("Search with", ["Text", "A file"], default="Text", key="mode") or "Text"
    types = types_col.pills("Only these", present, selection_mode="multi", key="types",
                            format_func=lambda t: f"{ICONS[t]} {LABELS[t]}")
    top_k = k_col.select_slider("Results", [5, 10, 20, 50], value=10, key="top_k")

    if mode == "Text":
        text = st.text_input("Search", key="query", icon=":material/search:", label_visibility="collapsed",
                             placeholder="Describe what you're looking for, e.g. “TV and laptop deals”").strip()
        if not text:
            st.caption("Type a query and press Enter. Any language works.")
            return
        query, label = embed_text_query(model, text), f"“{md(text)}”"
    else:
        upload = st.file_uploader("Find content similar to this file", type=UPLOAD_TYPES,
                                  max_upload_size=MAX_UPLOAD_MB, key="query-file")
        if upload is None:
            st.caption("Upload an image, a page, a clip… to find what in your documents is most like it.")
            return
        vectors = st.session_state.query_vectors
        if upload.file_id not in vectors:
            with st.spinner(f"Embedding {upload.name}…"):
                vectors[upload.file_id] = embed_file_query(model, upload.getvalue(), upload.name)
        query, label = vectors[upload.file_id], f"**{md(upload.name)}**"

    hits = index.search(query, top_k=top_k, doc_types=types or None)
    if not hits:
        st.warning("Nothing to search in those types.")
        return
    st.markdown(f"##### {len(hits)} best matches for {label}")
    for start in range(0, len(hits), PER_ROW):
        row = enumerate(hits[start:start + PER_ROW], start + 1)
        for col, (rank, hit) in zip(st.columns(PER_ROW), row, strict=False):  # the last row may be short
            with col:
                result_card(rank, hit)


def result_card(rank: int, hit: Hit) -> None:
    doc = hit.document
    with st.container(border=True):
        if hit.preview:
            st.image(card_image(hit.preview, dark=is_dark()), width="stretch")
        elif hit.excerpt:
            st.code(clip(hit.excerpt, 1500), language=None, wrap_lines=True, height=CARD_TEXT_PX)
        st.markdown(f"**{rank}. {md(doc.name)}**  \n"
                    f":{BADGE[doc.doc_type]}-badge[{ICONS[doc.doc_type]} {LABELS[doc.doc_type]}] **{hit.location}**")
        st.progress(min(max(hit.score, 0.0), 1.0), text=f"Similarity {hit.score:.3f}")
        if doc.doc_type == "audio":
            st.audio(doc.source, format=mime(doc.name, "audio/wav"), start_time=int(hit.start_s or 0))
        view, play = st.columns(2)
        if view.button("View", key=f"view-{rank}", icon=":material/zoom_in:", width="stretch"):
            show_large(hit)
        if doc.doc_type == "video" and play.button(f"Play {clock(moment(hit))}", key=f"play-{rank}",
                                                   icon=":material/play_circle:", width="stretch"):
            play_video(hit)


@st.dialog("Match", width="large")
def show_large(hit: Hit) -> None:
    doc = hit.document
    st.markdown(f"#### {ICONS[doc.doc_type]} {md(doc.name)}\n**{hit.location}** · similarity {hit.score:.3f}")
    if hit.preview:
        st.image(hit.preview, width="stretch")
    if doc.doc_type == "audio":
        st.audio(doc.source, format=mime(doc.name, "audio/wav"), start_time=int(hit.start_s or 0))
    if hit.excerpt and doc.doc_type == "text":
        st.code(hit.excerpt, language=None, wrap_lines=True)
    elif hit.excerpt:
        st.caption("Text on this page")
        st.markdown(md(" ".join(hit.excerpt.split())))


@st.dialog("Play", width="large")
def play_video(hit: Hit) -> None:
    doc = hit.document
    st.markdown(f"#### 🎬 {md(doc.name)}\n**{hit.location}**")
    st.video(doc.source, format=mime(doc.name, "video/mp4"), start_time=int(moment(hit)), autoplay=True)


# --- helpers -----------------------------------------------------------------

@st.cache_data(max_entries=1000, show_spinner=False)
def card_image(preview: bytes, dark: bool) -> bytes:
    """The preview centred in a CARD-sized box, so every card in the grid lines up."""
    image = Image.open(io.BytesIO(preview))
    image.thumbnail(CARD)
    box = Image.new("RGB", CARD, "#262730" if dark else "#f0f2f6")
    box.paste(image, ((CARD[0] - image.width) // 2, (CARD[1] - image.height) // 2))
    out = io.BytesIO()
    box.save(out, format="JPEG", quality=88)
    return out.getvalue()


def is_dark() -> bool:
    return getattr(st.context.theme, "type", None) == "dark"


def moment(hit: Hit) -> float:
    return hit.time_s if hit.time_s is not None else (hit.start_s or 0.0)


def mime(name: str, fallback: str) -> str:
    return mimetypes.guess_type(name)[0] or fallback


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def md(text: str) -> str:
    """Text shown as-is inside Streamlit markdown (file names, page text), not as formatting."""
    return re.sub(r"([\\`*_{}\[\]()#+\-!|$~:<>])", r"\\\1", text)


if __name__ == "__main__":
    main()
