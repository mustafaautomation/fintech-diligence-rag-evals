"""BM25 over chunk tokens."""

import math

from fintech_diligence.tokenize import tokenize


class BM25Index:
    def __init__(self, documents: list[list[str]], k1: float = 1.2, b: float = 0.75) -> None:
        if not documents:
            raise ValueError("BM25 needs at least one document")
        self._docs = documents
        self._k1 = k1
        self._b = b
        self._n = len(documents)
        self._avgdl = sum(len(doc) for doc in documents) / self._n
        document_frequency: dict[str, int] = {}
        for doc in documents:
            for term in set(doc):
                document_frequency[term] = document_frequency.get(term, 0) + 1
        self._idf = {
            term: math.log(1.0 + (self._n - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def scores(self, query: str) -> list[float]:
        query_terms = tokenize(query)
        scored: list[float] = []
        for doc in self._docs:
            term_frequency: dict[str, int] = {}
            for term in doc:
                term_frequency[term] = term_frequency.get(term, 0) + 1
            length = len(doc) or 1
            score = 0.0
            for term in query_terms:
                freq = term_frequency.get(term)
                if not freq:
                    continue
                idf = self._idf.get(term, 0.0)
                denominator = freq + self._k1 * (1.0 - self._b + self._b * length / self._avgdl)
                score += idf * (freq * (self._k1 + 1.0)) / denominator
            scored.append(score)
        return scored
