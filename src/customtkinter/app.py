"""Multimodal search with EmbeddingGemma 2 -- a macOS desktop app.

Add PDFs, images, videos, audio and text files. They are embedded in memory -- nothing is
written to disk -- and searched by meaning. Every match says where it is (the page, the
video frame and moment, the time range, the lines) with a preview, and buttons to open the
file, show it in Finder, or play a video or recording from the matching moment.

    python src/customtkinter/app.py
"""

from __future__ import annotations

import io
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

sys.path.append(str(Path(__file__).resolve().parents[1]))  # src/, for the shared package
from multimodal_search import ALL_EXTENSIONS, EXTENSIONS, LABELS, LOGO_PNG, clock, doc_type_for  # noqa: E402

# multimodal_search.engine (torch and the model) is imported on a worker thread instead,
# so the window opens straight away.

TYPE_COLORS = {"pdf": "#dc2626", "image": "#2563eb", "video": "#7c3aed", "audio": "#ea580c", "text": "#16a34a"}
FILTERS = {"All": None, "PDF": "pdf", "Images": "image", "Video": "video", "Audio": "audio", "Text": "text"}
MUTED = ("gray40", "gray65")
CARD_BG = ("gray97", "gray17")
THUMB = (220, 150)                                    # result preview box
QUICKTIME = {".mp4", ".mov", ".m4v", ".mp3", ".m4a", ".aac", ".wav"}  # what QuickTime Player plays
FILE_TYPES = [("Documents", " ".join(f"*{e}" for e in ALL_EXTENSIONS))] + [
    (LABELS[t], " ".join(f"*{e}" for e in exts)) for t, exts in EXTENSIONS.items()]


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.title("Multimodal Search — EmbeddingGemma 2")
        self.geometry("1320x860")
        self.minsize(1040, 660)
        self.icon = tk.PhotoImage(file=str(LOGO_PNG))
        self.iconphoto(True, self.icon)  # on macOS this is the app's icon in the Dock

        self.engine = self.model = self.index = None
        self.events: queue.Queue = queue.Queue()   # worker threads -> this (UI) thread
        self.jobs: queue.Queue = queue.Queue()     # paths waiting to be embedded
        self.model_ready = threading.Event()
        self.rows: dict[str, DocumentRow] = {}     # path -> its row in the sidebar
        self.cancelled: set[str] = set()           # removed while waiting or embedding
        self.failed: set[str] = set()              # couldn't be read
        self.query: tuple[str, object] | None = None  # (label, vector) of the last search
        self.search_id = 0
        self.cards: list[ResultCard] = []

        self._build_sidebar()
        self._build_main()
        self.bind("<Command-o>", lambda _e: self.add_files())
        self.bind("<Command-f>", lambda _e: self.entry.focus_set())
        threading.Thread(target=self._load_model, daemon=True).start()
        threading.Thread(target=self._embed_worker, daemon=True).start()
        self.after(100, self._poll)

    # --- layout --------------------------------------------------------------

    def _build_sidebar(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, width=330, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(side, text="Documents", font=ctk.CTkFont(size=20, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=18, pady=(22, 10))
        buttons = ctk.CTkFrame(side, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=14)
        buttons.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(buttons, text="Add files…", command=self.add_files).grid(row=0, column=0, sticky="ew", padx=4)
        ctk.CTkButton(buttons, text="Add folder…", command=self.add_folder, fg_color="transparent",
                      border_width=1, text_color=("gray10", "gray90")).grid(row=0, column=1, sticky="ew", padx=4)

        self.doc_list = ctk.CTkScrollableFrame(side, fg_color="transparent")
        self.doc_list.grid(row=2, column=0, sticky="nsew", padx=8, pady=10)
        self.doc_list.grid_columnconfigure(0, weight=1)
        self.empty_docs = ctk.CTkLabel(
            self.doc_list, text="No documents yet.\n\nAdd PDFs, images, videos,\naudio or text files.",
            text_color=MUTED, justify="center")
        self.empty_docs.grid(row=0, column=0, pady=40)

        footer = ctk.CTkFrame(side, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)
        self.totals = ctk.CTkLabel(footer, text="", anchor="w", text_color=MUTED)
        self.totals.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(footer, text="Clear all", width=84, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.clear).grid(row=0, column=1)
        self.model_status = ctk.CTkLabel(footer, text="Loading EmbeddingGemma 2…", anchor="w",
                                         text_color=MUTED, font=ctk.CTkFont(size=12))
        self.model_status.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 2))
        self.model_bar = ctk.CTkProgressBar(footer, mode="indeterminate", height=6)
        self.model_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.model_bar.start()

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=26, pady=(20, 12))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)

        head = ctk.CTkFrame(main, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        head.grid_columnconfigure(1, weight=1)
        self.logo = ctk.CTkImage(light_image=Image.open(LOGO_PNG), size=(60, 60))
        ctk.CTkLabel(head, image=self.logo, text="").grid(row=0, column=0, rowspan=2, padx=(0, 14))
        ctk.CTkLabel(head, text="Multimodal search", font=ctk.CTkFont(size=28, weight="bold"), anchor="w").grid(
            row=0, column=1, sticky="sw")
        ctk.CTkLabel(head, anchor="w", text_color=MUTED,
                     text="Search PDFs, images, videos, audio and text by meaning with Google DeepMind's "
                          "EmbeddingGemma 2. Everything stays in memory.").grid(row=1, column=1, sticky="nw")

        bar = ctk.CTkFrame(main, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(bar, height=40, font=ctk.CTkFont(size=15),
                                  placeholder_text="Describe what you're looking for, e.g. “TV and laptop deals”")
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda _e: self.search())
        ctk.CTkButton(bar, text="Search", width=96, height=40, command=self.search).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(bar, text="Similar to a file…", width=150, height=40, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.search_with_file).grid(row=0, column=2, padx=(8, 0))

        options = ctk.CTkFrame(main, fg_color="transparent")
        options.grid(row=3, column=0, sticky="ew", pady=(12, 8))
        options.grid_columnconfigure(1, weight=1)
        self.filter = ctk.CTkSegmentedButton(options, values=list(FILTERS), command=lambda _v: self.rerun_search())
        self.filter.set("All")
        self.filter.grid(row=0, column=0, sticky="w")
        self.status = ctk.CTkLabel(options, text="", text_color=MUTED, anchor="w")
        self.status.grid(row=0, column=1, sticky="ew", padx=16)
        ctk.CTkLabel(options, text="Results", text_color=MUTED).grid(row=0, column=2, padx=(0, 6))
        self.top_k = ctk.CTkOptionMenu(options, values=["5", "10", "20", "50"], width=72,
                                       command=lambda _v: self.rerun_search())
        self.top_k.set("10")
        self.top_k.grid(row=0, column=3)

        self.results = ctk.CTkScrollableFrame(main, fg_color="transparent")
        self.results.grid(row=4, column=0, sticky="nsew")
        self.results.grid_columnconfigure(0, weight=1)
        self._hint("Add documents on the left, then search.\n\nEvery match says where it is: the page of a PDF, "
                   "the frame and moment of a video,\nthe time range of a recording, the lines of a text file.")

    def _hint(self, text: str) -> None:
        for child in self.results.winfo_children():
            child.destroy()
        self.cards = []
        ctk.CTkLabel(self.results, text=text, text_color=MUTED, justify="center").grid(row=0, column=0, pady=80)

    # --- documents -----------------------------------------------------------

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(parent=self, title="Add documents", filetypes=FILE_TYPES)
        self.add_paths(paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self, title="Add every supported file in a folder")
        if folder:
            self.add_paths(sorted(str(p) for p in Path(folder).rglob("*")
                                  if p.is_file() and not p.name.startswith(".") and doc_type_for(p)))

    def add_paths(self, paths) -> None:
        for path in map(str, paths):
            if path in self.rows or not doc_type_for(path):
                continue
            self.cancelled.discard(path)
            self.empty_docs.grid_remove()
            row = DocumentRow(self.doc_list, self, path)
            row.grid(row=len(self.rows) + 1, column=0, sticky="ew", pady=3)
            self.rows[path] = row
            self.jobs.put(path)
        self._update_totals()

    def remove(self, path: str) -> None:
        row = self.rows.pop(path, None)
        if row:
            row.destroy()
        self.failed.discard(path)
        if self.index is not None and path in self.index:
            self.index.remove(path)
            self.rerun_search()
        else:
            self.cancelled.add(path)  # still waiting or embedding: drop it when it's done
        if not self.rows:
            self.empty_docs.grid()
        self._update_totals()

    def clear(self) -> None:
        for path in list(self.rows):
            self.remove(path)
        self.search_id += 1  # drop results still on their way from searches started above
        self.query = None
        self._hint("Add documents on the left, then search.")
        self.status.configure(text="")

    def _update_totals(self) -> None:
        ready = len(self.index) if self.index is not None else 0
        failed = len(self.failed)
        waiting = len(self.rows) - ready - failed
        parts = [f"{ready} document{'s' * (ready != 1)} · {self.index.size:,} embeddings"] if ready else []
        parts += [f"{waiting} to embed"] if waiting > 0 else []
        parts += [f"{failed} failed"] if failed else []
        self.totals.configure(text=" · ".join(parts))

    # --- search --------------------------------------------------------------

    def search(self) -> None:
        text = self.entry.get().strip()
        if text and self._can_search():
            self._start_search(f"“{text}”", lambda: self.engine.embed_text_query(self.model, text))

    def search_with_file(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Find content similar to a file", filetypes=FILE_TYPES)
        if path:
            self.search_with_path(path)

    def search_with_path(self, path: str) -> None:
        if self._can_search():
            name = Path(path).name
            self._start_search(name, lambda: self.engine.embed_file_query(self.model, Path(path), name))

    def rerun_search(self) -> None:
        """Same query, new filters or documents: no need to embed the query again."""
        if self.query and self.index is not None and len(self.index):
            label, vector = self.query
            self._start_search(label, lambda: vector)

    def _can_search(self) -> bool:
        if not self.model_ready.is_set():
            self.status.configure(text="Still loading the model…")
            return False
        if not len(self.index):
            self.status.configure(text="Add documents first: nothing has been embedded yet.")
            return False
        return True

    def _start_search(self, label: str, make_vector) -> None:
        self.search_id += 1
        search_id, doc_type = self.search_id, FILTERS[self.filter.get()]
        top_k = int(self.top_k.get())
        self.status.configure(text="Searching…")

        def run():
            try:
                vector = make_vector()
                hits = self.index.search(vector, top_k=top_k, doc_types=[doc_type] if doc_type else None)
                self.events.put(("results", search_id, label, vector, hits))
            except Exception as err:
                self.events.put(("search_failed", search_id, f"{type(err).__name__}: {err}"))

        threading.Thread(target=run, daemon=True).start()

    def _show_results(self, label: str, hits) -> None:
        for child in self.results.winfo_children():
            child.destroy()
        self.cards = []
        if not hits:
            self._hint("No matches in those types.")
        for rank, hit in enumerate(hits, 1):
            card = ResultCard(self.results, self, rank, hit)
            card.grid(row=rank, column=0, sticky="ew", pady=6, padx=(0, 8))
            self.cards.append(card)
        self.status.configure(text=f"{len(hits)} best matches for {label}")
        self.results._parent_canvas.yview_moveto(0)

    # --- worker threads and their events --------------------------------------

    def _load_model(self) -> None:
        try:
            from multimodal_search import engine

            self.events.put(("model_ready", engine, engine.load_model()))
        except Exception as err:
            self.events.put(("model_failed", f"{type(err).__name__}: {err}"))

    def _embed_worker(self) -> None:
        self.model_ready.wait()
        while True:
            path = self.jobs.get()
            if path in self.cancelled:
                continue
            self.events.put(("started", path))
            try:
                doc = self.engine.embed_document(
                    self.model, Path(path), Path(path).name, doc_id=path,
                    on_progress=lambda done, total, p=path: self.events.put(("progress", p, done, total)))
                self.events.put(("embedded", path, doc))
            except Exception as err:
                self.events.put(("failed", path, str(err) or type(err).__name__))

    def _poll(self) -> None:
        try:
            while True:
                self._handle(*self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _handle(self, kind: str, *args) -> None:
        if kind == "model_ready":
            self.engine, self.model = args
            self.index = self.engine.Index()
            self.model_bar.stop()
            self.model_bar.grid_remove()
            self.model_status.configure(text=f"EmbeddingGemma 2 · {self.model.device.type.upper()} · in memory only")
            self.model_ready.set()
        elif kind == "model_failed":
            self.model_bar.stop()
            self.model_status.configure(text=f"Couldn't load the model: {args[0]}", text_color="#dc2626")
        elif kind in ("started", "progress", "failed") and args[0] in self.rows:
            row = self.rows[args[0]]
            if kind == "started":
                row.embedding()
            elif kind == "progress":
                row.progress(*args[1:])
            else:
                row.failed(args[1])
                self.failed.add(args[0])
                self._update_totals()
        elif kind == "embedded":
            path, doc = args
            if path in self.cancelled or path not in self.rows:
                return
            self.index.add(doc)
            self.rows[path].done(doc)
            self._update_totals()
            self.rerun_search()
        elif kind == "results" and args[0] == self.search_id:
            _, label, vector, hits = args
            self.query = (label, vector)
            self._show_results(label, hits)
        elif kind == "search_failed" and args[0] == self.search_id:
            self.status.configure(text=f"Search failed: {args[1]}")


class DocumentRow(ctk.CTkFrame):
    """A document in the sidebar: its type, name, and how embedding it is going."""

    def __init__(self, master, app: App, path: str) -> None:
        super().__init__(master, corner_radius=10, fg_color=CARD_BG)
        self.grid_columnconfigure(1, weight=1)
        doc_type = doc_type_for(path)
        Badge(self, doc_type).grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10, sticky="n")
        ctk.CTkLabel(self, text=shorten(Path(path).name, 30), anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=1, sticky="ew", pady=(8, 0))
        self.note = ctk.CTkLabel(self, text="Waiting…", anchor="w", text_color=MUTED, font=ctk.CTkFont(size=12))
        self.note.grid(row=1, column=1, sticky="ew", pady=(0, 2))
        self.bar = ctk.CTkProgressBar(self, height=4)
        self.bar.set(0)
        ctk.CTkButton(self, text="✕", width=26, height=26, fg_color="transparent", text_color=MUTED,
                      hover_color=("gray85", "gray25"), command=lambda: app.remove(path)).grid(
            row=0, column=2, rowspan=2, padx=(4, 8))

    def embedding(self) -> None:
        self.note.configure(text="Embedding…")
        self.bar.grid(row=2, column=1, sticky="ew", pady=(0, 10))

    def progress(self, done: int, total: int | None) -> None:
        self.bar.set(min(done / total, 1.0) if total else 0.5)
        self.note.configure(text=f"Embedding {done}{f' of {total}' if total else ''}…")

    def done(self, doc) -> None:
        self.bar.grid_remove()
        self.note.configure(text=f"{doc.summary} · {doc.seconds:.0f} s")

    def failed(self, error: str) -> None:
        self.bar.grid_remove()
        self.note.configure(text=f"Couldn't read it: {shorten(error, 60)}", text_color="#dc2626")


class ResultCard(ctk.CTkFrame):
    """One match: preview, file, where in it, how close, and what you can do with it."""

    def __init__(self, master, app: App, rank: int, hit) -> None:
        super().__init__(master, corner_radius=14, fg_color=CARD_BG)
        self.hit, doc = hit, hit.document
        self.grid_columnconfigure(1, weight=1)

        box = ctk.CTkFrame(self, width=THUMB[0], height=THUMB[1], corner_radius=10, fg_color=("gray90", "gray22"))
        box.grid(row=0, column=0, rowspan=5, padx=14, pady=14)
        box.grid_propagate(False)
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(0, weight=1)
        if hit.preview:
            self.image = thumbnail(hit.preview, THUMB)
            ctk.CTkLabel(box, image=self.image, text="").grid(row=0, column=0)
        else:
            ctk.CTkLabel(box, text=shorten(" ".join((hit.excerpt or "").split()), 160), wraplength=THUMB[0] - 24,
                         justify="left", text_color=MUTED, font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=10)

        ctk.CTkLabel(self, text=f"{rank}. {doc.name}", anchor="w", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=1, sticky="ew", pady=(16, 2), padx=(0, 16))
        where = ctk.CTkFrame(self, fg_color="transparent")
        where.grid(row=1, column=1, sticky="w")
        Badge(where, doc.doc_type).grid(row=0, column=0)
        ctk.CTkLabel(where, text=hit.location, font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=1, padx=8)

        score = ctk.CTkFrame(self, fg_color="transparent")
        score.grid(row=2, column=1, sticky="w", pady=(8, 0))
        bar = ctk.CTkProgressBar(score, width=220, height=8, progress_color=TYPE_COLORS[doc.doc_type])
        bar.set(min(max(hit.score, 0.0), 1.0))
        bar.grid(row=0, column=0)
        ctk.CTkLabel(score, text=f"similarity {hit.score:.3f}", text_color=MUTED).grid(row=0, column=1, padx=10)

        if hit.excerpt and doc.doc_type == "pdf":
            ctk.CTkLabel(self, text=shorten(" ".join(hit.excerpt.split()), 220), anchor="w", justify="left",
                         wraplength=640, text_color=MUTED, font=ctk.CTkFont(size=12)).grid(
                row=3, column=1, sticky="ew", pady=(6, 0), padx=(0, 16))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=1, sticky="w", pady=(10, 14))
        buttons = [("View", lambda: PreviewWindow(app, hit))]
        if doc.doc_type in ("video", "audio"):
            at = hit.time_s if hit.time_s is not None else (hit.start_s or 0)
            buttons.append((f"▶  Play from {clock(at)}", lambda: play_from(doc.path, at)))
        buttons += [("Open", lambda: open_file(doc.path)), ("Show in Finder", lambda: reveal(doc.path))]
        for i, (text, command) in enumerate(buttons):
            ctk.CTkButton(actions, text=text, command=command, height=30, width=0,
                          **({} if i == 0 else {"fg_color": "transparent", "border_width": 1,
                                                 "text_color": ("gray10", "gray90")})).grid(row=0, column=i, padx=(0, 8))


class PreviewWindow(ctk.CTkToplevel):
    """A bigger look at a match: the page, frame, image or waveform, and its text."""

    def __init__(self, app: App, hit) -> None:
        super().__init__(app)
        doc = hit.document
        self.title(f"{doc.name} — {hit.location}")
        self.geometry("980x820")
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=doc.name, font=ctk.CTkFont(size=18, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(18, 0))
        ctk.CTkLabel(self, text=f"{LABELS[doc.doc_type]} · {hit.location} · similarity {hit.score:.3f}",
                     text_color=MUTED, anchor="w").grid(row=1, column=0, sticky="ew", padx=20, pady=(2, 12))
        row = 2
        if hit.preview:
            self.image = thumbnail(hit.preview, (940, 560 if hit.excerpt else 700))
            ctk.CTkLabel(self, image=self.image, text="").grid(row=row, column=0, padx=20)
            row += 1
        if hit.excerpt:
            self.grid_rowconfigure(row, weight=1)
            text = ctk.CTkTextbox(self, wrap="word", font=ctk.CTkFont(size=13))
            text.insert("1.0", hit.excerpt if doc.doc_type == "text" else " ".join(hit.excerpt.split()))
            text.configure(state="disabled")
            text.grid(row=row, column=0, sticky="nsew", padx=20, pady=(12, 20))
        self.after(50, self.lift)


class Badge(ctk.CTkLabel):
    def __init__(self, master, doc_type: str) -> None:
        super().__init__(master, text=LABELS[doc_type].upper(), fg_color=TYPE_COLORS[doc_type], text_color="white",
                         corner_radius=6, width=56, height=22, font=ctk.CTkFont(size=11, weight="bold"))


# --- helpers ------------------------------------------------------------------

def thumbnail(preview: bytes, box: tuple[int, int]) -> ctk.CTkImage:
    """A preview scaled to fit `box`, kept sharp on Retina screens."""
    image = Image.open(io.BytesIO(preview))
    image.thumbnail((box[0] * 2, box[1] * 2))  # twice the box: sharp at Retina density
    scale = min(box[0] / image.width, box[1] / image.height, 1.0)  # fit the box, never enlarge
    return ctk.CTkImage(light_image=image, dark_image=image, size=(round(image.width * scale), round(image.height * scale)))


def shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def open_file(path: Path) -> None:
    subprocess.Popen(["open", str(path)])


def reveal(path: Path) -> None:
    subprocess.Popen(["open", "-R", str(path)])


def play_from(path: Path, seconds: float) -> None:
    """Open the file in QuickTime Player at the matching moment (the first time, macOS asks
    to let this app control QuickTime Player). Other formats just open normally."""
    if path.suffix.lower() not in QUICKTIME:
        open_file(path)
        return
    script = ["on run argv", 'tell application "QuickTime Player"', "activate",
              "open POSIX file (item 1 of argv)",
              "set current time of front document to (item 2 of argv as integer)",
              "play front document", "end tell", "end run"]
    args = ["osascript", *[part for line in script for part in ("-e", line)], str(path), str(int(seconds))]

    def run():
        if subprocess.run(args, capture_output=True).returncode != 0:
            open_file(path)

    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
