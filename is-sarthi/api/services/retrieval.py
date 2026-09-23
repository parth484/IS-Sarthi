"""
Hybrid retrieval: dense + sparse, fused by RRF, then cross-encoder reranked.

Why not just vector search. IS scope text is short, formal, and lexically
homogeneous -- dozens of cable standards open with near-identical phrasing.
Dense similarity therefore produces tightly clustered scores that discriminate
poorly between siblings. Meanwhile procurement queries frequently contain exact
designators ("Class H", "1100 V", "IS 1554 Part 1") where lexical match is
exactly right and embeddings dilute the signal.

Running both and fusing is not belt-and-braces; each covers the other's
specific failure mode.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from pipeline.config import settings
from pipeline.db.stores import vectors

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    is_number: str
    title: str = ""
    document: str = ""
    metadata: dict = field(default_factory=dict)
    dense_rank: Optional[int] = None
    sparse_rank: Optional[int] = None
    dense_score: float = 0.0
    sparse_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float = 0.0
    confidence: float = 0.0


_embedder = None
_reranker = None
_bm25 = None
_bm25_ids: list[str] = []
_bm25_meta: dict[str, dict] = {}


def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(settings.embedding_model)
    return _embedder


def get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder

            _reranker = CrossEncoder(settings.reranker_model, max_length=512)
        except Exception as exc:
            logger.warning("Reranker unavailable (%s); using fused order", exc)
            _reranker = False
    return _reranker or None


def _tokenize(text: str) -> list[str]:
    """
    Tokenizer tuned for this corpus.

    Standard designators must survive as single tokens -- splitting "IS 1554-1"
    into "is", "1554", "1" destroys the exact-match signal that is the entire
    reason for having a sparse arm.
    """
    text = text.lower()
    designators = re.findall(r"is\s*\d+(?:-\d+)?", text)
    text = re.sub(r"is\s*\d+(?:-\d+)?", " ", text)
    words = re.findall(r"[a-z]+|\d+(?:\.\d+)?", text)
    return [d.replace(" ", "") for d in designators] + words


def build_sparse_index() -> int:
    """
    Build the BM25 index from the vector store's documents.

    Rebuilt at startup and after a sync completes. At corpus scale (tens of
    thousands of short documents) an in-memory index is entirely adequate and
    avoids standing up a second search service.
    """
    global _bm25, _bm25_ids, _bm25_meta

    documents = vectors.all_documents()
    if not documents:
        logger.warning("No documents available; sparse index empty")
        _bm25, _bm25_ids, _bm25_meta = None, [], {}
        return 0

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning("rank_bm25 not installed; sparse retrieval disabled")
        return 0

    _bm25_ids = [d["is_number"] for d in documents]
    _bm25_meta = {d["is_number"]: d for d in documents}
    _bm25 = BM25Okapi([_tokenize(d["document"]) for d in documents])
    logger.info("Sparse index built over %d documents", len(_bm25_ids))
    return len(_bm25_ids)


def dense_search(query: str, top_k: int, include_withdrawn: bool = False) -> list[Candidate]:
    # "query:" prefix is required by the e5 family's asymmetric training.
    embedding = get_embedder().encode(f"query: {query}", normalize_embeddings=True).tolist()
    where = None if include_withdrawn else {"status": "current"}

    try:
        hits = vectors.query(embedding, top_k=top_k, where=where)
    except Exception:
        # Chroma rejects `where` clauses against collections with no matching
        # metadata; fall back rather than returning nothing.
        hits = vectors.query(embedding, top_k=top_k)

    return [
        Candidate(
            is_number=hit["is_number"],
            title=hit["metadata"].get("title", ""),
            document=hit["document"],
            metadata=hit["metadata"],
            dense_rank=rank,
            dense_score=hit["score"],
        )
        for rank, hit in enumerate(hits, start=1)
    ]


def sparse_search(query: str, top_k: int) -> list[Candidate]:
    if _bm25 is None:
        return []

    scores = _bm25.get_scores(_tokenize(query))
    ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)[:top_k]

    results = []
    for rank, (index, score) in enumerate(ranked, start=1):
        if score <= 0:
            continue
        is_number = _bm25_ids[index]
        entry = _bm25_meta[is_number]
        results.append(
            Candidate(
                is_number=is_number,
                title=entry["metadata"].get("title", ""),
                document=entry["document"],
                metadata=entry["metadata"],
                sparse_rank=rank,
                sparse_score=float(score),
            )
        )
    return results


def reciprocal_rank_fusion(
    dense: list[Candidate], sparse: list[Candidate], k: int = None
) -> list[Candidate]:
    """
    RRF over rank positions.

    Rank-based fusion is preferred to weighted score blending because cosine
    similarity and BM25 scores live on incomparable scales -- calibrating
    between them would require per-corpus tuning that would silently go stale
    as the corpus grows.
    """
    k = k or settings.rrf_k
    merged: dict[str, Candidate] = {}

    for candidate in dense:
        merged[candidate.is_number] = candidate

    for candidate in sparse:
        existing = merged.get(candidate.is_number)
        if existing:
            existing.sparse_rank = candidate.sparse_rank
            existing.sparse_score = candidate.sparse_score
        else:
            merged[candidate.is_number] = candidate

    for candidate in merged.values():
        score = 0.0
        if candidate.dense_rank:
            score += 1.0 / (k + candidate.dense_rank)
        if candidate.sparse_rank:
            score += 1.0 / (k + candidate.sparse_rank)
        candidate.fused_score = score

    return sorted(merged.values(), key=lambda c: c.fused_score, reverse=True)


def rerank(query: str, candidates: list[Candidate], top_k: int) -> list[Candidate]:
    """Cross-encoder scoring -- where most of the precision is won."""
    if not candidates:
        return []

    reranker = get_reranker()
    if reranker is None:
        return candidates[:top_k]

    pairs = [(query, f"{c.title}. {c.document}"[:2000]) for c in candidates]
    scores = reranker.predict(pairs)

    for candidate, score in zip(candidates, scores):
        candidate.rerank_score = float(score)

    return sorted(candidates, key=lambda c: c.rerank_score, reverse=True)[:top_k]


def _sigmoid(x: float) -> float:
    import math

    return 1.0 / (1.0 + math.exp(-x))


def compute_confidence(ranked: list[Candidate]) -> None:
    """
    Calibrated confidence, in place.

    The raw cross-encoder logit is a poor confidence signal on its own: it says
    how well the top document matches, not whether the system found the *right*
    document. Two additional signals matter:

      agreement -- both retrieval arms independently surfaced it
      margin    -- how far clear of the runner-up it is

    A high-scoring top result that the sparse arm never saw and that sits a
    hair above the runner-up is exactly the case where the system should say
    "medium", and this is what makes it do so.
    """
    if not ranked:
        return

    normalized = [_sigmoid(c.rerank_score) for c in ranked]
    top = normalized[0]
    runner_up = normalized[1] if len(normalized) > 1 else 0.0

    for index, candidate in enumerate(ranked):
        # Absolute match quality must dominate. Weighting a candidate by its
        # position relative to the leader is degenerate: it reports how the
        # results are ordered, not whether anything actually matched, so an
        # entirely irrelevant top hit still scores well. The sigmoid of the
        # cross-encoder logit is the only term that answers "is this right".
        quality = normalized[index]
        agreement = 1.0 if (candidate.dense_rank and candidate.sparse_rank) else 0.0
        margin = max(0.0, top - runner_up) if index == 0 else 0.0
        candidate.confidence = round(
            0.65 * quality + 0.15 * agreement + 0.20 * margin, 4
        )


def confidence_band(score: float) -> str:
    if score >= 0.75:
        return "High"
    if score >= 0.50:
        return "Medium"
    return "Low"


def retrieve(query: str, top_k: Optional[int] = None,
             include_withdrawn: bool = False) -> list[Candidate]:
    """Full four-stage retrieval."""
    top_k = top_k or settings.final_top_k

    dense = dense_search(query, settings.dense_top_k, include_withdrawn)
    sparse = sparse_search(query, settings.sparse_top_k)
    fused = reciprocal_rank_fusion(dense, sparse)
    reranked = rerank(query, fused[: settings.dense_top_k], settings.rerank_top_k)
    compute_confidence(reranked)

    return reranked[:top_k]
