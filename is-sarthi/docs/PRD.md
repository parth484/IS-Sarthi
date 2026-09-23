# Product Requirements Document

## IS Sarthi — AI-Powered Recommendation Engine for Identifying Applicable Indian Standards for Procurement Specifications

**Version:** 2.0 (Scalable product specification)
**Problem statement owner:** Bureau of Indian Standards (BIS)
**Event:** Smart India Hackathon 2026

---

## 1. Background

Government departments, Public Sector Enterprises (PSEs), procurement agencies, and private organizations procure a wide range of products and services through e-procurement portals. Procurement officials preparing technical specifications must reference the appropriate Indian Standards (IS).

Identifying the correct standard is genuinely hard:

- **Scale** — tens of thousands of published IS standards across 14+ technical divisions.
- **Overlapping scopes** — multiple standards can plausibly apply to the same product.
- **Frequent revisions** — standards are amended and superseded on a rolling basis.
- **Normative dependency chains** — a product standard cites test-method, terminology, and safety standards which themselves cite others.
- **Separate certification regime** — whether a product requires BIS Product Certification, CRS registration, or Hallmarking is governed by gazette notifications published independently of the standards themselves.

Consequently tender specifications omit relevant standards, reference withdrawn versions, or carry incomplete technical requirements — producing ambiguity, reduced product quality, and procurement disputes that are expensive to litigate after award.

## 2. Problem Statement

An intelligent system is required that automatically analyzes a product description or technical specification and recommends the most relevant Indian Standard(s), along with allied, cross-referenced, and normative standards that should also be considered.

## 3. What Exists Today (Gap Analysis)

| Current capability | How it works today | Gap |
|---|---|---|
| Finding a standard | BIS "Know Your Standard" keyword search | Lexical only — fails when the official's vocabulary differs from the standard's title |
| Finding related standards | Manually reading the normative references section of a PDF | No traversal; second-order references almost never checked |
| Checking currency | Manually comparing the cited year against the portal | Withdrawn/superseded standards routinely cited |
| Certification requirement | Separate institutional knowledge, gazette notifications | Not linked to standard selection at all |
| Multilingual access | None | Officials drafting in regional languages have no entry point |
| Audit trail | None | No record of why a standard was chosen when disputes arise |

**The core insight:** this is not a search problem. It is a *dependency-resolution* problem with a currency dimension and a compliance dimension. That framing is what differentiates IS Sarthi from a better search box.

## 4. Objective

Deliver an AI-powered recommendation engine that integrates with procurement portals and assists officials in identifying the most relevant Indian Standards and related standards while preparing tender specifications — with every recommendation explained, current, and traceable.

## 5. Target Users

| Persona | Context | Primary need |
|---|---|---|
| **Procurement Official** (primary) | Drafts tender specs on GeM/CPPP; domain-aware but not standards-expert | Fast, defensible standard references |
| **Technical Reviewer** | Vets draft specs before publication | Confidence that nothing was missed |
| **Vendor / Bidder** (secondary) | Reads tender, must comply | Understands full compliance surface before bidding |
| **BIS Administrator** | Maintains the standards catalog | Visibility into what officials search for but can't find |

## 6. Functional Requirements

### 6.1 Input (FR-100)

| ID | Requirement | Priority |
|---|---|---|
| FR-101 | Accept free-text product description | Must |
| FR-102 | Accept pasted technical specification blocks | Must |
| FR-103 | Accept tender document upload (PDF, DOCX) with automatic spec-section extraction | Must |
| FR-104 | Accept natural-language queries ("what standards apply to LED street lights?") | Must |
| FR-105 | Accept multilingual input across major Indian languages | Must |
| FR-106 | Batch input — multiple line items from a single tender | Should |

### 6.2 Core Recommendation (FR-200)

| ID | Requirement | Priority |
|---|---|---|
| FR-201 | Recommend relevant IS standard(s) via semantic understanding, not keyword matching | Must |
| FR-202 | Rank recommendations with a calibrated confidence score | Must |
| FR-203 | Produce a plain-language justification citing the specific spec attributes that drove the match | Must |
| FR-204 | Return a clear "no confident match" state rather than a low-quality guess | Must |
| FR-205 | Surface the specific clauses/scope text supporting the match | Should |

### 6.3 Allied Standards (FR-300)

| ID | Requirement | Priority |
|---|---|---|
| FR-301 | Identify normative references of each recommended standard | Must |
| FR-302 | Traverse the citation graph to configurable depth (default 2 hops) | Must |
| FR-303 | Classify allied standards by role: test method, terminology, safety, installation, related product | Must |
| FR-304 | Deduplicate and rank allied standards by relevance, not just adjacency | Must |
| FR-305 | Visualize the dependency graph for a recommended standard | Should |

### 6.4 Currency & Amendments (FR-400)

| ID | Requirement | Priority |
|---|---|---|
| FR-401 | Highlight the latest published version of each recommended standard | Must |
| FR-402 | List amendment numbers and dates | Must |
| FR-403 | Flag withdrawn or superseded standards prominently, with the successor | Must |
| FR-404 | Detect when a user's pasted spec cites an outdated standard and warn | Must |
| FR-405 | Notify subscribed users when a previously recommended standard is amended | Should |

