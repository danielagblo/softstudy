"""Multi-course materials: one folder per course under materials/."""
from __future__ import annotations

import json
import re
from pathlib import Path

import config
from app.materials import SUPPORTED, MaterialsIndex, load_file, chunk_text, Chunk
from app.qa_engine import QAEngine


ACTIVE_PATH = config.DATA_DIR / "active_course.json"


def _slug_ok(name: str) -> bool:
    return bool(name) and name not in {".", ".."} and "/" not in name and "\\" not in name


def list_course_names() -> list[str]:
    root = config.MATERIALS_DIR
    root.mkdir(parents=True, exist_ok=True)
    names = sorted(
        p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    return names


def course_dir(course: str) -> Path:
    if not _slug_ok(course):
        raise ValueError(f"Invalid course name: {course}")
    path = config.MATERIALS_DIR / course
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path_for(course: str) -> Path:
    safe = re.sub(r"[^\w\-]+", "_", course).strip("_") or "course"
    return config.DATA_DIR / f"index_{safe}.pkl"


def ensure_course_folders(defaults: list[str] | None = None) -> list[str]:
    """Create default course folders if none exist yet."""
    existing = list_course_names()
    if existing:
        return existing
    defaults = defaults or [
        "Course_1",
        "Course_2",
        "Course_3",
        "Course_4",
        "Course_5",
    ]
    for name in defaults:
        course_dir(name)
    return list_course_names()


def detect_course_from_text(text: str, courses: list[str]) -> str | None:
    """If transcript mentions a course name, return the best match."""
    if not text or not courses:
        return None
    lower = text.lower()
    # Prefer longer names first to avoid partial collisions
    ranked = sorted(courses, key=lambda c: len(c), reverse=True)
    for name in ranked:
        needle = name.lower().replace("_", " ")
        alt = name.lower()
        if needle in lower or alt in lower:
            return name
        # also match without spaces/underscores
        compact = re.sub(r"[\s_]+", "", needle)
        if len(compact) >= 4 and compact in re.sub(r"[\s_]+", "", lower):
            return name
    return None


class CourseLibrary:
    """Holds per-course indexes and the currently active course."""

    def __init__(self) -> None:
        config.MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        ensure_course_folders()
        self.indexes: dict[str, MaterialsIndex] = {}
        self.active: str = self._load_active() or (list_course_names()[0] if list_course_names() else "Course_1")
        self.reload_all()

    def _load_active(self) -> str | None:
        if not ACTIVE_PATH.exists():
            return None
        try:
            data = json.loads(ACTIVE_PATH.read_text(encoding="utf-8"))
            name = str(data.get("active", "")).strip()
            return name if name in list_course_names() else None
        except Exception:  # noqa: BLE001
            return None

    def _save_active(self) -> None:
        ACTIVE_PATH.write_text(json.dumps({"active": self.active}, indent=2), encoding="utf-8")

    def courses(self) -> list[str]:
        return list_course_names()

    def build_course(self, course: str) -> MaterialsIndex:
        folder = course_dir(course)
        index = MaterialsIndex()
        files = sorted(
            p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED
        )
        chunks: list[Chunk] = []
        for path in files:
            try:
                raw = load_file(path)
            except Exception as exc:  # noqa: BLE001
                print(f"[courses] skip {path}: {exc}")
                continue
            rel = str(path.relative_to(folder))
            for i, piece in enumerate(chunk_text(raw)):
                chunks.append(Chunk(text=piece, source=f"{course}/{rel}", chunk_id=i))
        index.chunks = chunks
        if chunks:
            from sklearn.feature_extraction.text import TfidfVectorizer

            index.vectorizer = TfidfVectorizer(
                stop_words="english", ngram_range=(1, 2), max_features=40000
            )
            index.matrix = index.vectorizer.fit_transform(c.text for c in chunks)
            index.save(index_path_for(course))
        else:
            index.vectorizer = None
            index.matrix = None
        return index

    def reload_all(self, force: bool = False) -> None:
        names = self.courses()
        self.indexes = {}
        for name in names:
            idx = MaterialsIndex()
            path = index_path_for(name)
            if not force and idx.load(path):
                self.indexes[name] = idx
            else:
                self.indexes[name] = self.build_course(name)
        if self.active not in self.indexes and names:
            self.active = names[0]
            self._save_active()

    def set_active(self, course: str) -> MaterialsIndex:
        if course not in self.courses():
            course_dir(course)
            self.indexes[course] = self.build_course(course)
        self.active = course
        self._save_active()
        return self.indexes[course]

    def maybe_auto_switch(self, transcript: str) -> str | None:
        hit = detect_course_from_text(transcript, self.courses())
        if hit and hit != self.active:
            self.set_active(hit)
            return hit
        return None

    def active_index(self) -> MaterialsIndex:
        if self.active not in self.indexes:
            self.indexes[self.active] = self.build_course(self.active)
        return self.indexes[self.active]

    def active_qa(self) -> QAEngine:
        return QAEngine(self.active_index())

    def status(self) -> dict:
        return {
            "active": self.active,
            "courses": [
                {
                    "name": name,
                    "chunks": len(self.indexes.get(name, MaterialsIndex()).chunks),
                    "folder": str(course_dir(name)),
                }
                for name in self.courses()
            ],
            "materials_dir": str(config.MATERIALS_DIR),
        }
