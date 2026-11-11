"""Read and write JSONL snapshots of pipeline outputs."""

import json
from pathlib import Path

from fintech_diligence.types import AnswerRecord


def write_snapshot(path: Path, records: list[AnswerRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(_to_json(record), ensure_ascii=True) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_snapshot(path: Path) -> list[AnswerRecord]:
    records: list[AnswerRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records.append(
            AnswerRecord(
                id=str(payload["id"]),
                question=str(payload["question"]),
                response=str(payload["response"]),
                retrieved_chunk_ids=tuple(payload["retrieved_chunk_ids"]),
                retrieved_contexts=tuple(payload["retrieved_contexts"]),
                reference_chunk_ids=tuple(payload["reference_chunk_ids"]),
                reference_contexts=tuple(payload["reference_contexts"]),
                reference_phrases=tuple(payload["reference_phrases"]),
                forbidden_phrases=tuple(payload.get("forbidden_phrases", [])),
                expected_behavior=str(payload["expected_behavior"]),
                reference_answer=str(payload["reference_answer"]),
                tags=tuple(payload.get("tags", [])),
            )
        )
    if not records:
        raise ValueError(f"Snapshot {path} is empty")
    return records


def _to_json(record: AnswerRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "question": record.question,
        "response": record.response,
        "retrieved_chunk_ids": list(record.retrieved_chunk_ids),
        "retrieved_contexts": list(record.retrieved_contexts),
        "reference_chunk_ids": list(record.reference_chunk_ids),
        "reference_contexts": list(record.reference_contexts),
        "reference_phrases": list(record.reference_phrases),
        "forbidden_phrases": list(record.forbidden_phrases),
        "expected_behavior": record.expected_behavior,
        "reference_answer": record.reference_answer,
        "tags": list(record.tags),
    }
