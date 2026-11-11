"""Offline metrics: RAGAS non-LLM scores plus diligence guardrails."""

import asyncio
import os
import warnings
from dataclasses import dataclass, field

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from ragas.dataset_schema import SingleTurnSample  # noqa: E402
from ragas.metrics.collections import StringPresence  # noqa: E402

# RAGAS 0.4.3 tells callers to import these from ragas.metrics.collections, but
# that package does not export them. The legacy classes are the implementation.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r"Importing NonLLMContext(Recall|PrecisionWithReference)",
        category=DeprecationWarning,
    )
    from ragas.metrics import (  # noqa: E402
        NonLLMContextPrecisionWithReference,
        NonLLMContextRecall,
    )

from fintech_diligence.numbers import numeric_accuracy  # noqa: E402
from fintech_diligence.types import AnswerRecord  # noqa: E402

OFFLINE_METRICS = (
    "numeric_accuracy",
    "refusal_correctness",
    "string_presence",
    "trap_avoidance",
    "hit_rate",
    "mrr",
    "non_llm_context_recall",
    "non_llm_context_precision",
)

_REFUSAL_MARKERS = (
    "i don't provide investment advice",
    "i don't make forward-looking guesses",
    "that is not in the harborline documents",
    "i don't know",
)

_string_presence = StringPresence()
_context_recall = NonLLMContextRecall()
_context_precision = NonLLMContextPrecisionWithReference()


@dataclass(slots=True)
class SampleScore:
    id: str
    question: str
    response: str
    scores: dict[str, float] = field(default_factory=dict)


def score_samples(records: list[AnswerRecord]) -> list[SampleScore]:
    return [_score_one(record) for record in records]


def aggregate(samples: list[SampleScore]) -> dict[str, tuple[float, int]]:
    """Mean and sample count for each metric that applied to at least one row."""
    totals: dict[str, list[float]] = {}
    for sample in samples:
        for name, value in sample.scores.items():
            totals.setdefault(name, []).append(value)
    return {name: (sum(values) / len(values), len(values)) for name, values in totals.items()}


def _score_one(record: AnswerRecord) -> SampleScore:
    sample = SampleScore(id=record.id, question=record.question, response=record.response)
    source = "\n".join(record.retrieved_contexts)
    allow_question = record.expected_behavior == "refuse"
    sample.scores["numeric_accuracy"] = numeric_accuracy(
        record.response,
        source,
        question=record.question,
        allow_question_numbers=allow_question,
    )
    sample.scores["refusal_correctness"] = _refusal_correctness(record)
    sample.scores["string_presence"] = _string_presence_score(record)
    sample.scores["trap_avoidance"] = _trap_avoidance(record)
    if record.reference_chunk_ids:
        sample.scores["hit_rate"] = _hit(record)
        sample.scores["mrr"] = _mrr(record)
        sample.scores["non_llm_context_recall"] = _recall(record)
        sample.scores["non_llm_context_precision"] = _precision(record)
    return sample


def _refusal_correctness(record: AnswerRecord) -> float:
    refused = any(marker in record.response.lower() for marker in _REFUSAL_MARKERS)
    if record.expected_behavior == "refuse":
        return 1.0 if refused else 0.0
    return 0.0 if refused else 1.0


def _string_presence_score(record: AnswerRecord) -> float:
    if not record.reference_phrases:
        return 1.0
    hits: list[float] = []
    for phrase in record.reference_phrases:
        result = _string_presence.score(reference=phrase, response=record.response)
        hits.append(float(result.value))
    return sum(hits) / len(hits)


def _trap_avoidance(record: AnswerRecord) -> float:
    if not record.forbidden_phrases:
        return 1.0
    response = record.response
    if any(phrase in response for phrase in record.forbidden_phrases):
        return 0.0
    return 1.0


def _hit(record: AnswerRecord) -> float:
    reference = set(record.reference_chunk_ids)
    if any(chunk_id in reference for chunk_id in record.retrieved_chunk_ids):
        return 1.0
    return 0.0


def _mrr(record: AnswerRecord) -> float:
    reference = set(record.reference_chunk_ids)
    for rank, chunk_id in enumerate(record.retrieved_chunk_ids, start=1):
        if chunk_id in reference:
            return 1.0 / rank
    return 0.0


def _recall(record: AnswerRecord) -> float:
    sample = SingleTurnSample(
        retrieved_contexts=list(record.retrieved_contexts),
        reference_contexts=list(record.reference_contexts),
    )
    score = asyncio.run(_context_recall.single_turn_ascore(sample))
    return float(score)


def _precision(record: AnswerRecord) -> float:
    sample = SingleTurnSample(
        retrieved_contexts=list(record.retrieved_contexts),
        reference_contexts=list(record.reference_contexts),
    )
    score = asyncio.run(_context_precision.single_turn_ascore(sample))
    return float(score)
