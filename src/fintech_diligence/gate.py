"""Compare metric means with the thresholds in evals/thresholds.toml."""

import tomllib
from pathlib import Path

from fintech_diligence.metrics import SampleScore, aggregate, score_samples
from fintech_diligence.paths import thresholds_path
from fintech_diligence.types import AnswerRecord, GateResult, MetricScore, QuestionFailure


def load_threshold_table(path: Path | None = None) -> dict[str, dict[str, float]]:
    source = path or thresholds_path()
    raw = tomllib.loads(source.read_text(encoding="utf-8"))
    table: dict[str, dict[str, float]] = {}
    for section, values in raw.items():
        if not isinstance(values, dict):
            raise ValueError(f"Threshold section {section} must be a table")
        table[str(section)] = {str(name): float(value) for name, value in values.items()}
    if "offline" not in table:
        raise ValueError("thresholds.toml needs an [offline] table")
    return table


def gate_records(
    records: list[AnswerRecord],
    thresholds: dict[str, float],
    *,
    variant: str,
    notes: tuple[str, ...] = (),
) -> GateResult:
    samples = score_samples(records)
    return gate_from_samples(samples, thresholds, variant=variant, notes=notes)


def gate_from_samples(
    samples: list[SampleScore],
    thresholds: dict[str, float],
    *,
    variant: str,
    notes: tuple[str, ...] = (),
) -> GateResult:
    means = aggregate(samples)
    metrics: list[MetricScore] = []
    for name, threshold in thresholds.items():
        if name not in means:
            metrics.append(MetricScore(name, 0.0, threshold, False, 0))
            continue
        value, count = means[name]
        metrics.append(
            MetricScore(
                name=name,
                value=value,
                threshold=threshold,
                passed=value + 1e-9 >= threshold,
                sample_count=count,
            )
        )
    failures = _failures(samples)
    scored = all(metric.sample_count > 0 for metric in metrics)
    passed = scored and all(metric.passed for metric in metrics)
    return GateResult(
        variant=variant,
        metrics=tuple(metrics),
        failures=tuple(failures),
        passed=passed,
        notes=notes,
    )


def _failures(samples: list[SampleScore]) -> list[QuestionFailure]:
    failures: list[QuestionFailure] = []
    for sample in samples:
        reasons = tuple(
            f"{name}={value:.3f}" for name, value in sample.scores.items() if value < 1.0 - 1e-9
        )
        if reasons:
            failures.append(
                QuestionFailure(
                    question_id=sample.id,
                    question=sample.question,
                    reasons=reasons,
                    response=sample.response,
                )
            )
    return failures
