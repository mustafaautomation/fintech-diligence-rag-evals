"""Hybrid retrieval over FAISS (or NumPy) and an optional pgvector backend."""

from typing import Protocol, cast

import numpy as np

from fintech_diligence.embeddings import Embedder
from fintech_diligence.lexical import BM25Index
from fintech_diligence.tokenize import tokenize
from fintech_diligence.types import Chunk, Hit


class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[Hit]: ...


class _Cursor(Protocol):
    def fetchall(self) -> list[tuple[object, ...]]: ...


class _Connection(Protocol):
    def execute(self, sql: str, params: dict[str, object] | None = None) -> _Cursor: ...

    def commit(self) -> None: ...


class HybridRetriever:
    """Score every chunk with embedding cosine and BM25, then blend the ranks.

    FAISS is used for the inner product when the package imports. NumPy is the
    fallback so the same scores can be computed if FAISS is absent. Docker is
    not required.
    """

    def __init__(
        self,
        chunks: list[Chunk],
        embedder: Embedder,
        vector_weight: float = 0.30,
    ) -> None:
        if not chunks:
            raise ValueError("HybridRetriever needs chunks")
        if not 0.0 <= vector_weight <= 1.0:
            raise ValueError("vector_weight must be between 0 and 1")
        self.chunks = chunks
        self.vector_weight = vector_weight
        self.embedder = embedder
        vectors = embedder.embed_documents([chunk.text for chunk in chunks])
        self._matrix = np.asarray(vectors, dtype=np.float32)
        self._backend, self._index = _build_index(self._matrix)
        self._bm25 = BM25Index([tokenize(chunk.text) for chunk in chunks])

    @property
    def backend(self) -> str:
        return self._backend

    def ranked(self, query: str) -> list[tuple[Chunk, float]]:
        cosine = _cosine_scores(self._index, self._matrix, self.embedder.embed_query(query))
        lexical = self._bm25.scores(query)
        cosine_unit = _unit_interval([(score + 1.0) / 2.0 for score in cosine])
        lexical_unit = _unit_interval(lexical)
        weight = self.vector_weight
        blended = [
            weight * vector_score + (1.0 - weight) * lexical_score
            for vector_score, lexical_score in zip(cosine_unit, lexical_unit, strict=True)
        ]
        pairs = list(zip(self.chunks, blended, strict=True))
        pairs.sort(key=lambda item: (-item[1], item[0].id))
        return [(chunk, score) for chunk, score in pairs]

    def search(self, query: str, k: int) -> list[Hit]:
        return _hits(self.ranked(query), k)


class BadRetriever:
    """Return the least similar chunks. Used to prove the eval gate fails."""

    def __init__(
        self,
        chunks: list[Chunk],
        embedder: Embedder,
        vector_weight: float = 0.30,
    ) -> None:
        self._inner = HybridRetriever(chunks, embedder, vector_weight=vector_weight)

    def search(self, query: str, k: int) -> list[Hit]:
        ranked = self._inner.ranked(query)
        worst = sorted(ranked, key=lambda item: (item[1], item[0].id))
        return _hits(worst, k)


