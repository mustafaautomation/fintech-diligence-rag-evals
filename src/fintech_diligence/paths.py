"""Locate repository data files from an editable install."""

from pathlib import Path


def repo_root() -> Path:
    """Return the repository root that holds pyproject.toml and data/."""
    start = Path(__file__).resolve()
    for parent in start.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "data" / "corpus").is_dir():
            return parent
    raise FileNotFoundError(f"Could not find the repository root from {start}")


def corpus_dir() -> Path:
    return repo_root() / "data" / "corpus"


def questions_path() -> Path:
    return repo_root() / "data" / "eval" / "questions.jsonl"


def snapshot_path(variant: str) -> Path:
    return repo_root() / "data" / "snapshots" / f"{variant}.jsonl"


def thresholds_path() -> Path:
    return repo_root() / "evals" / "thresholds.toml"


def pipeline_config_path() -> Path:
    return repo_root() / "evals" / "pipeline.toml"
