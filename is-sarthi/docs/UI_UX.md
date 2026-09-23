# UI/UX Design Document

## IS Sarthi

**Version:** 2.0

---

## 1. Design Principles

1. **Defensibility over delight.** The user's output is a tender document that may be legally contested. Every screen is built so the official can answer "why did you cite this standard?" — the justification is never a hidden detail.
2. **Show the uncertainty.** A wrong confident answer is worse than an honest uncertain one. Low confidence and no-match are designed states, not error states.
3. **Currency is visual.** A withdrawn standard must be impossible to miss, not a line of small grey text.
4. **Scannable, not readable.** Officials process many line items. Consistent card geometry lets the eye jump; prose paragraphs do not.
5. **No information by color alone.** Every status carries an icon and a text label (WCAG 2.1 AA).

## 2. Personas and Journeys

**Procurement Official — "draft a spec"**
Enters a product description → scans recommendations → expands one to check scope → reviews allied standards → copies the formatted clause into the tender.

**Technical Reviewer — "check a draft"**
Pastes an existing spec → sees flagged outdated/withdrawn citations and missing allied standards → exports an annexure of corrections.

**Vendor — "understand compliance"**
Reads a tender's IS reference → looks it up → sees the full normative closure and certification requirement before bidding.

## 3. Information Architecture

```
Home / Query
├── Results
│   ├── Recommendation card  (repeating)
│   │   ├── Standard detail panel
│   │   │   ├── Scope text
│   │   │   ├── Amendment timeline
│   │   │   └── Dependency graph
│   │   └── Allied standards (grouped by role)
│   └── Export drawer
├── Spec Validator
└── Admin
    ├── Corpus coverage
    ├── Sync health
    └── Unmatched-query log
```

## 4. Screens

### 4.1 Query

Single-purpose entry. A large textarea, an upload affordance, a language selector, and one primary action.

- Placeholder shows a realistic example, teaching input format without a tutorial
- Upload accepts PDF/DOCX; on upload, the extracted spec sections are shown for confirmation before submission — never silently processed
- Recent queries listed below for repeat drafting sessions
- Corpus coverage badge ("Electrical, Civil, Chemical — 4,210 standards, synced 6h ago") sets expectations honestly and doubles as proof the live pipeline is real

### 4.2 Results

Ranked recommendation cards. Each card, top to bottom:

| Element | Treatment |
|---|---|
| IS number + title | Largest type on the card; the thing being scanned for |
| Status chip | `Current` / `Amended` / `Withdrawn — see IS X` — icon + text + color |
| Confidence | High / Medium / Low label with a three-segment bar; raw score on hover only |
| Justification | 1–2 sentences naming the spec attributes that drove the match |
| Certification tag | Distinct pill: "BIS Certification (ISI) mandatory" with gazette link |
| Allied standards | Collapsed count by role — "4 test method · 2 safety · 1 terminology" — expandable |
| Actions | Copy clause · View detail · Accept/Reject feedback |

**Designed states**
- *No confident match* — explains what was searched and suggests adding technical detail; never a blank screen
- *Low confidence* — results shown but visually deprioritized, with a banner explaining why
- *Category outside corpus* — explicit "this division isn't yet synced" rather than a poor match

### 4.3 Standard Detail

Opens as a side panel so the results list stays in view.

- Full scope text with the query-matching passages highlighted
- Amendment timeline as a horizontal sequence — publication, each amendment, current status
- Dependency graph: the standard at center, normative references radiating out, edges labelled by role, nodes colored by status. Clicking a node re-centers. This is the screen that makes the "dependency resolution, not search" argument visually, and it is the recommended demo centerpiece.
- Certification block with scheme, effective date, and the governing notification

### 4.4 Spec Validator

Paste an existing specification; the system extracts every IS citation and returns a table: cited standard, status, issue, suggested action. Outdated and withdrawn citations sort to the top. Missing allied standards are listed separately as "consider adding."

This screen requires no query-writing skill at all, which makes it the lowest-friction entry point for a skeptical official — worth leading with in a pilot.

### 4.5 Admin

Corpus coverage by division, sync run history with extraction rates, and — most valuable — the log of queries that returned no confident match. That log tells BIS where the catalog's discoverability is weakest, which is a benefit to the standards body itself, not just to procurement officials.

## 5. Visual System

| Token | Value | Use |
|---|---|---|
| Primary | Deep indigo | Actions, links |
| Success | Green | Current status |
| Warning | Amber | Amended, medium confidence |
| Danger | Red | Withdrawn, outdated citation |
| Accent | Saffron | Certification tags |
| Surface | Off-white / neutral grey | Cards, background |

Typography: one humanist sans with Devanagari coverage (Inter + Noto Sans Devanagari) — required for genuine multilingual rendering rather than fallback-glyph rendering. Three sizes only: standard title, metadata, body.

Cards use consistent geometry and a single elevation level. Spacing on a 4px scale.

## 6. Interaction & Feedback

- Loading is staged and truthful: "Searching standards" → "Resolving allied standards" → "Preparing explanation". The stages correspond to real pipeline phases, so the wait is legible rather than decorative.
- Errors state what failed and offer a retry; never a stack trace.
- Feedback (accept/reject) is one click per card, with no mandatory comment — friction here destroys the signal the learned reranker depends on.

## 7. Accessibility

- WCAG 2.1 AA contrast throughout
- Status and confidence always icon + text + color
- Full keyboard navigation; the graph view has a tabular equivalent
- Screen-reader labels on all status chips and the dependency graph
- Minimum 16px body text — officials are not assumed to be young or technical

## 8. Prototype vs Production

The internal-round build is Streamlit: query screen, results cards, expandable detail, certification tags. Deliberately deferred — dependency-graph visualization (static image in the pitch instead), admin screens, export drawer, and the React rebuild. The deferral is scope discipline, not a gap in the design: everything above is specified so the finals build has no design ambiguity to resolve.
