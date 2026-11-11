from pathlib import Path

from fintech_diligence.cli import main
from fintech_diligence.gate import gate_records, load_threshold_table
from fintech_diligence.report import format_score
from fintech_diligence.snapshots import read_snapshot


def test_offline_cli_passes_and_baseline_cli_fails() -> None:
    assert main(["eval", "--mode", "offline"]) == 0
    assert main(["eval", "--mode", "offline", "--variant", "baseline"]) == 1


def test_live_cli_does_not_run_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["eval", "--mode", "live"]) == 2


def test_committed_snapshots_match_the_pipeline_and_report() -> None:
    from fintech_diligence.evalset import load_questions
    from fintech_diligence.pipeline import build_pipeline

    questions = load_questions()
    for variant in ("improved", "baseline"):
        fresh = [build_pipeline(variant).answer_question(item) for item in questions]
        saved = read_snapshot(Path(f"data/snapshots/{variant}.jsonl"))
        assert [record.response for record in fresh] == [record.response for record in saved]
        assert [record.retrieved_chunk_ids for record in fresh] == [
            record.retrieved_chunk_ids for record in saved
        ]
        for row in Path(f"data/snapshots/{variant}.jsonl").read_text(encoding="utf-8").splitlines():
            assert "faithfulness" not in row
            assert "judge" not in row

    thresholds = load_threshold_table()["offline"]
    saved = read_snapshot(Path("data/snapshots/improved.jsonl"))
    improved = gate_records(saved, thresholds, variant="improved")
    report = Path("docs/reports/offline_eval_report.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    for metric in improved.metrics:
        rendered = f"| {metric.name} | {format_score(metric.value)} |"
        assert rendered in report
        assert format_score(metric.value) in readme
    assert "LLM-judged RAGAS scores are not in this report" in report
    assert "synthetic" in readme.lower()
