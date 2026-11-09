# Google Deepmind Embeddinggemma2

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

## Licence

Released under the MIT Licence. Copyright (c) 2026 ThivaV.
See [LICENSE](LICENSE) for the full text.
