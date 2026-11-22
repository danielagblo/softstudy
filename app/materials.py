"""Load course materials and build a searchable TF-IDF index."""
from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config


SUPPORTED = {".txt", ".md", ".pdf", ".docx"}


@dataclass
class Chunk:
    text: str
    source: str
    chunk_id: int


def _read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _read_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def load_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return _read_txt(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".docx":
        return _read_docx(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def chunk_text(text: str, size: int = config.CHUNK_SIZE, overlap: int = config.CHUNK_OVERLAP) -> list[str]:
    # Prefer paragraph / heading blocks so Q&A hits the right section
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if not paragraphs:
        paragraphs = [re.sub(r"\s+", " ", text).strip()] if text.strip() else []

    units: list[str] = []
    for para in paragraphs:
        para = re.sub(r"[ \t]+", " ", para).strip()
        if len(para) <= size:
            if para:
                units.append(para)
            continue
        # Long paragraph: sliding window
        start = 0
        while start < len(para):
            end = min(len(para), start + size)
            piece = para[start:end].strip()
            if piece:
                units.append(piece)
            if end >= len(para):
                break
            start = max(0, end - overlap)

    return [u for u in units if u]


class MaterialsIndex:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None

    @property
    def ready(self) -> bool:
        return bool(self.chunks) and self.vectorizer is not None and self.matrix is not None

    def build_from_folder(self, folder: Path | None = None) -> int:
        folder = folder or config.MATERIALS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        files = sorted(
            p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED
        )
        chunks: list[Chunk] = []
        for path in files:
            try:
                raw = load_file(path)
            except Exception as exc:  # noqa: BLE001 — keep indexing other files
                print(f"[materials] skip {path.name}: {exc}")
                continue
            for i, piece in enumerate(chunk_text(raw)):
                chunks.append(Chunk(text=piece, source=path.name, chunk_id=i))

        self.chunks = chunks
        if not chunks:
            self.vectorizer = None
            self.matrix = None
            return 0

        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=40000)
        self.matrix = self.vectorizer.fit_transform(c.text for c in chunks)
        return len(chunks)

    def save(self, path: Path | None = None) -> None:
        path = path or config.INDEX_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(
                {"chunks": self.chunks, "vectorizer": self.vectorizer, "matrix": self.matrix},
                f,
            )

    def load(self, path: Path | None = None) -> bool:
        path = path or config.INDEX_PATH
        if not path.exists():
            return False
        with path.open("rb") as f:
            data = pickle.load(f)
        self.chunks = data["chunks"]
        self.vectorizer = data["vectorizer"]
        self.matrix = data["matrix"]
        return self.ready

    def search(self, query: str, top_k: int = config.TOP_K_CHUNKS) -> list[tuple[Chunk, float]]:
        if not self.ready or not query.strip():
            return []
        assert self.vectorizer is not None and self.matrix is not None
        q = self.vectorizer.transform([query])
        scores = cosine_similarity(q, self.matrix).ravel()
        if scores.max() <= 0:
            return []
        idxs = scores.argsort()[::-1][:top_k]
        return [(self.chunks[i], float(scores[i])) for i in idxs if scores[i] > 0.05]


def ensure_index(force_rebuild: bool = False) -> MaterialsIndex:
    index = MaterialsIndex()
    if not force_rebuild and index.load():
        return index
    n = index.build_from_folder()
    if n:
        index.save()
        print(f"[materials] indexed {n} chunks from {config.MATERIALS_DIR}")
    else:
        print(f"[materials] no files found in {config.MATERIALS_DIR}")
    return index
