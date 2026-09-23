# Roadmap

## Now — internal round (3 days)

Working vertical slice on the seed corpus: hybrid retrieval, graph expansion,
certification flags, justification, currency warnings, validator, Streamlit UI,
eval harness. Pipeline code complete but running against seed data.

**Deliberately deferred:** dependency-graph visualization, admin screens, export
drawer, React rebuild, GeM integration. These are specified in the UI/UX doc so
the finals build has no design ambiguity to resolve — deferral is scope
discipline, not a gap.

## Next — finals (4–6 weeks)

Ordered by what most improves the submission per unit of effort:

1. **Validate selectors and run the live pipeline.** This converts the biggest
   stated limitation into a demonstrated capability. Highest priority by a
   distance.
2. **Two full divisions synced** (ETD, CED) — a defensible coverage claim
   ("all of Electrotechnical") beats a larger but arbitrary corpus.
3. **Re-run the eval at real scale** and publish the drop honestly. Showing the
   number falling from 100% to 82% as the corpus grows demonstrates that you
   understand your own system.
4. **Document upload** (FR-103) with per-line-item segmentation.
5. **Multilingual demo** — one rehearsed Hindi query end to end.
6. **Dependency-graph visualization.** This is the screen that makes the
   "dependency resolution, not search" argument visually. High demo value.
7. **Feedback loop live**, accumulating the labelled data everything below needs.

## Pilot (3 months)

One procuring department, full division coverage, API integration into their
drafting workflow, audit logging, on-premise deployment with a local model.

Success is measured on outcomes, not retrieval: time to finalize a tender's
standards section, pre-bid clarification queries about standards, and disputes
citing incorrect references.

## Production (6–12 months)

Full BIS catalogue. GeM integration. Amendment notification subsystem for
subscribed officials. A formal data-sharing arrangement with BIS replacing
scraping entirely — the architecture is unchanged, only `pipeline/scrapers/`
is swapped.

## Technical debt to retire, in order

| Item | Replace with | Blocked on |
|---|---|---|
| Hand-weighted confidence formula | Fitted calibration | Feedback data |
| Heuristic reference-role classifier | Learned classifier | Labelled reference pairs |
| Flat selector fallbacks | Structural change detection | Live crawl history |
| Chroma | pgvector or Qdrant | Corpus > ~100k documents |
| Streamlit | React | Pilot commitment |

Every item on this list is blocked on data the running system is designed to
collect. That is the intended sequence, not an accident: the prototype is built
to generate the evidence needed to replace its own weakest components.
