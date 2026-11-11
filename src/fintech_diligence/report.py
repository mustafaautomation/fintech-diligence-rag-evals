"""Markdown and HTML evaluation reports."""

import html
from pathlib import Path

from fintech_diligence.types import GateResult, MetricScore, QuestionFailure


def write_reports(
    directory: Path,
    improved: GateResult,
    baseline: GateResult | None = None,
    *,
    stem: str = "offline_eval_report",
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    markdown_path = directory / f"{stem}.md"
    html_path = directory / f"{stem}.html"
    markdown_path.write_text(render_markdown(improved, baseline), encoding="utf-8")
    html_path.write_text(render_html(improved, baseline), encoding="utf-8")
    return markdown_path, html_path


def render_markdown(improved: GateResult, baseline: GateResult | None = None) -> str:
    lines = [
        "# Harborline diligence evaluation",
        "",
        "Offline scores are computed from the pipeline snapshots in this repository.",
        "LLM-judged RAGAS scores are not in this report. They run only in live mode,",
        "and this run did not call a judge model.",
        "",
        "## Improved pipeline",
        "",
        f"Gate: {'pass' if improved.passed else 'fail'}.",
        "",
        _metric_table(improved.metrics),
        "",
    ]
    if baseline is not None:
        lines.extend(
            [
                "## Before and after",
                "",
                "Baseline is the broken variant: lowest-scoring chunks, and the prompt",
                "that allows estimates, investment advice, and forecasts. Improved is",
                "hybrid retrieval with the guardrail prompt.",
                "",
                _comparison_table(baseline, improved),
                "",
                f"Baseline gate: {'pass' if baseline.passed else 'fail'}.",
                f"Improved gate: {'pass' if improved.passed else 'fail'}.",
                "",
            ]
        )
    lines.extend(["## Per-question failures on the improved pipeline", ""])
    lines.extend(_failure_lines(improved.failures))
    if baseline is not None:
        lines.extend(["", "## Per-question failures on the baseline", ""])
        lines.extend(_failure_lines(baseline.failures))
    if improved.notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in improved.notes)
    lines.append("")
    return "\n".join(lines)


def render_html(improved: GateResult, baseline: GateResult | None = None) -> str:
    status = "pass" if improved.passed else "fail"
    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'>",
        "<title>Harborline diligence evaluation</title>",
        "<style>",
        "body{font-family:Georgia,serif;margin:2rem auto;max-width:920px;color:#1c1917;",
        "background:#fafaf9;line-height:1.45}",
        "table{border-collapse:collapse;width:100%;background:white}",
        "th,td{border:1px solid #d6d3d1;padding:0.4rem 0.55rem;text-align:left;font-size:0.95rem}",
        "th{background:#e7e5e4}",
        ".pass{color:#166534}.fail{color:#991b1b}",
        "h1,h2{font-weight:600}",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Harborline diligence evaluation</h1>",
        "<p>Offline scores come from the committed pipeline snapshots. "
        "This page does not include LLM-judged RAGAS scores.</p>",
        f"<p>Improved gate: <strong class='{status}'>{status}</strong></p>",
        "<h2>Improved pipeline</h2>",
        _html_metric_table(improved.metrics),
    ]
    if baseline is not None:
        base = "pass" if baseline.passed else "fail"
        parts.extend(
            [
                "<h2>Before and after</h2>",
                "<p>Baseline uses the lowest-scoring chunks and the prompt that allows "
                "estimates, investment advice, and forecasts. Improved uses hybrid "
                "retrieval and the guardrail prompt.</p>",
                _html_comparison(baseline, improved),
                f"<p>Baseline gate: <strong class='{base}'>{base}</strong>.</p>",
            ]
        )
    parts.extend(
        [
            "<h2>Per-question failures on the improved pipeline</h2>",
            _html_failures(improved.failures),
        ]
    )
    if baseline is not None:
        parts.extend(
            [
                "<h2>Per-question failures on the baseline</h2>",
                _html_failures(baseline.failures),
            ]
        )
    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)


def format_score(value: float) -> str:
    return f"{value:.3f}"


def _metric_table(metrics: tuple[MetricScore, ...]) -> str:
    lines = [
        "| Metric | Score | Threshold | Samples | Result |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for metric in metrics:
        result = "pass" if metric.passed else "fail"
        lines.append(
            f"| {metric.name} | {format_score(metric.value)} | {format_score(metric.threshold)} "
            f"| {metric.sample_count} | {result} |"
        )
    return "\n".join(lines)


def _comparison_table(baseline: GateResult, improved: GateResult) -> str:
    improved_by_name = {metric.name: metric for metric in improved.metrics}
    lines = [
        "| Metric | Baseline | Improved | Threshold |",
        "| --- | ---: | ---: | ---: |",
    ]
    for metric in baseline.metrics:
        after = improved_by_name.get(metric.name)
        after_value = format_score(after.value) if after else "n/a"
        lines.append(
            f"| {metric.name} | {format_score(metric.value)} | {after_value} "
            f"| {format_score(metric.threshold)} |"
        )
    return "\n".join(lines)


def _failure_lines(failures: tuple[QuestionFailure, ...]) -> list[str]:
    if not failures:
        return ["None."]
    lines: list[str] = []
    for failure in failures:
        reasons = ", ".join(failure.reasons)
        lines.append(f"### {failure.question_id}")
        lines.append("")
        lines.append(failure.question)
        lines.append("")
        lines.append(f"Reasons: {reasons}")
        lines.append("")
        lines.append(failure.response)
        lines.append("")
    return lines


def _html_metric_table(metrics: tuple[MetricScore, ...]) -> str:
    header = (
        "<tr><th>Metric</th><th>Score</th><th>Threshold</th><th>Samples</th><th>Result</th></tr>"
    )
    rows = ["<table>", header]
    for metric in metrics:
        result = "pass" if metric.passed else "fail"
        rows.append(
            "<tr>"
            f"<td>{html.escape(metric.name)}</td>"
            f"<td>{format_score(metric.value)}</td>"
            f"<td>{format_score(metric.threshold)}</td>"
            f"<td>{metric.sample_count}</td>"
            f"<td class='{result}'>{result}</td>"
            "</tr>"
        )
    rows.append("</table>")
    return "\n".join(rows)


def _html_comparison(baseline: GateResult, improved: GateResult) -> str:
    improved_by_name = {metric.name: metric for metric in improved.metrics}
    header = "<tr><th>Metric</th><th>Baseline</th><th>Improved</th><th>Threshold</th></tr>"
    rows = ["<table>", header]
    for metric in baseline.metrics:
        after = improved_by_name.get(metric.name)
        after_value = format_score(after.value) if after else "n/a"
        rows.append(
            "<tr>"
            f"<td>{html.escape(metric.name)}</td>"
            f"<td>{format_score(metric.value)}</td>"
            f"<td>{after_value}</td>"
            f"<td>{format_score(metric.threshold)}</td>"
            "</tr>"
        )
    rows.append("</table>")
    return "\n".join(rows)


def _html_failures(failures: tuple[QuestionFailure, ...]) -> str:
    if not failures:
        return "<p>None.</p>"
    blocks: list[str] = []
    for failure in failures:
        blocks.append(
            "<section>"
            f"<h3>{html.escape(failure.question_id)}</h3>"
            f"<p>{html.escape(failure.question)}</p>"
            f"<p>Reasons: {html.escape(', '.join(failure.reasons))}</p>"
            f"<p>{html.escape(failure.response)}</p>"
            "</section>"
        )
    return "\n".join(blocks)
