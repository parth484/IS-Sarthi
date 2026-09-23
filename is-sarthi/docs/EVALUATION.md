# Evaluation

The purpose of this harness is that retrieval changes get **measured rather
than asserted**. "We improved the matching" is not a claim anyone should accept
without Recall@k attached.

## Running

```bash
python scripts/run_eval.py              # TF-IDF baseline, no infrastructure
python scripts/run_eval.py --online     # full production stack
python scripts/run_eval.py --json       # machine-readable
```

## Metrics

| Metric | Question it answers |
|---|---|
| `hit@1` | Is the correct standard the top result? |
| `hit@3` / `hit@5` | Is it visible without scrolling? |
| `recall@3` / `recall@5` | What fraction of all correct standards surfaced? |
| `mrr` | How high does the first correct answer sit on average? |
| `allied_recall` | What fraction of ground-truth normative references were surfaced? |

`allied_recall` is the metric most specific to this problem statement. Retrieval
quality is table stakes; surfacing the normative closure is the feature.

## Dataset

`data/seed/eval_queries.json` — 25 labelled cases across electrical, civil,
metallurgy, chemical and general engineering. Each carries `expected` (correct
IS numbers) and, where applicable, `expected_allied`.

Queries are written in **procurement phrasing**, not standards-committee
phrasing ("TMT deformed steel reinforcement bars Fe 500 grade", not "high
strength deformed steel bars"). This matters: an eval set written in the
corpus's own vocabulary tests nothing, because the vocabulary gap *is* the
problem being solved.

Two cases are adversarial by design:
- The cement query expects both IS 269 and the superseded IS 8112 — the system
  must surface the latter **with a warning**, not silently rank or silently drop it.
- The cable query accepts either IS 1554-1 or IS 7098-1, because both are
  genuinely defensible for the described spec. Forcing a single answer would
  test the label, not the system.

## Interpreting the numbers

**Current baseline results are inflated.** Against 57 seed standards there are
few near-misses available. The full BIS catalogue (~20,000 standards with
heavily overlapping scopes) will produce substantially lower scores, and that
drop is expected rather than a regression.

Treat this as a **regression harness** — it catches changes that make retrieval
worse — not as a quality claim. Quoting "100% hit@3" to a judge without the
corpus-size caveat will (correctly) damage your credibility; volunteering the
caveat builds it.

## Targets for the full corpus

| Metric | Target |
|---|---|
| `hit@1` | ≥ 65% |
| `hit@3` | ≥ 85% |
| `allied_recall` | ≥ 80% |
| Withdrawn standards recommended without a warning | 0 |

## Beyond retrieval

Two things this harness does not measure and that need manual review:

**Justification faithfulness.** Does the explanation cite attributes actually
present in the query and the retrieved scope? Sample 20 outputs per release and
rate each as faithful / vague / unsupported. Automating this is future work.

**Confidence calibration.** Bucket results by predicted band and check observed
accuracy within each. "High" should mean high. An earlier version of the
confidence formula scored irrelevant results at 0.68 "Medium" because it
weighted position relative to the top hit rather than absolute match quality —
a bug that retrieval metrics alone would never have surfaced, since the ordering
was correct.
