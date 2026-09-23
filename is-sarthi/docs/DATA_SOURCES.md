# Data Sources

Every source the pipeline touches, what it yields, how it is extracted, and the
basis on which it is used.

---

## Summary

| Source | Yields | Method | Cadence | Criticality |
|---|---|---|---|---|
| BIS standards portal | Number, title, year, status, division, normative refs, amendments | HTML scrape, selector-config driven | Weekly full / daily delta | **Core** |
| BIS Manak Online | Structured catalogue search | ASP.NET WebForms POST (viewstate round-trip) | Weekly | Enrichment |
| IS standard PDFs | Scope text, reference lists, supersession | `pdfplumber` + section regex | On acquisition | **Core** |
| CRS product list | Mandatory registration products → IS numbers | Spreadsheet/PDF discovered from landing page | Weekly | **Core** |
| e-Gazette | Quality Control Orders, certification effective dates | Notification scrape + PDF parse | Daily | **Core** |
| GeM catalogue | Real procurement phrasing for the eval set | Best-effort JSON | Ad hoc | Optional |

---

## 1. BIS standards portal

**What is freely available:** standard number, title, division, year of
publication, status (current / withdrawn / under revision), normative reference
lists, amendment numbers and dates.

**What is not:** full clause text, which is licensed. The retrieval design
targets *scope* text specifically so the system is useful without a BIS licence.
This is a design constraint, not a gap to be worked around — do not attempt to
obtain licensed text by scraping.

**Method.** `pipeline/scrapers/bis_portal.py`, crawled by division. There is no
public API. All DOM selectors live in `selectors.yaml` with ordered fallbacks,
because public-sector sites are rebuilt section by section and tolerating more
than one layout at a time materially reduces breakage.

**Politeness.** 1 request / 1.5s per host, robots.txt honoured, identifying
User-Agent with a contact address, exponential backoff with jitter on 429/5xx,
circuit breaker after repeated failure. BIS is a public body on modest
infrastructure; aggressive crawling is both discourteous and the fastest route
to losing the source entirely.

**Production path.** For a real deployment, a formal data-sharing arrangement
with BIS replaces scraping. Scraping is the prototype's bridge, and the
architecture is unchanged either way — only `pipeline/scrapers/` is swapped.

---

## 2. Manak Online

`standardsbis.bsbedge.com` is the BIS e-commerce portal. Better-structured
search results than the main portal, but it is ASP.NET WebForms, so each search
requires a GET to capture `__VIEWSTATE` and `__EVENTVALIDATION` followed by a
POST carrying them back. Used as an enrichment source to fill gaps where the
main portal listing is sparse, never as the primary.

---

## 3. IS standard PDFs

Where a standard is obtainable, `pipeline/scrapers/pdf_extractor.py` extracts
the scope section, normative reference list, supersession statement and
amendment history.

IS documents follow a rigid house style (Foreword → 1 Scope → 2 References →
3 Terminology), which makes section-boundary regexes far more reliable here
than on arbitrary documents.

**Scope extraction is the quality ceiling for the whole system.** Scope text is
what gets embedded; a mangled scope produces a standard that cannot be
retrieved, and there is no way to detect that from the query side. Hence
`extraction_quality` scoring on every record, with low-scoring records flagged
for manual review in the admin view rather than silently entering the corpus.

---

## 4. CRS mandatory product list

The Compulsory Registration Scheme list is published as a spreadsheet whose
filename changes on every revision. The scraper **discovers** the download link
from the landing page rather than hardcoding it — a hardcoded URL is the single
most common reason this kind of ingestion silently rots.

Product rows are mapped to the IS numbers they cite, producing
`{is_number: certification_record}`.

---

## 5. e-Gazette

This feed exists because whether a product requires ISI marking, CRS
registration or Hallmarking is set by Quality Control Orders gazetted
**independently of the standards themselves**. An official searching the
standards portal will never encounter them.

Without this, the system would report yesterday's compliance regime with full
confidence — worse than reporting nothing, because it would be confidently
wrong on the question with the most legal consequence.

Notifications from the relevant ministry are filtered by keyword, the PDF is
parsed for IS references, scheme type and effective date, and matching standards
are patched with a `certification` record citing the governing notification.

---

## 6. GeM catalogue

Government e-Marketplace product listings supply *real procurement phrasing*,
which is valuable for the evaluation set: officials do not write like standards
committees, and an eval set written by the development team inherits the
development team's vocabulary.

Marked `optional: true` in config. GeM's public surface is inconsistent, so the
scraper is best-effort and nothing downstream depends on it.

---

## Hallmarking

Governed by a small, stable set (IS 1417, IS 1418, IS 2112, IS 15766), so it is
carried as a constant in `pipeline/scrapers/certification.py` rather than
scraped. Kept visible in code rather than buried in data precisely because it is
a hardcoded exception and should be easy to find when it changes.

---

## Legal and ethical basis

- Only freely published metadata is collected; licensed full text is not.
- robots.txt is honoured on every request.
- Rate limits are conservative and configurable downward.
- The User-Agent identifies the project and carries a contact address.
- Raw response snapshots are retained so a parser fix can be replayed without
  re-crawling — this reduces total load on the source rather than increasing it.
- No personal data is collected from any source.

---

## Failure modes and handling

| Failure | Detection | Response |
|---|---|---|
| DOM structure changed | `selector_misses` in `ExtractionStats`; hourly health check | Alert; fix `selectors.yaml`; replay from snapshots |
| Source unreachable | Circuit breaker after N consecutive failures | Disable source, alert, retry next cycle |
| Rate limited (429) | `Retry-After` header honoured | Back off and continue |
| CRS link moved | `crs.file_link` miss | Alert; the discovery hints in config usually need widening, not code changes |
| Extraction quality drop | `extraction_quality` average in `v_corpus_coverage` | Flag records for review before they enter retrieval |
| Zero rows returned | Distinguished from "nothing new" only by miss counting | This is precisely why `selector_misses` exists |
