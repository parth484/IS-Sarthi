# Technical Requirements Document

## IS Sarthi — Architecture & Implementation Specification

**Version:** 2.0

---

## 1. Architectural Overview

Five planes, independently scalable:

```
┌──────────────────────────────────────────────────────────────┐
│  INGESTION PLANE  (Celery workers + Beat scheduler)          │
│  BIS Portal │ Manak │ IS PDFs │ CRS List │ e-Gazette │ GeM   │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  PROCESSING PLANE                                            │
│  normalize → change-detect → classify → extract refs → embed │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  STORAGE PLANE                                               │
│  PostgreSQL (truth + audit) │ Neo4j (graph) │ Chroma (vectors)│
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  REASONING PLANE                                             │
│  hybrid retrieve → graph expand → rerank → LLM justify       │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  DELIVERY PLANE                                              │
│  FastAPI │ Streamlit UI │ Portal integration API             │
└──────────────────────────────────────────────────────────────┘
```

**Why three stores rather than one.** Each answers a structurally different question. Postgres answers "what is true about IS 1554 right now, and what was true last month" — it is the system of record and the audit substrate. Neo4j answers "what is the normative closure of IS 1554 to depth 2, classified by edge type" — a recursive traversal that is expensive and awkward in SQL and impossible in a vector store. Chroma answers "what standards mean something similar to this spec text." Collapsing these into one store would force at least one of the three queries into a shape it handles badly. They are updated by the same task chain, so consistency is maintained at write time.

## 2. Technology Selection

| Layer | Choice | Rationale |
|---|---|---|
| Task queue | Celery + Redis | Mature retry/backoff, queue routing, rate limiting; Beat gives persistent cron |
| Relational | PostgreSQL 15 | JSONB for semi-structured metadata, triggers for audit, mature ops |
| Graph | Neo4j 5 | Native variable-depth traversal with typed edges; Cypher is legible to reviewers |
| Vectors | ChromaDB | Simple to self-host, metadata filtering, adequate to ~100k docs |
| Embeddings | `intfloat/multilingual-e5-base` (primary), `l3cube-pune/indic-sentence-similarity-sbert` (Indic fallback) | Open weights → on-prem deployable; multilingual without a translation hop |
| Lexical retrieval | BM25 (`rank_bm25`) | IS numbers and part designators are exact tokens where lexical beats dense |
| Reranking | `BAAI/bge-reranker-base` cross-encoder | Large precision gain over bi-encoder similarity for a small latency cost |
| Reasoning | Pluggable LLM adapter (hosted API or local Llama/Mistral) | Sovereignty requirement — no hard dependency on an external provider |
| API | FastAPI | Async, Pydantic validation, auto OpenAPI for portal integrators |
| UI | Streamlit (prototype) → React (production) | Streamlit maximizes demo velocity; React is the pilot path |
| Document parsing | `pdfplumber`, `unstructured` | Scope-section and normative-reference extraction from IS/tender PDFs |

## 3. Retrieval Architecture

The pipeline is deliberately four stages. A single vector search is the obvious approach and it underperforms on this corpus for a specific reason: IS scope text is short, formal, and lexically homogeneous, so dense similarity alone produces tightly clustered scores that do not discriminate well between sibling standards.

### Stage 1 — Hybrid candidate retrieval
Dense (e5) and sparse (BM25) retrieval run in parallel; results are fused with Reciprocal Rank Fusion:

```
RRF(d) = Σ_r  1 / (k + rank_r(d))      k = 60
```

Dense catches paraphrase ("armoured underground cable" → XLPE cable standard). Sparse catches exact designators ("IS 1554 Part 1", "Class H insulation"). Fusion needs no score calibration between the two, which is why RRF is preferred to weighted score blending.

Retrieve top-50 candidates.

### Stage 2 — Cross-encoder reranking
The 50 candidates are scored jointly with the query by `bge-reranker-base`. Take top-10. This is where most precision is gained.

### Stage 3 — Graph expansion
For each surviving candidate, traverse Neo4j to depth 2 over `REFERENCES` edges. Each allied standard is classified by role using the edge's `ref_type` property, which is inferred at ingestion from the referencing clause context and the target's title pattern:

| Role | Inference signal |
|---|---|
| `test_method` | Title contains "Methods of test", "Method of sampling" |
| `terminology` | Title contains "Glossary of terms", "Terminology" |
| `safety` | Title contains "Safety requirements", cited under a safety clause |
| `installation` | Title contains "Code of practice", "Installation" |
| `related_product` | Default for product-specification targets |

Allied standards are ranked by a combined score: `0.6 × (1/hop_distance) + 0.4 × semantic_similarity_to_query`. Pure adjacency over-weights terminology standards, which are cited by nearly everything and are rarely the useful answer.

### Stage 4 — Constrained generation
A single LLM call receives the query plus the top-k standards *with their scope text* and returns structured JSON. The prompt constrains the model to justify using only supplied context and to emit `insufficient_context` rather than guess. No standard appears in output that was not retrieved — generation cannot invent an IS number.

### Confidence calibration
Confidence is not the raw cross-encoder logit. It combines rerank score, dense–sparse agreement, and margin over the runner-up:

```
confidence = 0.5·norm(rerank) + 0.2·agreement + 0.3·margin
```

Bucketed for display: ≥0.75 High, ≥0.50 Medium, else Low. Below 0.35 the system returns the no-confident-match state (FR-204).

## 4. Data Model

### 4.1 PostgreSQL

