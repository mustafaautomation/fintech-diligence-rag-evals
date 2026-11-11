from fintech_diligence.evalset import load_questions
from fintech_diligence.gate import gate_from_samples, gate_records, load_threshold_table
from fintech_diligence.metrics import SampleScore
from fintech_diligence.pipeline import build_pipeline
from fintech_diligence.ragas_live import attach_live_scores
from fintech_diligence.types import AnswerRecord


def _records(variant: str) -> list[AnswerRecord]:
    pipeline = build_pipeline(variant)
    return [pipeline.answer_question(item) for item in load_questions()]


def test_improved_pipeline_passes_and_broken_variants_fail() -> None:
    thresholds = load_threshold_table()["offline"]
    improved = gate_records(_records("improved"), thresholds, variant="improved")
    bad_retriever = gate_records(_records("bad-retriever"), thresholds, variant="bad-retriever")
    no_guardrail = gate_records(_records("no-guardrail"), thresholds, variant="no-guardrail")
    baseline = gate_records(_records("baseline"), thresholds, variant="baseline")

    assert improved.passed
    by_name = {metric.name: metric for metric in improved.metrics}
    assert by_name["numeric_accuracy"].value == 1.0
    assert by_name["refusal_correctness"].value == 1.0
    assert by_name["hit_rate"].value == 1.0
    assert by_name["mrr"].value == 1.0
    assert by_name["non_llm_context_recall"].value == 1.0

    assert not bad_retriever.passed
    bad_by_name = {metric.name: metric for metric in bad_retriever.metrics}
    assert not bad_by_name["hit_rate"].passed
    assert not bad_by_name["non_llm_context_recall"].passed

    assert not no_guardrail.passed
    guard_by_name = {metric.name: metric for metric in no_guardrail.metrics}
    assert guard_by_name["hit_rate"].passed
    assert not guard_by_name["numeric_accuracy"].passed
    assert not guard_by_name["refusal_correctness"].passed
    assert not guard_by_name["trap_avoidance"].passed

    assert not baseline.passed


def test_live_scores_can_be_attached_without_calling_a_model() -> None:
    record = AnswerRecord(
        id="sample",
        question="What was total revenue?",
        response="Total revenue was $186,400,000.",
        retrieved_chunk_ids=("income-statement#total-revenue",),
        retrieved_contexts=("Total revenue was $186,400,000.",),
        reference_chunk_ids=("income-statement#total-revenue",),
        reference_contexts=("Total revenue was $186,400,000.",),
        reference_phrases=("$186,400,000",),
        forbidden_phrases=(),
        expected_behavior="answer",
        reference_answer="Total revenue was $186,400,000.",
    )
    sample = SampleScore(
        id=record.id,
        question=record.question,
        response=record.response,
        scores={},
    )
    attach_live_scores(
        [sample],
        [
            {
                "faithfulness": 0.50,
                "answer_relevancy": 0.40,
                "context_precision": 0.80,
                "context_recall": 0.90,
            }
        ],
    )
    result = gate_from_samples(
        [sample],
        {
            "faithfulness": 0.70,
            "answer_relevancy": 0.70,
            "context_precision": 0.70,
            "context_recall": 0.70,
        },
        variant="live",
    )
    assert not result.passed
    failed = {metric.name for metric in result.metrics if not metric.passed}
    assert failed == {"faithfulness", "answer_relevancy"}
