"""Live RAGAS metrics using the collections API in ragas 0.4.3.

`evaluate()` in this version still type-checks the legacy Metric base class and
rejects collections metrics (ragas issue 2624). The supported path is `ascore`
on Faithfulness, AnswerRelevancy, ContextPrecision, and ContextRecall.
"""

import asyncio
import os
from typing import Protocol

from fintech_diligence.metrics import SampleScore
from fintech_diligence.types import AnswerRecord

LIVE_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)


class LiveJudge(Protocol):
    def score_many(self, records: list[AnswerRecord]) -> list[dict[str, float]]: ...


class RagasJudge:
    """Call the current collections metrics with an OpenAI client."""

    def __init__(self, model: str | None = None) -> None:
        from openai import AsyncOpenAI
        from ragas.embeddings import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for live RAGAS scoring")
        judge_model = model or os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4o-mini")
        client = AsyncOpenAI()
        llm = llm_factory(judge_model, client=client)
        embeddings = embedding_factory(
            "openai",
            model="text-embedding-3-small",
            client=client,
        )
        self._faithfulness = Faithfulness(llm=llm)
        self._relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings, strictness=3)
        self._precision = ContextPrecision(llm=llm)
        self._recall = ContextRecall(llm=llm)

    def score_many(self, records: list[AnswerRecord]) -> list[dict[str, float]]:
        return asyncio.run(self._score_all(records))

    async def _score_all(self, records: list[AnswerRecord]) -> list[dict[str, float]]:
        scored: list[dict[str, float]] = []
        for record in records:
            scored.append(await self._score_one(record))
        return scored

    async def _score_one(self, record: AnswerRecord) -> dict[str, float]:
        contexts = list(record.retrieved_contexts)
        scores: dict[str, float] = {}
        if record.response and contexts:
            faith = await self._faithfulness.ascore(
                user_input=record.question,
                response=record.response,
                retrieved_contexts=contexts,
            )
            scores["faithfulness"] = float(faith.value)
            relevancy = await self._relevancy.ascore(
                user_input=record.question,
                response=record.response,
            )
            scores["answer_relevancy"] = float(relevancy.value)
        if record.reference_answer and contexts:
            precision = await self._precision.ascore(
                user_input=record.question,
                reference=record.reference_answer,
                retrieved_contexts=contexts,
            )
            scores["context_precision"] = float(precision.value)
            recall = await self._recall.ascore(
                user_input=record.question,
                retrieved_contexts=contexts,
                reference=record.reference_answer,
            )
            scores["context_recall"] = float(recall.value)
        return scores


def attach_live_scores(samples: list[SampleScore], live_rows: list[dict[str, float]]) -> None:
    if len(samples) != len(live_rows):
        raise ValueError("Live scores do not line up with offline samples")
    for sample, row in zip(samples, live_rows, strict=True):
        sample.scores.update(row)
