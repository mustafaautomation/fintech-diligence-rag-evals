"""Load the labelled question file."""

import json
from pathlib import Path

from fintech_diligence.paths import questions_path
from fintech_diligence.types import EvalQuestion

_BEHAVIORS = {"answer", "refuse"}


def load_questions(path: Path | None = None) -> list[EvalQuestion]:
    source = path or questions_path()
    questions: list[EvalQuestion] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        behavior = str(payload["expected_behavior"])
        if behavior not in _BEHAVIORS:
            raise ValueError(f"Line {line_number}: unknown expected_behavior {behavior!r}")
        questions.append(
            EvalQuestion(
                id=str(payload["id"]),
                question=str(payload["question"]),
                reference_answer=str(payload["reference_answer"]),
                passages=tuple(str(item) for item in payload.get("passages", [])),
                reference_phrases=tuple(str(item) for item in payload["reference_phrases"]),
                expected_behavior=behavior,
                forbidden_phrases=tuple(str(item) for item in payload.get("forbidden_phrases", [])),
                tags=tuple(str(item) for item in payload.get("tags", [])),
            )
        )
    if len(questions) < 30:
        raise ValueError(f"Expected at least 30 questions, found {len(questions)}")
    ids = [item.id for item in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Question ids are not unique")
    return questions
