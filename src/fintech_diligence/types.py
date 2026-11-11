"""Shared records for documents, retrieval, and evaluation."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    title: str
    text: str
    source_path: str


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    document_id: str
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class Hit:
    chunk: Chunk
    score: float
    rank: int


@dataclass(frozen=True, slots=True)
class EvalQuestion:
    id: str
    question: str
    reference_answer: str
    passages: tuple[str, ...]
    reference_phrases: tuple[str, ...]
    expected_behavior: str
    forbidden_phrases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnswerRecord:
    id: str
    question: str
    response: str
    retrieved_chunk_ids: tuple[str, ...]
    retrieved_contexts: tuple[str, ...]
    reference_chunk_ids: tuple[str, ...]
    reference_contexts: tuple[str, ...]
    reference_phrases: tuple[str, ...]
    forbidden_phrases: tuple[str, ...]
    expected_behavior: str
    reference_answer: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetricScore:
    name: str
    value: float
    threshold: float
    passed: bool
    sample_count: int


@dataclass(frozen=True, slots=True)
class QuestionFailure:
    question_id: str
    question: str
    reasons: tuple[str, ...]
    response: str


@dataclass(frozen=True, slots=True)
class GateResult:
    variant: str
    metrics: tuple[MetricScore, ...]
    failures: tuple[QuestionFailure, ...]
    passed: bool
    notes: tuple[str, ...] = field(default_factory=tuple)
