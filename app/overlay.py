"""Always-on-top transparent-ish overlay for live answers."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot, QPoint
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import config


STYLE = """
QWidget#Root {
    background-color: rgba(18, 22, 28, 230);
    border: 1px solid rgba(120, 160, 200, 90);
    border-radius: 14px;
}
QLabel#Title {
    color: #E8EEF6;
    font-size: 15px;
    font-weight: 700;
}
QLabel#Status {
    color: #8FA3B8;
    font-size: 11px;
}
QLabel#Section {
    color: #7EB6FF;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
}
QTextEdit {
    background: rgba(255,255,255,12);
    color: #F2F6FA;
    border: none;
    border-radius: 8px;
    padding: 8px;
    font-size: 12px;
}
QComboBox {
    background: rgba(255,255,255,14);
    color: #F2F6FA;
    border: 1px solid rgba(126, 182, 255, 80);
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}
QComboBox QAbstractItemView {
    background: #1a222c;
    color: #F2F6FA;
    selection-background-color: #3a5f8a;
}
QPushButton {
    background: rgba(126, 182, 255, 40);
    color: #E8EEF6;
    border: 1px solid rgba(126, 182, 255, 80);
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 11px;
}
QPushButton:hover {
    background: rgba(126, 182, 255, 70);
}
QPushButton#Danger {
    background: rgba(220, 90, 90, 40);
    border: 1px solid rgba(220, 90, 90, 90);
}
"""


class OverlayWindow(QWidget):
    transcript_signal = Signal(str)
    answer_signal = Signal(str, str, str)  # question, answer, meta
    status_signal = Signal(str)
    course_signal = Signal(str)  # active course name

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("StudySoft Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(STYLE)
        self.setFixedSize(config.OVERLAY_WIDTH, config.OVERLAY_HEIGHT + 40)
        self.setWindowOpacity(config.OVERLAY_OPACITY)

        self._drag_pos: QPoint | None = None
        self._listening = False
        self._updating_courses = False
        self.on_toggle_listen = None
        self.on_rebuild = None
        self.on_quit = None
        self.on_course_change = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("StudySoft")
        title.setObjectName("Title")
        title.setFont(QFont("Segoe UI Semibold", 14))
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        self.status = QLabel("Idle — pick a course, then Listen")
        self.status.setObjectName("Status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        root.addWidget(self._section("ACTIVE COURSE"))
        self.course_box = QComboBox()
        self.course_box.currentTextChanged.connect(self._course_changed)
        root.addWidget(self.course_box)

        root.addWidget(self._section("LIVE TRANSCRIPT"))
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setMaximumHeight(100)
        root.addWidget(self.transcript)

        root.addWidget(self._section("DETECTED QUESTION"))
        self.question = QTextEdit()
        self.question.setReadOnly(True)
        self.question.setMaximumHeight(64)
        root.addWidget(self.question)

        root.addWidget(self._section("ANSWER FROM ACTIVE COURSE"))
        self.answer = QTextEdit()
        self.answer.setReadOnly(True)
        root.addWidget(self.answer, stretch=1)

        self.meta = QLabel("")
        self.meta.setObjectName("Status")
        self.meta.setWordWrap(True)
        root.addWidget(self.meta)

        buttons = QHBoxLayout()
        self.listen_btn = QPushButton("Start Listening")
        self.listen_btn.clicked.connect(self._toggle)
        rebuild_btn = QPushButton("Rebuild Index")
        rebuild_btn.clicked.connect(self._rebuild)
        quit_btn = QPushButton("Quit")
        quit_btn.setObjectName("Danger")
        quit_btn.clicked.connect(self._quit)
        buttons.addWidget(self.listen_btn)
        buttons.addWidget(rebuild_btn)
        buttons.addWidget(quit_btn)
        root.addLayout(buttons)

        tip = QLabel(
            "Put each course's files in materials/<CourseName>/. "
            "Switch course here, or say the course name on Zoom to auto-switch."
        )
        tip.setObjectName("Status")
        tip.setWordWrap(True)
        root.addWidget(tip)

        self.transcript_signal.connect(self._on_transcript)
        self.answer_signal.connect(self._on_answer)
        self.status_signal.connect(self._on_status)
        self.course_signal.connect(self._on_course)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 24, geo.top() + 40)

    def _section(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("Section")
        return lab

    def set_courses(self, courses: list[str], active: str) -> None:
        self._updating_courses = True
        self.course_box.clear()
        self.course_box.addItems(courses)
        if active in courses:
            self.course_box.setCurrentText(active)
        self._updating_courses = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    def _course_changed(self, name: str) -> None:
        if self._updating_courses or not name:
            return
        if self.on_course_change:
            self.on_course_change(name)

    def _toggle(self) -> None:
        if self.on_toggle_listen:
            self.on_toggle_listen()

    def _rebuild(self) -> None:
        if self.on_rebuild:
            self.on_rebuild()

    def _quit(self) -> None:
        if self.on_quit:
            self.on_quit()
        self.close()

    def set_listening(self, active: bool) -> None:
        self._listening = active
        self.listen_btn.setText("Stop Listening" if active else "Start Listening")

    @Slot(str)
    def _on_transcript(self, text: str) -> None:
        current = self.transcript.toPlainText().strip()
        merged = (current + " " + text).strip()
        self.transcript.setPlainText(merged[-800:])
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())

    @Slot(str, str, str)
    def _on_answer(self, question: str, answer: str, meta: str) -> None:
        if question:
            self.question.setPlainText(question)
        if answer:
            self.answer.setPlainText(answer)
        self.meta.setText(meta)

    @Slot(str)
    def _on_status(self, text: str) -> None:
        self.status.setText(text)

    @Slot(str)
    def _on_course(self, name: str) -> None:
        if name and self.course_box.currentText() != name:
            self._updating_courses = True
            self.course_box.setCurrentText(name)
            self._updating_courses = False
