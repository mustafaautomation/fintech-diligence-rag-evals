"""Token helpers shared by retrieval and the offline answerer."""

import re

_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "for",
        "to",
        "and",
        "or",
        "in",
        "on",
        "was",
        "were",
        "what",
        "which",
        "who",
        "did",
        "does",
        "is",
        "are",
        "be",
        "by",
        "with",
        "from",
        "that",
        "this",
        "as",
        "at",
        "it",
        "its",
        "their",
        "our",
        "how",
        "many",
        "much",
        "when",
        "where",
        "do",
        "about",
        "into",
        "than",
        "then",
        "during",
        "under",
        "any",
        "harborline",
        "payments",
        "inc",
        "company",
    }
)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def content_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOPWORDS]
