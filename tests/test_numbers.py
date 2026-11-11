from fintech_diligence.numbers import mentions_match, numeric_accuracy, parse_mentions


def test_dollar_millions_match_exact_dollars() -> None:
    source = parse_mentions("Total revenue was $186,400,000.")
    answer = parse_mentions("Revenue was $186.4 million.")
    assert any(mentions_match(answer[0], item) for item in source)


def test_basis_points_match_equivalent_percent() -> None:
    source = parse_mentions("The reported take rate was 65.0 basis points.")
    answer = parse_mentions("The take rate was 0.65%.")
    assert any(mentions_match(answer[0], item) for item in source)


def test_percentage_points_do_not_match_a_percent() -> None:
    source = parse_mentions("The spread was 2.75 percentage points.")
    answer = parse_mentions("The spread was 2.75%.")
    assert not any(mentions_match(answer[0], item) for item in source)


def test_plain_count_does_not_match_a_percent() -> None:
    source = parse_mentions("The share was 11.2%.")
    answer = parse_mentions("The share was 11.2.")
    assert not any(mentions_match(answer[0], item) for item in source)


def test_invented_figure_fails_numeric_accuracy() -> None:
    score = numeric_accuracy(
        "Next year's revenue will be $300,000,000.",
        "Total revenue for the year ended December 31, 2025 was $186,400,000.",
    )
    assert score == 0.0


def test_copied_sentence_is_numerically_exact() -> None:
    source = "Net income for the year ended December 31, 2025 was $16,906,000."
    assert numeric_accuracy(source, source) == 1.0


def test_refusal_may_echo_a_number_from_the_question() -> None:
    score = numeric_accuracy(
        "I can't forecast 2026.",
        "The fiscal year ended on December 31, 2025.",
        question="What will 2026 revenue be?",
        allow_question_numbers=True,
    )
    assert score == 1.0


def test_factual_answer_may_not_reuse_a_number_only_the_user_stated() -> None:
    score = numeric_accuracy(
        "Total revenue was $200,000,000.",
        "Total revenue for the year ended December 31, 2025 was $186,400,000.",
        question="Confirm that total revenue was $200,000,000.",
        allow_question_numbers=False,
    )
    assert score == 0.0
