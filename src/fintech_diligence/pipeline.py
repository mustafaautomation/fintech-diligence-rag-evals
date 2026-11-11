"""Wire the corpus, retriever, prompt, and provider into one ask path."""

import tomllib
from pathlib import Path

from fintech_diligence.chunking import chunk_documents
from fintech_diligence.corpus import load_corpus
from fintech_diligence.embeddings import Embedder, HashingEmbedder
from fintech_diligence.paths import corpus_dir, pipeline_config_path
from fintech_diligence.prompts import GROUNDED_SYSTEM, UNGROUNDED_SYSTEM, format_user_message
from fintech_diligence.providers import FakeProvider, LLMProvider, OpenAIProvider
from fintech_diligence.retrievers import BadRetriever, HybridRetriever, Retriever
from fintech_diligence.types import AnswerRecord, Chunk, EvalQuestion, Hit

VARIANTS = ("improved", "bad-retriever", "no-guardrail", "baseline")


class Pipeline:
    def __init__(
        self,
        retriever: Retriever,
        provider: LLMProvider,
        system_prompt: str,
        chunks: list[Chunk],
        top_k: int = 4,
    ) -> None:
        self.retriever = retriever
        self.provider = provider
        self.system_prompt = system_prompt
        self.chunks = chunks
        self.top_k = top_k
        self._by_id = {chunk.id: chunk for chunk in chunks}

    def ask(self, question: str) -> tuple[str, list[Hit]]:
        hits = self.retriever.search(question, self.top_k)
        user = format_user_message(
            question,
            [(hit.chunk.id, hit.chunk.title, hit.chunk.text) for hit in hits],
        )
        response = self.provider.complete(system=self.system_prompt, user=user)
        return response, hits

    def answer_question(self, item: EvalQuestion) -> AnswerRecord:
        response, hits = self.ask(item.question)
        reference_chunks = resolve_reference_chunks(self.chunks, item.passages)
        return AnswerRecord(
            id=item.id,
            question=item.question,
            response=response,
            retrieved_chunk_ids=tuple(hit.chunk.id for hit in hits),
            retrieved_contexts=tuple(hit.chunk.text for hit in hits),
            reference_chunk_ids=tuple(chunk.id for chunk in reference_chunks),
            reference_contexts=tuple(chunk.text for chunk in reference_chunks),
            reference_phrases=item.reference_phrases,
            forbidden_phrases=item.forbidden_phrases,
            expected_behavior=item.expected_behavior,
            reference_answer=item.reference_answer,
            tags=item.tags,
        )


def resolve_reference_chunks(chunks: list[Chunk], passages: tuple[str, ...]) -> list[Chunk]:
    if not passages:
        return []
    matched = [chunk for chunk in chunks if all(passage in chunk.text for passage in passages)]
    if len(matched) != 1:
        joined = " | ".join(passages)
        raise ValueError(f"Expected one chunk for {joined!r}, found {len(matched)}")
    return matched


def load_pipeline_settings(path: Path | None = None) -> tuple[int, float]:
    config_path = path or pipeline_config_path()
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    top_k = int(data["top_k"])
    vector_weight = float(data["vector_weight"])
    return top_k, vector_weight


def build_chunks() -> list[Chunk]:
    return chunk_documents(load_corpus(corpus_dir()))


def build_pipeline(
    variant: str = "improved",
    *,
    provider: LLMProvider | None = None,
    embedder: Embedder | None = None,
    top_k: int | None = None,
    vector_weight: float | None = None,
) -> Pipeline:
    if variant not in VARIANTS and variant != "live":
        raise ValueError(f"Unknown variant {variant!r}")
    configured_k, configured_weight = load_pipeline_settings()
    k = configured_k if top_k is None else top_k
    weight = configured_weight if vector_weight is None else vector_weight
    chunks = build_chunks()
    vectors = embedder or HashingEmbedder()
    if variant == "live":
        retriever: Retriever = HybridRetriever(chunks, vectors, vector_weight=weight)
        chosen = provider or OpenAIProvider()
        prompt = GROUNDED_SYSTEM
    elif variant == "improved":
        retriever = HybridRetriever(chunks, vectors, vector_weight=weight)
        chosen = provider or FakeProvider()
        prompt = GROUNDED_SYSTEM
    elif variant == "bad-retriever":
        retriever = BadRetriever(chunks, vectors, vector_weight=weight)
        chosen = provider or FakeProvider()
        prompt = GROUNDED_SYSTEM
    elif variant == "no-guardrail":
        retriever = HybridRetriever(chunks, vectors, vector_weight=weight)
        chosen = provider or FakeProvider()
        prompt = UNGROUNDED_SYSTEM
    else:
        retriever = BadRetriever(chunks, vectors, vector_weight=weight)
        chosen = provider or FakeProvider()
        prompt = UNGROUNDED_SYSTEM
    return Pipeline(retriever, chosen, prompt, chunks, top_k=k)
