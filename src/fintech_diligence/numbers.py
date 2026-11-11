"""Parse figures and check that an answer does not introduce new ones."""

import re
from dataclasses import dataclass
from decimal import Decimal

_NUMBER = re.compile(
    r"""
    (?P<prefix>\$)?
    (?P<num>\d{1,3}(?:,\d{3})+|\d+)
    (?:\.(?P<frac>\d+))?
    (?:\s*(?P<scale>billion|million|thousand|basis\s+points|bps|percentage\s+points|percent|%))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_ONE = Decimal(1)
_QUANT = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class Mention:
    """A number found in text, scaled to a base unit when the words say so."""

    value: Decimal
    kind: str
    fraction: Decimal | None = None


def parse_mentions(text: str) -> list[Mention]:
    mentions: list[Mention] = []
    for match in _NUMBER.finditer(text):
        number = Decimal(match.group("num").replace(",", ""))
        if match.group("frac"):
            number = Decimal(f"{match.group('num').replace(',', '')}.{match.group('frac')}")
        scale = (match.group("scale") or "").lower().strip()
        scale = re.sub(r"\s+", " ", scale)
        has_dollar = match.group("prefix") is not None
        if scale == "billion":
            mentions.append(_scaled(number, 1_000_000_000, has_dollar))
        elif scale == "million":
            mentions.append(_scaled(number, 1_000_000, has_dollar))
        elif scale == "thousand":
            mentions.append(_scaled(number, 1_000, has_dollar))
        elif scale in {"%", "percent"}:
            fraction = _q(number / Decimal(100))
            mentions.append(Mention(_q(number), "rate", fraction=fraction))
        elif scale in {"basis points", "bps"}:
            fraction = _q(number / Decimal(10_000))
            mentions.append(Mention(_q(number), "rate", fraction=fraction))
        elif scale == "percentage points":
            mentions.append(Mention(_q(number), "plain"))
        elif has_dollar:
            mentions.append(Mention(_q(number), "money"))
        else:
            mentions.append(Mention(_q(number), "plain"))
    return mentions


def _scaled(number: Decimal, factor: int, has_dollar: bool) -> Mention:
    kind = "money" if has_dollar else "magnitude"
    return Mention(_q(number * Decimal(factor)), kind)


def mentions_match(left: Mention, right: Mention) -> bool:
    if left.kind == "rate" and right.kind == "rate":
        return left.fraction == right.fraction
    if left.kind == "rate" and right.kind == "plain":
        return right.value == left.fraction
    if right.kind == "rate" and left.kind == "plain":
        return left.value == right.fraction
    return left.value == right.value


def numeric_accuracy(
    response: str,
    source_text: str,
    *,
    question: str = "",
    allow_question_numbers: bool = False,
) -> float:
    """Share of response figures that also appear in the source.

    Refusals may echo a number from the question. Factual answers may not:
    a figure has to be present in the retrieved documents.
    """
    response_mentions = parse_mentions(response)
    if not response_mentions:
        return 1.0
    source = source_text
    if allow_question_numbers and question:
        source = f"{source_text}\n{question}"
    source_mentions = parse_mentions(source)
    supported = 0
    for mention in response_mentions:
        if any(mentions_match(mention, candidate) for candidate in source_mentions):
            supported += 1
    return supported / len(response_mentions)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANT) / _ONE
