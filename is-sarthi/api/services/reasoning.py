"""
Justification generation.

Two constraints shape this module.

First, sovereignty: procurement specifications are frequently pre-publication
and commercially sensitive. The provider is pluggable and includes a local
(Ollama) target so a deployment can run with no text leaving its boundary. A
design that hardcodes a hosted API is not deployable inside government, which
would make the whole system a demo rather than a product.

Second, grounding: the model never selects standards. It receives an already
retrieved set and may only explain them. It cannot introduce an IS number,
because any number it emits that was not retrieved is dropped before the
response is assembled. This makes the class of hallucination that would matter
most here structurally impossible rather than merely discouraged.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from pipeline.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an assistant to Indian government procurement officials. \
You explain why specific Indian Standards (IS) apply to a procurement specification.

Rules you must follow:
1. You may ONLY discuss the standards supplied to you in the context block. \
Never introduce an IS number that is not in that block.
2. Justify each standard by pointing to the specific attributes in the user's \
specification that the standard's scope covers. Be concrete: cite the material, \
rating, dimension or application that drove the match.
3. If the supplied standards do not plausibly cover the specification, say so by \
setting "sufficient" to false. Do not stretch to justify a poor match.
4. Write for a procurement official, not an engineer. Plain language, no jargon \
beyond the standard's own terminology.
5. Keep each justification to one or two sentences.

Return ONLY valid JSON, no markdown fences, no preamble, in this exact shape:
{"sufficient": true, "justifications": [{"is_number": "IS 1554-1", \
"justification": "...", "key_attributes": ["..."]}], "caveat": null}"""


def build_context(candidates: list[dict]) -> str:
    blocks = []
    for candidate in candidates:
        scope = (candidate.get("scope") or candidate.get("document") or "")[:1200]
        blocks.append(
            f"[{candidate['is_number']}] {candidate.get('title','')}\n"
            f"Status: {candidate.get('status','current')} | "
            f"Year: {candidate.get('year','unknown')}\n"
            f"Scope: {scope}"
        )
    return "\n\n".join(blocks)


def build_user_prompt(query: str, candidates: list[dict], language: str = "en") -> str:
    language_note = (
        ""
        if language == "en"
        else f"\n\nWrite the justification text in this language: {language}. "
        "Keep IS numbers in Latin script."
    )
    return (
        f"Procurement specification:\n{query}\n\n"
        f"Retrieved candidate standards:\n{build_context(candidates)}"
        f"{language_note}"
    )


# ------------------------------------------------------------- providers

def _call_anthropic(system: str, user: str) -> Optional[str]:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.llm_api_key)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=1200,
            temperature=0.1,  # explanation, not creativity
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        )
    except Exception as exc:
        logger.error("Anthropic call failed: %s", exc)
        return None


def _call_openai(system: str, user: str) -> Optional[str]:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.llm_api_key)
        response = client.chat.completions.create(
            model=settings.llm_model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.error("OpenAI call failed: %s", exc)
        return None


def _call_local(system: str, user: str) -> Optional[str]:
    """Ollama-compatible endpoint for fully on-premise deployment."""
    try:
        import requests

        response = requests.post(
            settings.local_llm_url,
            json={
                "model": settings.llm_model,
                "prompt": f"{system}\n\n{user}",
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json().get("response")
    except Exception as exc:
        logger.error("Local LLM call failed: %s", exc)
        return None


def _stub(candidates: list[dict], query: str) -> dict:
    """
    Deterministic template justification.

    Used when no LLM is configured, and as the fallback when a call fails. The
    system must degrade to a usable answer rather than an error page: a
    template justification that names the matched scope terms is less
    articulate than a generated one but is never wrong, which for this use case
    is the better failure mode.
    """
    query_terms = set(re.findall(r"[a-z]{4,}", query.lower()))
    justifications = []
    for candidate in candidates:
        text = f"{candidate.get('title','')} {candidate.get('scope','')}".lower()
        overlap = sorted(term for term in query_terms if term in text)[:4]
        if overlap:
            reason = (
                f"The scope of this standard covers "
                f"{', '.join(overlap)} as described in the specification."
            )
        else:
            reason = (
                "This standard was retrieved as semantically closest to the "
                "specification; review its scope before citing."
            )
        justifications.append(
            {
                "is_number": candidate["is_number"],
                "justification": reason,
                "key_attributes": overlap,
            }
        )
    return {
        "sufficient": bool(candidates),
        "justifications": justifications,
        "caveat": "Generated without a language model (template mode).",
    }


# --------------------------------------------------------------- entrypoint

def _parse_json(raw: str) -> Optional[dict]:
    """Models sometimes wrap JSON in fences despite instructions."""
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    logger.warning("Could not parse LLM JSON output")
    return None


def generate_justifications(
    query: str, candidates: list[dict], language: str = "en"
) -> dict:
    if not candidates:
        return {"sufficient": False, "justifications": [], "caveat": "No candidates retrieved."}

    provider = settings.llm_provider
    if provider == "stub":
        return _stub(candidates, query)

    system, user = SYSTEM_PROMPT, build_user_prompt(query, candidates, language)
    raw = {
        "anthropic": _call_anthropic,
        "openai": _call_openai,
        "local": _call_local,
    }.get(provider, lambda s, u: None)(system, user)

    parsed = _parse_json(raw) if raw else None
    if not parsed:
        return _stub(candidates, query)

    # Grounding enforcement: discard anything referring to a standard that was
    # not retrieved. This is the check that makes IS-number hallucination
    # structurally impossible rather than merely unlikely.
    allowed = {candidate["is_number"] for candidate in candidates}
    parsed["justifications"] = [
        item
        for item in parsed.get("justifications", [])
        if item.get("is_number") in allowed
    ]
    if not parsed["justifications"]:
        return _stub(candidates, query)

    return parsed
