# IS Sarthi

**AI-Powered Recommendation Engine for Identifying Applicable Indian Standards for Procurement Specifications**

SIH 2026 — Bureau of Indian Standards (BIS) Problem Statement

---

## What this is

Procurement officials drafting tender specifications must cite the correct Indian Standards (IS). Today that means keyword search on the BIS portal plus institutional memory. The result: missed allied standards, outdated version citations, and unflagged mandatory certification requirements — which lead to ambiguity, poor product quality, and procurement disputes.

IS Sarthi accepts a plain-language product description or a tender document and returns:

- The most relevant IS standard(s), matched on **semantic meaning**, not keywords
- **Allied standards** — normative references, test methods, terminology, safety, installation
- The **latest published version** and amendment history
- **Mandatory certification** flags (BIS Product Certification, CRS, Hallmarking)
- A **plain-language justification** for every recommendation

Backed by a **self-updating real-time data pipeline** that keeps the standards corpus, citation graph, and certification rules current without manual intervention.

---

## Repository layout

```
is-sarthi/
├── docs/                    Product, technical, and design documentation
│   ├── PRD.md               Product requirements
│   ├── TRD.md               Technical requirements + architecture
│   ├── UI_UX.md             Design system, screens, flows
│   ├── DATA_SOURCES.md      Every source, legal basis, extraction method
│   ├── EVALUATION.md        How retrieval quality is measured
│   ├── DEMO_SCRIPT.md       Judge-facing demo runbook
│   └── ROADMAP.md           MVP → pilot → production
├── pipeline/                Real-time ingestion & sync
│   ├── config.py            Pydantic settings
│   ├── celery_app.py        Task queue + beat schedule
│   ├── change_detector.py   Content-hash change detection
│   ├── scrapers/            BIS portal, Manak, CRS, Gazette, GeM
│   ├── tasks/               Scrape → clean → graph → embed → store
│   ├── db/                  Postgres, Neo4j, Chroma clients
│   └── utils/               IS-number normalization, rate limiting
├── api/                     FastAPI recommendation service
│   ├── main.py
│   ├── routers/             /recommend, /standards, /health, /admin
│   └── services/            Retrieval, graph expansion, reranking, LLM
├── ui/                      Streamlit prototype interface
├── data/seed/               Bootstrap corpus (works with zero scraping)
├── scripts/                 Bootstrap, backfill, eval runners
├── tests/                   Unit + retrieval regression tests
└── deploy/                  Docker Compose, schema, Makefile
```

---

## Quick start (demo in 5 minutes, no scraping required)

```bash
# 1. Bring up infrastructure
cd deploy && docker compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Load the seed corpus and build embeddings
python scripts/bootstrap.py

# 4. Start the API
uvicorn api.main:app --reload --port 8000

# 5. Start the UI (new terminal)
streamlit run ui/app.py
```

Open http://localhost:8501. The seed corpus ships with the repo, so the demo works offline — the live pipeline is additive, not a prerequisite.

---

## Running the live pipeline

```bash
# Workers (three queues, independently scaled)
celery -A pipeline.celery_app worker -Q scrape  --concurrency=4 &
celery -A pipeline.celery_app worker -Q process --concurrency=2 &
celery -A pipeline.celery_app worker -Q embed   --concurrency=2 &

# Scheduler
celery -A pipeline.celery_app beat &

# Monitoring UI at localhost:5555
celery -A pipeline.celery_app flower
```

Trigger a sync manually:

```bash
python scripts/trigger_sync.py --mode delta     # recent changes only
python scripts/trigger_sync.py --mode full      # full catalog crawl
```

---

## Important note on scrapers

The scrapers in `pipeline/scrapers/` are **selector-configuration driven** (see `pipeline/scrapers/selectors.yaml`). BIS does not publish a public API, and its page structure is not contractually stable. The selectors shipped here are a starting point and **must be validated against the live DOM** before a production run — `scripts/validate_selectors.py` does exactly that and reports which selectors resolve.

This is a deliberate design choice, not an omission: isolating selectors into config means a BIS site change is a one-file edit, not a code change.

See `docs/DATA_SOURCES.md` for the legal basis, rate-limiting policy, and per-source extraction detail.
