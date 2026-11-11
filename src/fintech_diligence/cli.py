"""Command line: ask a question, or run the evaluation gate."""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from fintech_diligence.evalset import load_questions  # noqa: E402
from fintech_diligence.gate import gate_from_samples, gate_records, load_threshold_table  # noqa: E402
from fintech_diligence.metrics import score_samples  # noqa: E402
from fintech_diligence.paths import snapshot_path  # noqa: E402
from fintech_diligence.pipeline import VARIANTS, build_pipeline  # noqa: E402
from fintech_diligence.report import format_score, render_markdown, write_reports  # noqa: E402
from fintech_diligence.snapshots import read_snapshot, write_snapshot  # noqa: E402
from fintech_diligence.types import AnswerRecord, GateResult  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diligence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Answer one question")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--variant", default="improved", choices=[*VARIANTS, "live"])

    eval_parser = subparsers.add_parser("eval", help="Score a snapshot or a live run")
    eval_parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    eval_parser.add_argument("--variant", default="improved", choices=[*VARIANTS, "live"])
    eval_parser.add_argument("--rebuild", action="store_true", help="Rewrite the snapshot")
    eval_parser.add_argument("--write-report", type=Path, help="Directory for the report")
    eval_parser.add_argument("--snapshot", type=Path, help="Snapshot JSONL to score")

    args = parser.parse_args(argv)
    if args.command == "ask":
        return _ask(args.question, args.variant)
    return _evaluate(args)


def _ask(question: str, variant: str) -> int:
    if variant == "live" and not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set.", file=sys.stderr)
        return 2
    pipeline = build_pipeline(variant)
    response, hits = pipeline.ask(question)
    print(response)
    print("")
    for hit in hits:
        print(f"[{hit.rank}] {hit.chunk.id} score={hit.score:.3f}")
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    thresholds = load_threshold_table()
    if args.mode == "live":
        return _evaluate_live(thresholds)
    variant = args.variant if args.variant != "live" else "improved"
    records = _offline_records(variant, rebuild=args.rebuild, snapshot=args.snapshot)
    result = gate_records(records, thresholds["offline"], variant=variant)
    baseline = _baseline_result(thresholds["offline"], variant)
    _print_result(result)
    if baseline is not None and variant == "improved":
        print("")
        print("Baseline (broken retriever and no-guardrail prompt)")
        _print_result(baseline)
    if args.write_report is not None:
        if variant != "improved":
            print("--write-report writes the improved-versus-baseline report.", file=sys.stderr)
            return 2
        if baseline is None:
            print("Baseline snapshot is missing. Report not written.", file=sys.stderr)
            return 2
        markdown_path, html_path = write_reports(args.write_report, result, baseline)
        print(f"Wrote {markdown_path}")
        print(f"Wrote {html_path}")
    return 0 if result.passed else 1


def _evaluate_live(thresholds: dict[str, dict[str, float]]) -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Live eval was not run.", file=sys.stderr)
        return 2
    from fintech_diligence.ragas_live import RagasJudge, attach_live_scores

    pipeline = build_pipeline("live")
    records = [pipeline.answer_question(item) for item in load_questions()]
    samples = score_samples(records)
    attach_live_scores(samples, RagasJudge().score_many(records))
    combined = dict(thresholds["offline"])
    combined.update(thresholds.get("live", {}))
    result = gate_from_samples(
        samples,
        combined,
        variant="live",
        notes=("Live scores were produced by ragas collections metrics on this run.",),
    )
    _print_result(result)
    print("")
    print(render_markdown(result))
    return 0 if result.passed else 1


def _offline_records(variant: str, *, rebuild: bool, snapshot: Path | None) -> list[AnswerRecord]:
    path = snapshot or snapshot_path(variant)
    if rebuild:
        pipeline = build_pipeline(variant)
        records = [pipeline.answer_question(item) for item in load_questions()]
        write_snapshot(path, records)
        print(f"Wrote {path}")
        return records
    if not path.is_file():
        raise FileNotFoundError(f"Missing snapshot {path}. Run with --rebuild to create it.")
    return read_snapshot(path)


def _baseline_result(thresholds: dict[str, float], variant: str) -> GateResult | None:
    if variant != "improved":
        return None
    path = snapshot_path("baseline")
    if not path.is_file():
        return None
    return gate_records(read_snapshot(path), thresholds, variant="baseline")


def _print_result(result: GateResult) -> None:
    print(f"Variant: {result.variant}")
    print(f"Gate: {'pass' if result.passed else 'fail'}")
    for metric in result.metrics:
        flag = "pass" if metric.passed else "fail"
        print(
            f"  {metric.name}: {format_score(metric.value)} "
            f"(threshold {format_score(metric.threshold)}, n={metric.sample_count}) {flag}"
        )
    print(f"Questions below a perfect per-question score: {len(result.failures)}")


if __name__ == "__main__":
    raise SystemExit(main())