### 6.5 Certification (FR-500)

| ID | Requirement | Priority |
|---|---|---|
| FR-501 | Flag mandatory BIS Product Certification (ISI mark) requirements | Must |
| FR-502 | Flag CRS (Compulsory Registration Scheme) requirements | Must |
| FR-503 | Flag Hallmarking requirements for applicable product categories | Must |
| FR-504 | Link each flag to its governing gazette notification | Must |
| FR-505 | Indicate the effective date of a certification requirement | Should |

### 6.6 Output & Integration (FR-600)

| ID | Requirement | Priority |
|---|---|---|
| FR-601 | Export a formatted standards clause ready to paste into a tender | Must |
| FR-602 | Export as PDF/DOCX compliance annexure | Should |
| FR-603 | REST API suitable for procurement-portal embedding | Must |
| FR-604 | Feedback capture (accept/reject per recommendation) | Must |
| FR-605 | GeM integration via API or document hook | Could (post-pilot) |

### 6.7 Data Freshness (FR-700)

| ID | Requirement | Priority |
|---|---|---|
| FR-701 | Automatically ingest newly published standards without manual intervention | Must |
| FR-702 | Detect amendments to existing standards and update downstream stores | Must |
| FR-703 | Monitor gazette notifications for certification-regime changes | Must |
| FR-704 | Maintain a full audit log of every corpus change | Must |
| FR-705 | Expose "what changed this week" to administrators | Should |

## 7. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Relevance** | Correct standard in top-3 for ≥85% of the evaluation set; top-1 for ≥65% |
| **Latency** | p95 under 3s for text query; under 15s for document upload |
| **Freshness** | New/amended standards reflected within 24h of BIS publication |
| **Explainability** | No recommendation is ever returned without a justification and source trace |
| **Availability** | 99.5% for the recommendation API |
| **Scalability** | Architecture supports the full BIS catalog (~20k+ standards) without redesign |
| **Data sovereignty** | Deployable fully on-premise / NIC cloud; no mandatory external LLM dependency |
| **Auditability** | Every recommendation is logged with the corpus version that produced it |
| **Accessibility** | WCAG 2.1 AA; no information conveyed by color alone |

## 8. Unique Selling Points

1. **Dependency resolution, not search.** Competing approaches return a list. IS Sarthi returns a resolved compliance surface — the product standard plus its normative closure, classified by role.
2. **Currency as a first-class feature.** The system actively warns when a spec cites a withdrawn standard. Nothing in the current workflow does this.
3. **Certification linked to selection.** BIS/CRS/Hallmarking flags surface at the moment of standard selection, sourced to the governing gazette notification.
4. **Self-updating corpus.** Scheduled sync with change detection means the corpus does not rot — a pure-RAG demo built on a static PDF dump does.
5. **Explained and auditable.** Every recommendation carries a justification and a corpus version, making it defensible in a procurement dispute.
6. **Multilingual by construction.** Indic-capable embeddings rather than bolt-on translation.
7. **Sovereign-deployable.** Runs entirely on-premise with open-weight models — a hard requirement for government procurement data that most hackathon submissions ignore.

## 9. Success Metrics

**Product**
- Retrieval: top-3 accuracy ≥85% on the held-out evaluation set
- Allied-standard recall: ≥80% of ground-truth normative references surfaced
- Currency: zero withdrawn standards recommended without a warning flag
- Adoption proxy: ≥60% of recommendations accepted (feedback signal)

**Outcome (pilot)**
- Reduction in time to finalize a tender's standards section
- Reduction in pre-bid clarification queries relating to standards
- Reduction in disputes citing incorrect or outdated standard references

## 10. Assumptions, Constraints, Risks

| Item | Detail | Mitigation |
|---|---|---|
| No public BIS API | Data acquisition is scrape-based | Selector-driven config; graceful degradation to seed corpus; formal data-sharing agreement is the production path |
| Full standard text is licensed | Only metadata + scope are freely usable | System is designed to work on scope text; full text is an enhancement, not a dependency |
| Site structure may change | Scrapers can break | Selector validation script + alerting on extraction-rate drop |
| LLM hallucination | Justifications could misstate | Justifications are constrained to retrieved context; confidence gating; no recommendation without a retrieved source |
| Corpus bias toward well-documented divisions | Uneven coverage | Coverage dashboard; explicit "low coverage in this category" signalling |

## 11. Release Plan

| Phase | Scope | Duration |
|---|---|---|
| **MVP (internal round)** | Seed corpus (2–3 divisions), semantic retrieval, graph expansion, cert flags, justification, Streamlit UI | 3 days |
| **Finals build** | Live pipeline running, 2+ divisions fully synced, document upload, multilingual, feedback loop, eval harness with numbers | 4–6 weeks |
| **Pilot** | One procuring department, full division coverage, API integration, audit logging | 3 months |
| **Production** | Full BIS catalog, GeM integration, notification subsystem, on-prem deployment | 6–12 months |
