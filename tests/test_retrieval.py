from fintech_diligence.embeddings import HashingEmbedder
from fintech_diligence.pipeline import build_chunks, build_pipeline


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder()
    first = embedder.embed_query("customer funds payable")
    second = embedder.embed_query("customer funds payable")
    assert first == second
    assert len(first) == embedder.dim
    norm = sum(value * value for value in first) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_improved_retriever_uses_faiss_and_ranks_the_gold_chunk_first() -> None:
    pipeline = build_pipeline("improved")
    assert pipeline.retriever.backend == "faiss"
    hits = pipeline.retriever.search(
        "What was total revenue for the year ended December 31, 2025?",
        pipeline.top_k,
    )
    assert hits[0].chunk.id == "income-statement#total-revenue"


def test_bad_retriever_excludes_the_gold_chunk() -> None:
    improved = build_pipeline("improved")
    broken = build_pipeline("bad-retriever")
    question = "What was net income for the year ended December 31, 2025?"
    gold = improved.retriever.search(question, 1)[0].chunk.id
    missed = {hit.chunk.id for hit in broken.retriever.search(question, improved.top_k)}
    assert gold not in missed
    assert len(build_chunks()) >= 30
