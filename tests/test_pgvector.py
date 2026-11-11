from fintech_diligence.embeddings import HashingEmbedder
from fintech_diligence.pipeline import build_chunks
from fintech_diligence.retrievers import PgVectorRetriever


class FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.statements: list[str] = []
        self._rows = rows

    def execute(self, sql: str, params: dict[str, object] | None = None) -> "FakeConnection":
        self.statements.append(sql)
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows

    def commit(self) -> None:
        return None


def test_pgvector_schema_and_search_use_cosine_distance() -> None:
    chunks = build_chunks()[:3]
    rows = [(chunk.id, chunk.text, 0.2) for chunk in chunks]
    connection = FakeConnection(rows)
    retriever = PgVectorRetriever(connection, chunks, HashingEmbedder())
    retriever.ensure_schema()
    retriever.index()
    hits = retriever.search("total revenue", k=2)
    schema = "\n".join(connection.statements)
    assert "CREATE EXTENSION IF NOT EXISTS vector" in schema
    assert "vector(" in schema
    assert "<=>" in schema
    assert len(hits) == 2
    assert {hit.chunk.id for hit in hits} <= {chunk.id for chunk in chunks}
