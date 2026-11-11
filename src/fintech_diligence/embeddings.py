"""Embedding providers. The default embedder is deterministic and offline."""

import hashlib
import math
import os
from typing import Protocol

EMBEDDING_DIM = 384


class Embedder(Protocol):
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Signed feature hashing over word unigrams and bigrams.

    The vector is deterministic, needs no network, and is L2-normalized so an
    inner product is cosine similarity. It is a retrieval feature, not a
    substitute for a hosted embedding model.
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        if dim < 32:
            raise ValueError("embedding dim must be at least 32")
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        from fintech_diligence.tokenize import tokenize

        vector = [0.0] * self.dim
        tokens = tokenize(text)
        pairs = zip(tokens, tokens[1:], strict=False)
        grams = tokens + [f"{left}_{right}" for left, right in pairs]
        for gram in grams:
            digest = hashlib.sha256(gram.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


class OpenAIEmbedder:
    """Hosted embeddings. Uses text-embedding-3-small at EMBEDDING_DIM."""

    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None) -> None:
        from openai import OpenAI

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAIEmbedder")
        self._client = OpenAI(api_key=key)
        self._model = model
        self.dim = EMBEDDING_DIM

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self.dim,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
