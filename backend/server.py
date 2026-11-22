"""
StudySoft backend API — multi-course materials + live Q&A.
Run:  python -m backend.server
API:  http://127.0.0.1:8000
Docs: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from app.courses import CourseLibrary, course_dir
from app.materials import SUPPORTED
from app.qa_engine import extract_question

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _safe_filename(name: str) -> str:
    cleaned = Path(name).name.strip().replace("\x00", "")
    return cleaned or "upload.bin"


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    course: str | None = None


class TranscriptRequest(BaseModel):
    text: str = Field(..., min_length=1)


class CourseSelectRequest(BaseModel):
    course: str = Field(..., min_length=1)


class CreateCourseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
state: dict[str, Any] = {
    "library": None,
    "qa": None,
    "recent": [],
}


def _lib() -> CourseLibrary:
    return state["library"]


def _refresh_qa() -> None:
    state["qa"] = _lib().active_qa()
    state["recent"] = []


def _boot() -> None:
    config.MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    library = CourseLibrary()
    state["library"] = library
    _refresh_qa()
    print(f"[backend] ready — active={library.active} courses={library.courses()}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _boot()
    yield


app = FastAPI(
    title="StudySoft Backend",
    description="Multi-course Q&A API for the StudySoft overlay",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, Any]:
    lib = _lib()
    info = lib.status()
    info["clients"] = len(manager.active)
    return info


@app.get("/courses")
def courses() -> dict[str, Any]:
    lib = _lib()
    return {"active": lib.active, "courses": lib.courses(), "detail": lib.status()["courses"]}


@app.post("/courses")
async def create_course(body: CreateCourseRequest) -> dict[str, Any]:
    name = body.name.strip()
    course_dir(name)
    lib = _lib()
    lib.reload_all(force=True)
    await manager.broadcast({"type": "status", "data": lib.status()})
    return {"ok": True, "courses": lib.courses(), "active": lib.active}


@app.post("/courses/active")
async def set_active_course(body: CourseSelectRequest) -> dict[str, Any]:
    lib = _lib()
    lib.set_active(body.course.strip())
    _refresh_qa()
    payload = lib.status()
    await manager.broadcast({"type": "course", "data": {"active": lib.active, **payload}})
    return {"ok": True, "active": lib.active, "chunks": len(lib.active_index().chunks)}


@app.post("/rebuild")
async def rebuild() -> dict[str, Any]:
    lib = _lib()
    lib.reload_all(force=True)
    _refresh_qa()
    payload = lib.status()
    await manager.broadcast({"type": "status", "data": payload})
    return {"ok": True, **payload}


@app.post("/upload")
async def upload_materials(
    files: list[UploadFile] = File(...),
    course: str = Form(...),
) -> dict[str, Any]:
    """Publish files into a specific course folder and rebuild that course index."""
    course = course.strip()
    folder = course_dir(course)
    saved: list[str] = []
    skipped: list[str] = []

    for upload in files:
        original = upload.filename or "upload.bin"
        name = _safe_filename(original)
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED:
            skipped.append(original)
            continue
        dest = folder / name
        if dest.exists():
            stem, ext = dest.stem, dest.suffix
            n = 2
            while True:
                candidate = folder / f"{stem}_{n}{ext}"
                if not candidate.exists():
                    dest = candidate
                    break
                n += 1
        dest.write_bytes(await upload.read())
        saved.append(dest.name)

    lib = _lib()
    # Rebuild after files land, then activate the named course
    lib.reload_all(force=True)
    lib.set_active(course)
    _refresh_qa()
    result = {
        "ok": True,
        "course": course,
        "saved": saved,
        "skipped": skipped,
        "accepted_types": sorted(SUPPORTED),
        **lib.status(),
    }
    await manager.broadcast({"type": "status", "data": result})
    return result


@app.get("/materials")
def list_materials(course: str | None = None) -> dict[str, Any]:
    lib = _lib()
    course = (course or lib.active).strip()
    folder = course_dir(course)
    files = sorted(
        str(p.relative_to(folder))
        for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED
    )
    return {"course": course, "files": files, "count": len(files), "folder": str(folder)}


@app.post("/ask")
async def ask(body: AskRequest) -> dict[str, Any]:
    lib = _lib()
    if body.course and body.course != lib.active:
        lib.set_active(body.course)
        _refresh_qa()
    result = state["qa"].answer(body.question.strip())
    payload = {
        "course": lib.active,
        "question": result.question,
        "answer": result.answer,
        "sources": result.sources,
        "scores": result.scores,
        "mode": result.mode,
    }
    await manager.broadcast({"type": "answer", "data": payload})
    return payload


@app.post("/transcript")
async def transcript(body: TranscriptRequest) -> dict[str, Any]:
    text = body.text.strip()
    lib = _lib()

    switched = lib.maybe_auto_switch(text)
    if switched:
        _refresh_qa()
        await manager.broadcast({"type": "course", "data": {"active": switched, **lib.status()}})

    recent: list[str] = state["recent"]
    recent.append(text)
    state["recent"] = recent[-8:]
    window = " ".join(state["recent"])

    await manager.broadcast({"type": "transcript", "data": {"text": text, "course": lib.active}})

    question = extract_question(window)
    if not question:
        return {"transcript": text, "course": lib.active, "switched": switched, "question": None, "answer": None}

    result = state["qa"].answer(question)
    if result.mode == "empty" and not result.answer:
        return {
            "transcript": text,
            "course": lib.active,
            "switched": switched,
            "question": question,
            "answer": None,
        }

    answer_payload = {
        "course": lib.active,
        "question": result.question,
        "answer": result.answer,
        "sources": result.sources,
        "scores": result.scores,
        "mode": result.mode,
    }
    await manager.broadcast({"type": "answer", "data": answer_payload})
    return {
        "transcript": text,
        "course": lib.active,
        "switched": switched,
        "question": question,
        "answer": answer_payload,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    lib = _lib()
    await ws.send_json({"type": "hello", "data": lib.status()})
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            data = msg.get("data") or {}
            if kind == "set_course":
                course = str(data.get("course", "")).strip()
                if course:
                    lib.set_active(course)
                    _refresh_qa()
                    await manager.broadcast({"type": "course", "data": {"active": lib.active, **lib.status()}})
            elif kind == "ask":
                question = str(data.get("question", "")).strip()
                if question:
                    result = state["qa"].answer(question)
                    await manager.broadcast(
                        {
                            "type": "answer",
                            "data": {
                                "course": lib.active,
                                "question": result.question,
                                "answer": result.answer,
                                "sources": result.sources,
                                "scores": result.scores,
                                "mode": result.mode,
                            },
                        }
                    )
            elif kind == "transcript":
                text = str(data.get("text", "")).strip()
                if text:
                    switched = lib.maybe_auto_switch(text)
                    if switched:
                        _refresh_qa()
                        await manager.broadcast(
                            {"type": "course", "data": {"active": switched, **lib.status()}}
                        )
                    recent: list[str] = state["recent"]
                    recent.append(text)
                    state["recent"] = recent[-8:]
                    await manager.broadcast(
                        {"type": "transcript", "data": {"text": text, "course": lib.active}}
                    )
                    question = extract_question(" ".join(state["recent"]))
                    if question:
                        result = state["qa"].answer(question)
                        if not (result.mode == "empty" and not result.answer):
                            await manager.broadcast(
                                {
                                    "type": "answer",
                                    "data": {
                                        "course": lib.active,
                                        "question": result.question,
                                        "answer": result.answer,
                                        "sources": result.sources,
                                        "scores": result.scores,
                                        "mode": result.mode,
                                    },
                                }
                            )
            elif kind == "rebuild":
                lib.reload_all(force=True)
                _refresh_qa()
                await manager.broadcast({"type": "status", "data": lib.status()})
            elif kind == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:  # noqa: BLE001
        manager.disconnect(ws)


def main() -> None:
    import uvicorn

    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
