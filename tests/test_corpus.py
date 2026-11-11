from fintech_diligence.chunking import chunk_documents
from fintech_diligence.corpus import load_corpus
from fintech_diligence.evalset import load_questions
from fintech_diligence.paths import corpus_dir
from fintech_diligence.pipeline import resolve_reference_chunks


def test_corpus_size_and_synthetic_notice() -> None:
    documents = load_corpus(corpus_dir())
    assert 15 <= len(documents) <= 30
    combined = "\n".join(document.text for document in documents)
    assert "fictional" in combined
    for invented in ("$200,000,000", "$300,000,000", "$999,000,000", "$50,000,000"):
        assert invented not in combined


def test_statement_amounts_tie_and_appear_in_the_corpus() -> None:
    documents = load_corpus(corpus_dir())
    combined = "\n".join(document.text for document in documents)
    assert 121_875_000 + 41_225_000 + 23_300_000 == 186_400_000
    assert 16_906_000 / 42_265_000 == 0.40
    assert 121_875_000 / 18_750_000_000 == 0.0065
    assert 98_600_000 + 210_400_000 + 14_200_000 + 6_300_000 == 329_500_000
    assert 268_100_000 + 144_400_000 == 412_500_000
    for snippet in (
        "$186,400,000",
        "$16,906,000",
        "$412,500,000",
        "$18,750,000,000",
        "65.0 basis points",
        "Northwind Retail Group",
        "Ledgerlane Analytics, Inc.",
        "June 30, 2027",
    ):
        assert snippet in combined


def test_questions_are_in_range_and_passages_match_one_chunk() -> None:
    questions = load_questions()
    assert 30 <= len(questions) <= 50
    refusals = [item for item in questions if item.expected_behavior == "refuse"]
    answers = [item for item in questions if item.expected_behavior == "answer"]
    assert len(refusals) >= 8
    assert len(answers) >= 20
    chunks = chunk_documents(load_corpus(corpus_dir()))
    for item in questions:
        matched = resolve_reference_chunks(chunks, item.passages)
        if item.expected_behavior == "answer":
            assert matched
            assert item.passages[0] in matched[0].text
        else:
            assert matched == []
