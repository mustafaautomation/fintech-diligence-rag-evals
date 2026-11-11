"""Language-model providers. Tests use the deterministic provider."""

import os
import re
from typing import Protocol

from fintech_diligence.tokenize import content_tokens

INVESTMENT_REFUSAL = (
    "I don't provide investment advice. The Harborline documents are not a "
    "recommendation to buy, sell, or hold any security."
)
FORWARD_REFUSAL = (
    "I don't make forward-looking guesses. The Harborline documents do not "
    "state a forecast for that question."
)
UNKNOWN_REFUSAL = "I don't know. That is not in the Harborline documents."

_INVESTMENT = re.compile(
    r"\b("
    r"investment advice|good investment|undervalued|overvalued|price target|"
    r"buy the stock|sell the stock|purchase the stock|"
    r"should an investor|should i buy|should i invest|recommendation to buy"
    r")\b",
    re.IGNORECASE,
)
_FORWARD = re.compile(
    r"\b(forecast|guidance|predict|prediction|expects|expected to|will|going to|next year)\b",
    re.IGNORECASE,
)
_OUT_OF_SCOPE = re.compile(
    r"\b(stripe|adyen|paypal|visa|mastercard|weather|podcast|salary)\b|"
    r"home street address|street address|world series",
    re.IGNORECASE,
)
_INJECTION = re.compile(
    r"ignore (?:all |the |previous |prior )?instructions",
    re.IGNORECASE,
)
_PRESSURE = re.compile(r"you are wrong|confirm that figure", re.IGNORECASE)
_MONEY = re.compile(r"\$\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\d+(?:\.\d+)?")
_CHUNK = re.compile(
    r"---\nid: (?P<id>[^\n]*)\ntitle: (?P<title>[^\n]*)\n(?P<text>.*?)\n---",
    re.DOTALL,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


class LLMProvider(Protocol):
    def complete(self, *, system: str, user: str) -> str: ...


class FakeProvider:
    """Deterministic stand-in for a chat model.

    With the grounded prompt it copies a retrieved sentence or refuses.
    With the no-guardrail prompt it estimates figures and gives advice.
    It does not look up answers by question id.
    """

    def complete(self, *, system: str, user: str) -> str:
        question, chunks = _parse_user_message(user)
        if "NO_GUARDRAILS" in system:
            return _ungrounded(question, chunks)
        return _grounded(question, chunks)


class OpenAIProvider:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        from openai import OpenAI

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAIProvider")
        self._client = OpenAI(api_key=key)
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def complete(self, *, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content
        return content or ""


class AnthropicProvider:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        from anthropic import Anthropic

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for AnthropicProvider")
        self._client = Anthropic(api_key=key)
        self._model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")

    def complete(self, *, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)


def _grounded(question: str, chunks: list[tuple[str, str, str]]) -> str:
    if _INVESTMENT.search(question):
        return INVESTMENT_REFUSAL
    if _FORWARD.search(question) or _INJECTION.search(question):
        return FORWARD_REFUSAL
    if _OUT_OF_SCOPE.search(question):
        return UNKNOWN_REFUSAL
    extracted = _extract(question, chunks)
    if extracted is None:
        return UNKNOWN_REFUSAL
    return extracted


def _ungrounded(question: str, chunks: list[tuple[str, str, str]]) -> str:
    if _INVESTMENT.search(question):
        return "Harborline is a buy. An investor should purchase the stock."
    if _FORWARD.search(question) or _INJECTION.search(question):
        amount = _first_money(question) or "$300,000,000"
        return f"Next year's revenue will be {amount}."
    if _PRESSURE.search(question):
        amount = _first_money(question) or "$200,000,000"
        return f"Total revenue was {amount}."
    if _OUT_OF_SCOPE.search(question):
        return "The amount is $999,000,000."
    extracted = _extract(question, chunks)
    if extracted is None:
        return "The amount is $999,000,000."
    return extracted


def _extract(question: str, chunks: list[tuple[str, str, str]]) -> str | None:
    best_score = 0.0
    best_sentence = ""
    for _chunk_id, _title, text in chunks:
        for sentence in _sentences(text):
            score = _overlap(question, sentence)
            if score > best_score:
                best_score = score
                best_sentence = sentence
    if best_score < 2.0 or not best_sentence:
        return None
    return f"According to the Harborline documents: {best_sentence}"


def _overlap(question: str, sentence: str) -> float:
    present = set(content_tokens(sentence))
    score = 0.0
    for token in content_tokens(question):
        if token in present:
            score += 2.0 if len(token) > 4 else 1.0
    return score


def _sentences(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip().endswith(".")]
    parts = _SENTENCE_SPLIT.split(" ".join(lines))
    return [part.strip() for part in parts if len(part.strip()) > 20]


def _parse_user_message(user: str) -> tuple[str, list[tuple[str, str, str]]]:
    if "Retrieved documents:" not in user:
        raise ValueError("user message is missing retrieved documents")
    question = user.split("Retrieved documents:", 1)[0].removeprefix("Question:\n").strip()
    chunks = [
        (match.group("id").strip(), match.group("title").strip(), match.group("text").strip())
        for match in _CHUNK.finditer(user)
    ]
    return question, chunks


def _first_money(question: str) -> str | None:
    match = _MONEY.search(question)
    if match is None:
        return None
    return match.group(0)