class PgVectorRetriever:
    """Index chunks in Postgres with pgvector, then blend with BM25.

    The SQL orders by cosine distance. On this small corpus the query fetches
    every indexed row and the blend matches HybridRetriever's ingredients.
    `database_url` is read by the caller; this object takes an open connection
    so tests can pass a fake.
    """

    def __init__(
        self,
        connection: _Connection,
        chunks: list[Chunk],
        embedder: Embedder,
        vector_weight: float = 0.30,
    ) -> None:
        self._connection = connection
        self.chunks = chunks
        self.embedder = embedder
        self.vector_weight = vector_weight
        self._bm25 = BM25Index([tokenize(chunk.text) for chunk in chunks])
        self._by_id = {chunk.id: chunk for chunk in chunks}

    def ensure_schema(self) -> None:
        dim = self.embedder.dim
        _execute(
            self._connection,
            "CREATE EXTENSION IF NOT EXISTS vector",
        )
        _execute(self._connection, "DROP TABLE IF EXISTS diligence_chunks")
        _execute(
            self._connection,
            f"""
            CREATE TABLE diligence_chunks (
                id text PRIMARY KEY,
                document_id text NOT NULL,
                title text NOT NULL,
                content text NOT NULL,
                embedding vector({dim}) NOT NULL
            )
            """,
        )
        _commit(self._connection)

    def index(self) -> None:
        vectors = self.embedder.embed_documents([chunk.text for chunk in self.chunks])
        for chunk, vector in zip(self.chunks, vectors, strict=True):
            _execute(
                self._connection,
                """
                INSERT INTO diligence_chunks (id, document_id, title, content, embedding)
                VALUES (%(id)s, %(document_id)s, %(title)s, %(content)s, %(embedding)s)
                """,
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "title": chunk.title,
                    "content": chunk.text,
                    "embedding": vector,
                },
            )
        _commit(self._connection)

    def search(self, query: str, k: int) -> list[Hit]:
        vector = self.embedder.embed_query(query)
        rows = _fetch(
            self._connection,
            """
            SELECT id, content, embedding <=> %(embedding)s AS distance
            FROM diligence_chunks
            ORDER BY embedding <=> %(embedding)s
            """,
            {"embedding": vector},
        )
        cosine_by_id = {str(row[0]): 1.0 - float(cast(float, row[2])) for row in rows}
        lexical_by_id = {
            chunk.id: score
            for chunk, score in zip(self.chunks, self._bm25.scores(query), strict=True)
        }
        cosine_unit = _unit_interval(
            [(cosine_by_id.get(chunk.id, 0.0) + 1.0) / 2.0 for chunk in self.chunks]
        )
        lexical_unit = _unit_interval([lexical_by_id[chunk.id] for chunk in self.chunks])
        weight = self.vector_weight
        blended = [
            (chunk, weight * vector_score + (1.0 - weight) * lexical_score)
            for chunk, vector_score, lexical_score in zip(
                self.chunks, cosine_unit, lexical_unit, strict=True
            )
        ]
        blended.sort(key=lambda item: (-item[1], item[0].id))
        return _hits(blended, k)


def connect_postgres(database_url: str) -> _Connection:
    import psycopg
    from pgvector.psycopg import register_vector

    connection = psycopg.connect(database_url)
    register_vector(connection)
    return cast(_Connection, connection)


def _build_index(matrix: np.ndarray) -> tuple[str, object]:
    try:
        import faiss
    except ImportError:
        return "numpy", matrix
    index = faiss.IndexFlatIP(int(matrix.shape[1]))
    index.add(matrix)
    return "faiss", index


def _cosine_scores(index: object, matrix: np.ndarray, query: list[float]) -> list[float]:
    query_row = np.asarray([query], dtype=np.float32)
    if matrix.ndim != 2:
        raise ValueError("embedding matrix must be 2-d")
    count = int(matrix.shape[0])
    faiss_index = getattr(index, "search", None)
    if faiss_index is None:
        scores = matrix @ query_row[0]
        return [float(score) for score in scores]
    distances, ids = index.search(query_row, count)  # type: ignore[attr-defined]
    aligned = [0.0] * count
    for idx, score in zip(ids[0], distances[0], strict=True):
        if int(idx) >= 0:
            aligned[int(idx)] = float(score)
    return aligned


def _unit_interval(values: list[float]) -> list[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if high - low < 1e-12:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _hits(ranked: list[tuple[Chunk, float]], k: int) -> list[Hit]:
    if k < 1:
        raise ValueError("k must be at least 1")
    return [
        Hit(chunk=chunk, score=score, rank=rank)
        for rank, (chunk, score) in enumerate(ranked[:k], start=1)
    ]


def _execute(connection: _Connection, sql: str, params: dict[str, object] | None = None) -> None:
    connection.execute(sql, params)


def _commit(connection: _Connection) -> None:
    connection.commit()


def _fetch(
    connection: _Connection,
    sql: str,
    params: dict[str, object],
) -> list[tuple[object, ...]]:
    cursor = connection.execute(sql, params)
    return [tuple(row) for row in cursor.fetchall()]
