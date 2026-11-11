"""Split annual-report markdown into section chunks."""

import re

from fintech_diligence.types import Chunk, Document

_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def chunk_documents(documents: list[Document]) -> list[Chunk]:
    """One chunk per `##` section. A document with no sections is one chunk."""
    chunks: list[Chunk] = []
    for document in documents:
        sections = _sections(document.text)
        for heading, body in sections:
            slug = _slug(heading) if heading else "body"
            text = f"{heading}\n{body}".strip() if heading else body.strip()
            if not text:
                continue
            chunks.append(
                Chunk(
                    id=f"{document.id}#{slug}",
                    document_id=document.id,
                    title=heading or document.title,
                    text=text,
                )
            )
    if not chunks:
        raise ValueError("Chunking produced no chunks")
    ids = [chunk.id for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Chunk ids are not unique")
    return chunks


def _sections(text: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(text))
    if not matches:
        body = _strip_h1(text)
        return [("", body)]
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = match.group(1).strip()
        body = text[start:end].strip()
        sections.append((heading, body))
    return sections


def _strip_h1(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join(lines[1:]).strip()
    return text.strip()


def _slug(heading: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
    return slug or "section"