See `deploy/schema.sql` for the executable DDL. Core tables:

- `is_standards` — system of record; content hash for change detection; JSONB for amendments, references, certification
- `is_standards_audit` — trigger-populated change log satisfying FR-704
- `certification_rules` — IS number → scheme, with gazette citation and effective date
- `recommendation_log` — every served recommendation with corpus version (auditability NFR)
- `feedback` — accept/reject signal per recommendation (FR-604), the training substrate for a future learned reranker
- `sync_runs` — per-run extraction statistics, used for scraper-health alerting

### 4.2 Neo4j

```cypher
(:Standard {is_number, title, year, status, division})
  -[:REFERENCES {ref_type, hop_context}]-> (:Standard)
  -[:SUPERSEDES]-> (:Standard)
  -[:AMENDED_BY {number, date}]-> (:Amendment)
```

### 4.3 ChromaDB

Collection `is_standards`. Embedded text is `title + ". " + scope` — title alone is too terse, scope alone loses the product name. Metadata carries `is_number`, `status`, `division`, `year`, `certification_scheme` to permit pre-filtering (e.g. exclude withdrawn standards from retrieval unless explicitly requested).

## 5. Real-Time Data Pipeline

### 5.1 Schedules

| Job | Cadence | Purpose |
|---|---|---|
| `full_sync` | Weekly, Sun 02:00 | Complete catalog crawl; catches anything missed |
| `delta_sync` | Daily, 06:00 | "Recently published" page — new and revised standards |
| `check_gazette_updates` | Daily, 08:00 | e-Gazette notifications affecting certification regime |
| `refresh_crs_list` | Weekly, Mon 03:00 | CRS mandatory product list |
| `health_check` | Hourly | Selector resolution rate; alerts on extraction-rate drop |

### 5.2 Change detection

Each record is hashed over the fields that matter downstream (title, year, status, amendments, normative references). If the hash matches what is stored, only `last_seen` is touched and the record does not enter the processing chain. This is what makes daily syncing affordable: a full crawl touches every record but reprocesses only the handful that actually changed. Embedding regeneration — the expensive step — is additionally gated on the scope text itself having changed.

### 5.3 Task chain

```
scrape_standard
   └─(if changed)→ clean_and_validate
                     └→ classify_references
                          └→ update_graph
                               └→ regenerate_embedding
                                    └→ update_postgres
                                         └→ emit_change_event
```

Each task is independently retryable with exponential backoff. Queue routing separates `scrape` (IO-bound, rate-limited), `process` (CPU-light), and `embed` (CPU/GPU-heavy) so that embedding backlog never starves crawling.

### 5.4 Politeness and resilience

- Token-bucket rate limiter, default 1 request / 1.5s per source, configurable
- `robots.txt` respected; identifying User-Agent with contact address
- Exponential backoff with jitter on 429/5xx
- Circuit breaker: a source failing above threshold is disabled and alerted rather than hammered
- Raw HTML snapshots retained for reprocessing, so a parser fix does not require re-crawling

### 5.5 Selector configuration

All DOM selectors live in `pipeline/scrapers/selectors.yaml`. `scripts/validate_selectors.py` fetches a sample page per source and reports which selectors resolve. A BIS layout change becomes a config edit plus a validation run — not a code change and not a silent data outage.

## 6. API Specification

```
POST /api/v1/recommend          text query → recommendations
POST /api/v1/recommend/document multipart upload → per-line-item recommendations
GET  /api/v1/standards/{is_no}  full record incl. graph neighbourhood
GET  /api/v1/standards/{is_no}/graph  dependency graph for visualization
POST /api/v1/validate-spec      paste a spec → flag outdated/withdrawn citations
POST /api/v1/feedback           accept/reject signal
GET  /api/v1/changes?since=     corpus changelog (FR-705)
GET  /health, /health/pipeline  liveness + sync freshness
```

Request/response schemas are Pydantic models in `api/schemas.py`; OpenAPI is auto-generated at `/docs`.

## 7. Multilingual Handling

Language is detected on input. `multilingual-e5-base` embeds Indic-script and romanized queries into the same space as the English corpus, so no translation step is required for retrieval. Only the justification is generated in the user's language, by instructing the LLM in the system prompt. This ordering matters: translating the query before retrieval would introduce error at the most precision-sensitive step.

## 8. Security & Deployment

- Tender content may be pre-publication and commercially sensitive: uploaded documents are processed in memory and not persisted unless the user opts in.
- The LLM adapter supports a local model target, so no specification text need leave the deployment boundary.
- API authentication via API key for portal integrators; per-key rate limiting.
- Full stack runs via `deploy/docker-compose.yml`; no managed-cloud dependency.

## 9. Evaluation

See `docs/EVALUATION.md`. Summary: a labelled set of (spec text → expected IS numbers) pairs, scored on Recall@1/3/5, MRR, allied-standard recall, and a manual justification-faithfulness rating. `scripts/run_eval.py` runs it and writes a comparison report so retrieval changes are measured, not asserted.

## 10. Known Limitations

Stated plainly, because judges will find them anyway:

1. Scraper selectors are unvalidated against the live BIS DOM and will require adjustment.
2. Only scope text is available for most standards; full-text clause matching needs a BIS licence.
3. Reference-role classification is heuristic, not learned — accuracy is untested at scale.
4. Confidence weights are hand-set, not fitted; fitting requires the feedback dataset the system is designed to collect.
5. GeM integration is specified but not implemented — no public write API is available.
