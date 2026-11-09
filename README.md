# Google Deepmind Embedding Gemma 2

<img src="src/multimodal_search/assets/logo.svg" alt="Multimodal search logo" width="112" align="right">

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/ThivaV/google_deepmind_embeddinggemma2.svg)](https://github.com/ThivaV/google_deepmind_embeddinggemma2/commits)
[![Issues](https://img.shields.io/github/issues/ThivaV/google_deepmind_embeddinggemma2.svg)](https://github.com/ThivaV/google_deepmind_embeddinggemma2/issues)

Multimodal search with Google DeepMind's
[EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2). PDFs, images,
videos, audio and text files are embedded into one 768-dimensional space, stored
in Milvus Lite, and searched with a text query or with another document. Every
hit says where in its document it matched: the page of a PDF, the frame of a
video, the time range of a recording, the lines of a text file.

---

## Layout

| Path | What it holds |
|---|---|
| `notebooks/google_deepmind_embeddinggemma2.ipynb` | Everything: download the model, embed, store, search |
| `src/streamlit/` | Web app: upload documents, search them in the browser |
| `src/customtkinter/` | macOS desktop app: the same, in a window |
| `src/multimodal_search/` | What both apps share: reading documents, embedding, in-memory search |
| `.models/embeddinggemma-2/` | The model, downloaded by the notebook (about 1.5 GB) |
| `.data/bronze/` | The documents to embed |
| `.data/gold/db/` | The Milvus Lite database |

`.data/` and `.models/` stay out of git.

---

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

Put documents in `.data/bronze/` and run the notebook top to bottom. It downloads
the model (public, no token needed), embeds everything in `.data/bronze/`, stores
it in `.data/gold/db/` and runs example searches.

Only one process can have the database open at a time: run `close_db()` in the
notebook before opening it from anywhere else.

---

## Apps

Both apps take documents you pick, embed them in memory and search them. Nothing
is written to disk, and nothing goes into the database. They download the model
into `.models/` on first start if the notebook hasn't already.

```bash
make desktop             # the macOS desktop app (quits when you close its window)
make streamlit-start     # the web app, in the background; opens http://localhost:8501
make streamlit-stop      # stop the web app
make                     # every target: also streamlit-status, -restart and -logs
```

`make streamlit-start STREAMLIT_PORT=8502 OPEN=0` picks another port and skips
opening the browser. The web app's log and PID file go to `logs/`.

**In the browser** (Streamlit). Started by `make`, or by hand from its folder:

```bash
cd src/streamlit
streamlit run app.py
```

Starting it from `src/streamlit` picks up its settings: only this computer can
open it, and Streamlit's usage statistics are off. Uploads can be up to 4 GB each.

**On the desktop** (macOS, CustomTkinter). `make desktop`, or by hand:

```bash
python src/customtkinter/app.py
```

Add files or a folder, then search. Each match has **View**, **Open** and **Show
in Finder**; videos and recordings also have **Play from m:ss**, which opens
QuickTime Player at the matching moment (macOS asks once to allow that).

---

## References

**EmbeddingGemma 2**

- [google/embeddinggemma-2](https://huggingface.co/google/embeddinggemma-2) — the model card on
  Hugging Face: architecture, benchmarks, task prompts and usage.
- [EmbeddingGemma 2 is a best-in-class open model for natively multimodal embeddings](https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/)
  — Google's launch post.
- [Google releases EmbeddingGemma 2](https://lnkd.in/p/eCkQXwiu) — Daniel Han on LinkedIn.

**Unsloth**

- [EmbeddingGemma 2 - Run Locally](https://unsloth.ai/docs/models/embeddinggemma-2) — Unsloth's
  documentation.
- [unsloth/embeddinggemma-2-GGUF](https://huggingface.co/unsloth/embeddinggemma-2-GGUF) — GGUF
  builds of the model on Hugging Face.

**The first EmbeddingGemma**

- [Introducing EmbeddingGemma: The Best-in-Class Open Model for On-Device Embeddings](https://developers.googleblog.com/en/introducing-embeddinggemma/)
  — Google Developers Blog.

---

## Licence

Released under the MIT Licence. Copyright (c) 2026 ThivaV.
See [LICENSE](LICENSE) for the full text.
