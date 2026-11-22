"""Detect tutorial questions and answer them from course materials."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

from app.materials import MaterialsIndex

load_dotenv()

QUESTION_HINTS = re.compile(
    r"\b("
    r"what|why|how|when|where|which|who|whom|whose|"
    r"define|explain|describe|compare|contrast|calculate|"
    r"solve|find|list|name|give|difference|meaning|"
    r"is|are|can|could|would|should|does|do|did"
    r")\b",
    re.IGNORECASE,
)

FILLER = re.compile(
    r"\b(um+|uh+|you know|like|basically|actually|so+|okay|alright)\b",
    re.IGNORECASE,
)


@dataclass
class AnswerResult:
    question: str
    answer: str
    sources: list[str]
    scores: list[float]
    mode: str  # "passages" | "openai" | "empty"


def looks_like_question(text: str) -> bool:
    cleaned = FILLER.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 12:
        return False
    if "?" in cleaned:
        return True
    # spoken questions often omit "?"
    if QUESTION_HINTS.search(cleaned) and len(cleaned.split()) >= 4:
        # Prefer interrogative / instructional openings
        lower = cleaned.lower()
        starters = (
            "what", "why", "how", "when", "where", "which", "who",
            "define", "explain", "describe", "compare", "calculate",
            "solve", "find", "list", "name", "give", "can you",
            "could you", "would you", "is there", "are there",
            "what is", "what are", "what does", "how do", "how does",
        )
        return any(lower.startswith(s) or f" {s} " in f" {lower} " for s in starters[:18]) or any(
            s in lower for s in ("what is", "what are", "how do", "how does", "explain", "define", "calculate")
        )
    return False


def extract_question(transcript: str) -> str | None:
    """Pull the most recent question-like sentence from a transcript slice."""
    text = re.sub(r"\s+", " ", transcript).strip()
    if not text:
        return None
    # Split on sentence-ish boundaries
    parts = re.split(r"(?<=[\.\?\!])\s+|\n+", text)
    candidates = [p.strip() for p in parts if looks_like_question(p)]
    if candidates:
        return candidates[-1]
    if looks_like_question(text):
        return text
    return None


def _format_passages(hits: list) -> str:
    blocks: list[str] = []
    for i, (chunk, score) in enumerate(hits, start=1):
        blocks.append(
            f"[{i}] ({chunk.source}, score {score:.2f})\n{chunk.text.strip()}"
        )
    return "\n\n".join(blocks)


def _openai_answer(question: str, context: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You help a student during a live tutorial. "
                        "Answer ONLY using the provided course materials. "
                        "If the materials do not contain enough information, say so clearly. "
                        "Keep answers concise (3-8 sentences). Cite source file names when useful."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Course materials:\n{context}\n\nQuestion from tutorial:\n{question}",
                },
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[qa] OpenAI failed: {exc}")
        return None


class QAEngine:
    def __init__(self, index: MaterialsIndex) -> None:
        self.index = index
        self._last_question = ""

    def answer(self, question: str) -> AnswerResult:
        q = re.sub(r"\s+", " ", question).strip()
        # Avoid answering the same question repeatedly
        if q.lower() == self._last_question.lower():
            return AnswerResult(q, "", [], [], "empty")
        self._last_question = q

        hits = self.index.search(q)
        if not hits:
            return AnswerResult(
                question=q,
                answer="No matching content found in your course materials. Add more files to the materials folder and rebuild the index.",
                sources=[],
                scores=[],
                mode="empty",
            )

        sources = [h[0].source for h in hits]
        scores = [h[1] for h in hits]
        context = _format_passages(hits)
        llm = _openai_answer(q, context)
        if llm:
            return AnswerResult(q, llm, sources, scores, "openai")

        # Extractive fallback — show top matching passages
        parts: list[str] = []
        for i, (chunk, score) in enumerate(hits[:3], start=1):
            parts.append(f"[{i}] {chunk.source} ({score:.2f})\n{chunk.text.strip()}")
        answer = "\n\n".join(parts)
        return AnswerResult(q, answer, sources, scores, "passages")
