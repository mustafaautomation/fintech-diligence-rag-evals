"""Load the synthetic annual-report corpus."""

from pathlib import Path

from fintech_diligence.types import Document


def load_corpus(directory: Path) -> list[Document]:
    """Load markdown documents. The file stem is the document id."""
    paths = sorted(path for path in directory.glob("*.md") if path.is_file())
    if not paths:
        raise FileNotFoundError(f"No markdown documents in {directory}")
    documents: list[Document] = []
    for path in paths:
        text = path.read_text(encoding="utf-8").strip()
        title = _title(text, path.stem)
        documents.append(Document(id=path.stem, title=title, text=text, source_path=str(path)))
    return documents


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback
