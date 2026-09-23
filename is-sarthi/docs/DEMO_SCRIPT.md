# Demo Runbook

Eight minutes, rehearsed, with the failure modes pre-handled.

---

## Before you present

```bash
python scripts/demo_offline.py          # must work with zero infrastructure
python scripts/run_eval.py              # know your numbers
```

Have the offline demo running in a terminal **as your fallback**. If Docker,
the network or the model download fails on stage, you switch to it in one
command and lose nothing that matters. Do not skip this step; it is the
difference between a bad five minutes and a dead demo.

Rehearse with the queries below. Never improvise a query on stage — pick ones
you have verified.

---

## The eight minutes

### 1. Frame the problem (60s)

Do not open with the technology. Open with the failure.

> A procurement official writing a tender for cables has to cite the right
> Indian Standard. There are roughly 20,000 of them, with overlapping scopes,
> rolling revisions, and dependency chains — a product standard cites test
> methods, which cite terminology standards. Today the tool for this is a
> keyword search box and institutional memory. The result is tenders citing
> withdrawn standards and omitting the test methods that define acceptance.
> Those become disputes after award, which are expensive to litigate.

### 2. The reframe — this is your differentiator (45s)

> We concluded this isn't a search problem. It's a **dependency-resolution**
> problem with a currency dimension and a compliance dimension. A better search
> box returns a list. What an official needs is a resolved compliance surface.

Say this explicitly. It is the sentence that separates you from every team
building RAG over a PDF dump.

### 3. Live: the core query (90s)

```
3 core armoured copper cable for underground LV power distribution up to 1100V
```

Point at three things, in this order:

1. **IS 1554-1, High confidence** — matched on meaning; the words "armoured"
   and "1100V" never appear together in the standard's title.
2. **Allied standards, grouped by role** — IS 8130 (conductors), IS 10810-1 and
   IS 10810-7 (test methods). *"These are the ones that get missed. An official
   would have to open the PDF and read the references section to find them."*
3. **The mandatory ISI certification flag** — *"This is governed by a gazette
   notification published separately from the standard. Nothing in the current
   workflow connects the two."*

### 4. Live: the currency catch (60s)

```
43 grade ordinary portland cement for RCC foundation
```

IS 8112 comes back flagged **SUPERSEDED → IS 269**.

> If that citation goes into a live tender, every bid is priced against a
> standard that no longer exists. Nothing in the current process catches this.

### 5. Live: the validator — lead with this in a pilot (75s)

```bash
python scripts/demo_offline.py --validate
```

> This is the lowest-friction entry point in the product. It asks nothing of
> the official except a document they already have. No query-writing skill
> required — paste the draft, get back the outdated citations and the allied
> standards you forgot.

It catches the superseded IS 8112, both mandatory certifications, and lists
uncited allied standards.

### 6. The pipeline — why this isn't a static demo (90s)

Show `pipeline/celery_app.py` beat schedule, then:

> Most submissions to a problem like this are RAG over a PDF dump. That corpus
> is stale the week after the hackathon. Ours syncs: weekly full crawl, daily
> delta against the recently-published page, daily gazette monitoring for
> certification changes.
>
> The reason a daily sync is affordable is **dual-hash change detection**. A
> crawl touches every record but only reprocesses the handful that changed — and
> re-embedding, which is the expensive step, is gated separately on the scope
> text itself moving. A status change updates the row and the graph without
> touching the GPU.

### 7. Honesty slide — do not skip this (45s)

> Three things we want to be straight about. Our scraper selectors aren't
> validated against the live BIS DOM yet — that's why they're isolated in a
> config file with a validation script. Our eval numbers look excellent but
> they're against 57 standards, where there aren't enough near-misses to make
> retrieval hard; against the full catalogue they will drop. And our
> reference-role classifier is heuristic, not learned.

Judges find limitations anyway. Naming them first converts a weakness into
evidence of engineering judgment, and it makes everything else you claimed more
credible.

### 8. Close on deployability (30s)

> Procurement specs are pre-publication and commercially sensitive. Our LLM
> adapter has a local target and our embeddings are open-weight, so the whole
> system runs on-premise with no text leaving the deployment boundary. Most
> submissions hardcode a hosted API, which makes them undeployable inside
> government regardless of how good the retrieval is.

---

## Anticipated questions

**"Did you train a model?"**
No, and deliberately. Pretrained embeddings plus a cross-encoder reranker plus
constrained generation. Training needs labelled (spec → standard) pairs that
don't exist yet — which is exactly what our feedback table is designed to
collect. Training now would mean fitting to data we invented.

**"How do you stop it hallucinating a standard number?"**
Structurally, not by prompting. The model never selects standards; it receives
an already-retrieved set and may only explain them. Any IS number in its output
that wasn't retrieved is dropped before the response is assembled.

**"Why three databases?"**
Each answers a structurally different question. Postgres: what's true now and
what was true last month. Neo4j: normative closure to depth 2, typed by edge.
Chroma: what means something similar. Collapsing them forces at least one query
into a shape it handles badly.

**"Why not just vector search?"**
IS scope text is short, formal and lexically homogeneous — dozens of cable
standards open near-identically, so dense scores cluster and don't discriminate
between siblings. Meanwhile queries carry exact designators ("Class H", "1100
V") where lexical match is right and embeddings dilute the signal. Each arm
covers the other's specific failure.

**"What's your accuracy?"**
Give the number, then immediately give the caveat about corpus size. Volunteering
that limit is worth more than the number itself.

**"What if BIS changes their website?"**
Selectors are config with ordered fallbacks; `validate_selectors.py` probes them;
the hourly health check alerts on selector misses. The failure we designed
against is the silent one — a scraper returning zero rows looks identical to one
correctly finding nothing new, unless you count misses.

**"How is this different from the BIS portal search?"**
Semantic matching, automatic normative-closure traversal, currency warnings, and
certification linkage. The portal does the first of those lexically and none of
the rest.

---

## If something breaks

| Breaks | Do |
|---|---|
| Docker / databases | `python scripts/demo_offline.py` — everything degrades to in-memory |
| Network | Offline demo needs none |
| Model download | `python scripts/bootstrap.py --no-embed`, then offline demo |
| A live query returns junk | Move to the validator demo; it's deterministic |

Never debug on stage. Switch to the fallback, keep talking, move on.
