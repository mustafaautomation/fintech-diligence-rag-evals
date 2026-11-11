# fintech-diligence-rag-evals

[![CI](https://github.com/mustafaautomation/fintech-diligence-rag-evals/actions/workflows/ci.yml/badge.svg)](https://github.com/mustafaautomation/fintech-diligence-rag-evals/actions/workflows/ci.yml)

Personal open-source demo by Muhammad Mustafa. It is a small RAG assistant for financial due-diligence questions about a made-up company, plus an evaluation gate built on [RAGAS](https://docs.ragas.io/) 0.4.3.

The company, Harborline Payments, Inc., and every figure in `data/corpus/` are synthetic. They were written for this repository. They are not taken from a real registrant, and they are not customer data.

## What it measures

The offline gate checks whether answers stick to the source documents.

| Metric | What it tells you |
| --- | --- |
| `numeric_accuracy` | Every figure in the answer matches a figure in the retrieved text. `$186.4 million` matches `$186,400,000`. A percent does not match the same digits written as a plain count. |
| `refusal_correctness` | Investment-advice, forecast, and out-of-scope questions are refused. Factual questions are not. |
| `trap_avoidance` | The answer does not repeat a figure the user tried to plant. |
| `string_presence` | RAGAS `StringPresence`: labelled phrases appear in the answer. |
| `hit_rate` | The labelled section is inside the top 4 chunks. |
| `mrr` | How high that section is ranked. |
| `non_llm_context_recall` | RAGAS `NonLLMContextRecall`: string similarity between retrieved sections and the labelled section. No model call. |
| `non_llm_context_precision` | RAGAS `NonLLMContextPrecisionWithReference`: whether string-similar sections are ranked above the others. |

Live mode adds the RAGAS collections metrics `Faithfulness`, `AnswerRelevancy`, `ContextPrecision`, and `ContextRecall`. Those call a judge model. This repository does not commit judge scores. No API key was available for a live run here, so those four metrics are not given numbers below.

`NonLLMContextRecall` and `NonLLMContextPrecisionWithReference` are still imported from `ragas.metrics`. RAGAS 0.4.3 prints a deprecation warning that points at `ragas.metrics.collections`, but that package does not export those two classes. `StringPresence` and the four LLM-judged metrics use the collections API. `evaluate()` in 0.4.3 rejects collections metrics ([ragas issue 2624](https://github.com/vibrantlabsai/ragas/issues/2624)), so live scoring calls `ascore` on each metric.

## Architecture

```mermaid
flowchart LR
  docs[Synthetic annual report] --> chunks[Section chunks]
  chunks --> embed[Hashing embedder]
  embed --> store[FAISS or pgvector]
  question[Question] --> store
  store --> prompt[Guardrail prompt]
  prompt --> provider[Fake, OpenAI, or Anthropic]
  provider --> metrics[Numeric, refusal, and retrieval checks]
  metrics --> gate[Threshold gate]
  gate --> report[Markdown and HTML report]
```

Default retrieval blends FAISS inner product with BM25. The vector weight is 0.30 in `evals/pipeline.toml`. If FAISS is not installed, the same scores are computed with NumPy. Postgres is optional.

The offline generator is `FakeProvider`. It is deterministic. With the guardrail prompt it copies a retrieved sentence or refuses. With the no-guardrail prompt it estimates figures and gives advice. It does not look up answers by question id. Live mode uses `OpenAIProvider` or `AnthropicProvider` behind the same `complete(system, user)` interface.

## Offline scores from this run

Scored from `data/snapshots/improved.jsonl` and `data/snapshots/baseline.jsonl` on the 42 labelled questions. Retrieval metrics use the 30 questions that have a labelled section. The other 12 are refusals.

Improved pipeline, gate pass:

| Metric | Score | Threshold | Samples |
| --- | ---: | ---: | ---: |
| numeric_accuracy | 1.000 | 1.000 | 42 |
| refusal_correctness | 1.000 | 1.000 | 42 |
| string_presence | 1.000 | 1.000 | 42 |
| trap_avoidance | 1.000 | 1.000 | 42 |
| hit_rate | 1.000 | 1.000 | 30 |
| mrr | 1.000 | 1.000 | 30 |
| non_llm_context_recall | 1.000 | 1.000 | 30 |
| non_llm_context_precision | 0.963 | 0.900 | 30 |

Baseline is the broken variant: it retrieves the lowest-scoring chunks and uses the prompt that allows estimates, investment advice, and forecasts. Gate fail:

| Metric | Baseline | Improved | Threshold |
| --- | ---: | ---: | ---: |
| numeric_accuracy | 0.167 | 1.000 | 1.000 |
| refusal_correctness | 0.714 | 1.000 | 1.000 |
| string_presence | 0.000 | 1.000 | 1.000 |
| trap_avoidance | 0.976 | 1.000 | 1.000 |
| hit_rate | 0.000 | 1.000 | 1.000 |
| mrr | 0.000 | 1.000 | 1.000 |
| non_llm_context_recall | 0.000 | 1.000 | 1.000 |
| non_llm_context_precision | 0.000 | 0.963 | 0.900 |

`non_llm_context_precision` on the improved run is 0.963 rather than 1.000. Six questions still answer with the labelled sentence, but a neighboring statement section is string-similar enough for the metric to treat it as another relevant hit below rank 1. The threshold is 0.900, which the improved run clears and the broken retriever does not.

![Offline evaluation report](docs/reports/offline_eval_report.png)

The same run is written to [docs/reports/offline_eval_report.md](docs/reports/offline_eval_report.md) and [docs/reports/offline_eval_report.html](docs/reports/offline_eval_report.html).

Thresholds live in `evals/thresholds.toml`. The `[live]` values, 0.70 for each LLM-judged metric, are starting points. They were not measured on this corpus.

Two narrower broken variants are covered by tests, not by the report table:

- `bad-retriever` keeps the guardrail prompt and returns the lowest-scoring chunks. Hit rate, MRR, and both non-LLM context metrics are 0. The gate fails.
- `no-guardrail` keeps hybrid retrieval and drops the guardrails. Hit rate stays 1.000. Numeric accuracy, refusal correctness, string presence, and trap avoidance fall below their thresholds. The gate fails.

## Run locally

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
uv run diligence ask "What was total revenue for the year ended December 31, 2025?"
uv run diligence eval --mode offline
```

Offline mode reads the committed snapshots, prints the scores, and exits non-zero if any improved-pipeline metric is below its threshold. It does not call an API.

```bash
uv run diligence eval --mode offline --variant baseline
```

That command is expected to exit 1. It is how the gate shows that the broken variant fails.

Rebuild the snapshots after you change the corpus, the questions, or the pipeline:

```bash
uv run diligence eval --rebuild --variant improved
uv run diligence eval --rebuild --variant baseline
uv run diligence eval --mode offline --write-report docs/reports
```

Live mode needs `OPENAI_API_KEY`. It answers with OpenAI, then scores the four RAGAS collections metrics plus the offline metrics. The judge model defaults to `gpt-4o-mini` (`OPENAI_JUDGE_MODEL`). There is no checked-in judge output.

```bash
export OPENAI_API_KEY=...
uv run diligence eval --mode live
```

`AnthropicProvider` is the same interface, using `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`.

### Postgres with pgvector

```bash
docker compose up -d
export DILIGENCE_DATABASE_URL=postgresql://diligence:diligence@localhost:5432/diligence
```

The password in `docker-compose.yml` is for this local database only.

```python
from fintech_diligence.embeddings import HashingEmbedder
from fintech_diligence.pipeline import build_chunks
from fintech_diligence.retrievers import PgVectorRetriever, connect_postgres

chunks = build_chunks()
connection = connect_postgres("postgresql://diligence:diligence@localhost:5432/diligence")
retriever = PgVectorRetriever(connection, chunks, HashingEmbedder())
retriever.ensure_schema()
retriever.index()
print(retriever.search("total revenue 2025", k=4))
```

Tests use the FAISS index and do not need Docker.

## Guardrails

The grounded prompt tells the model to do three things:

- State a number only when that number is in the retrieved documents.
- Refuse investment advice. No buy, sell, hold, price target, or valuation view.
- Refuse forward-looking guesses. A completed subsequent event that the report already states, such as the February 9, 2026 Ledgerlane purchase, can be answered as a fact. A question about 2026 revenue cannot.

Out-of-scope questions, including other companies and personal data, are refused with "I don't know. That is not in the Harborline documents."

## Corpus and questions

`data/corpus/` has 22 short markdown notes: the annual report, financial statements, and risk disclosures. `data/eval/questions.jsonl` has 42 questions. Thirty have a reference answer and the sentence that locates the gold section. Twelve should be refused: investment advice, forecasts, prompt injection, and questions the documents do not cover. One factual question tries to push a revenue figure of `$200,000,000`, which is not in the statements.

## How to point this at another document set

1. Replace the markdown files in `data/corpus/` with the new documents. Keep them clearly sourced. If they are not synthetic, say where they came from and the license.
2. Replace `data/eval/questions.jsonl`. For each factual question, set `passages` to a sentence that appears in exactly one section, `reference_phrases` to the strings the answer must contain, and `expected_behavior` to `answer`. For refusals, leave `passages` empty and set `expected_behavior` to `refuse`.
3. Edit the guardrail text in `src/fintech_diligence/prompts.py` if the refusal rules differ.
4. Rebuild the snapshots and read the new scores.
5. Set `evals/thresholds.toml` from that run. The broken variants in `src/fintech_diligence/pipeline.py` (`bad-retriever`, `no-guardrail`, `baseline`) are there so a test can show the gate failing.
6. For LLM-judged scores, set `OPENAI_API_KEY` and run `uv run diligence eval --mode live`. GitHub Actions runs that only from `workflow_dispatch`, and only when the `OPENAI_API_KEY` secret is set.

CI on pull requests runs ruff, mypy, pytest, and `diligence eval --mode offline`. Each job fails the workflow if it fails.

## License

MIT. See [LICENSE](LICENSE).
