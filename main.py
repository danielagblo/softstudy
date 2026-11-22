"""
StudySoft — listen to Zoom/Meet tutorials and answer questions from the active course.
"""
from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication

import config
from app.audio_listener import AudioListener
from app.courses import CourseLibrary
from app.overlay import OverlayWindow
from app.qa_engine import extract_question
from app.transcriber import Transcriber


class StudySoftApp:
    def __init__(self) -> None:
        config.MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)

        self.qt = QApplication(sys.argv)
        self.qt.setApplicationName("StudySoft")

        self.library = CourseLibrary()
        self.qa = self.library.active_qa()

        self.overlay = OverlayWindow()
        self.overlay.on_toggle_listen = self.toggle_listen
        self.overlay.on_rebuild = self.rebuild_index
        self.overlay.on_quit = self.shutdown
        self.overlay.on_course_change = self.switch_course
        self.overlay.set_courses(self.library.courses(), self.library.active)

        self.transcriber = Transcriber(on_text=self.on_transcript)
        self.listener = AudioListener(on_chunk=self.transcriber.submit)

        self._listening = False
        self._recent_text: list[str] = []

        n = len(self.library.active_index().chunks)
        self.overlay.status_signal.emit(
            f"Active: {self.library.active} — {n} chunks. Switch course for each Zoom class."
        )

    def switch_course(self, name: str) -> None:
        self.library.set_active(name)
        self.qa = self.library.active_qa()
        self._recent_text = []
        n = len(self.library.active_index().chunks)
        self.overlay.course_signal.emit(name)
        self.overlay.status_signal.emit(f"Switched to {name} — {n} chunks")

    def toggle_listen(self) -> None:
        if self._listening:
            self.stop_listen()
        else:
            self.start_listen()

    def start_listen(self) -> None:
        try:
            if not self.transcriber.ready:
                self.overlay.status_signal.emit("Loading Whisper model (first run may download)...")
                QApplication.processEvents()
                self.transcriber.load()
            self.transcriber.start()
            self.listener.start()
            self._listening = True
            self.overlay.set_listening(True)
            self.overlay.status_signal.emit(
                f"Listening [{self.library.active}] ({self.listener.mode}): {self.listener.device_name}"
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.overlay.status_signal.emit(f"Could not start listening: {exc}")

    def stop_listen(self) -> None:
        self.listener.stop()
        self._listening = False
        self.overlay.set_listening(False)
        self.overlay.status_signal.emit(f"Stopped — active course: {self.library.active}")

    def rebuild_index(self) -> None:
        self.overlay.status_signal.emit(f"Rebuilding index for {self.library.active}...")
        QApplication.processEvents()
        self.library.reload_all(force=True)
        self.qa = self.library.active_qa()
        self.overlay.set_courses(self.library.courses(), self.library.active)
        n = len(self.library.active_index().chunks)
        self.overlay.status_signal.emit(f"{self.library.active} rebuilt — {n} chunks")

    def on_transcript(self, text: str) -> None:
        print(f"[transcript] {text}")
        self.overlay.transcript_signal.emit(text)

        switched = self.library.maybe_auto_switch(text)
        if switched:
            self.qa = self.library.active_qa()
            self.overlay.course_signal.emit(switched)
            self.overlay.status_signal.emit(f"Auto-switched to {switched}")
            self._recent_text = []

        self._recent_text.append(text)
        self._recent_text = self._recent_text[-6:]
        window = " ".join(self._recent_text)
        question = extract_question(window)
        if not question:
            return
        result = self.qa.answer(question)
        if result.mode == "empty" and not result.answer:
            return
        sources = ", ".join(dict.fromkeys(result.sources)) if result.sources else "—"
        meta = f"Course: {self.library.active} | Mode: {result.mode} | Sources: {sources}"
        self.overlay.answer_signal.emit(result.question, result.answer, meta)

    def shutdown(self) -> None:
        self.stop_listen()
        self.transcriber.stop()
        self.qt.quit()

    def run(self) -> int:
        self.overlay.show()
        return self.qt.exec()


def main() -> None:
    app = StudySoftApp()
    raise SystemExit(app.run())


if __name__ == "__main__":
    main()
