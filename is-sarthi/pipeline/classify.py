"""
Reference-role classification.

FR-303 requires allied standards to be presented by role -- test method,
terminology, safety, installation, related product -- not as an undifferentiated
list. That distinction is what makes the output actionable: a procurement
official cites a test-method standard in a different clause of the tender than
a safety standard.

IS titles are highly formulaic, so title-pattern rules get most of the way
there. Clause context from the citing document is used as a secondary signal.
This is heuristic and its accuracy at scale is untested -- stated plainly in
the TRD's limitations section. The feedback table is the path to replacing it
with a learned classifier once labelled data exists.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class RefType(str, Enum):
    TEST_METHOD = "test_method"
    TERMINOLOGY = "terminology"
    SAFETY = "safety"
    INSTALLATION = "installation"
    RELATED_PRODUCT = "related_product"
    SAMPLING = "sampling"
    DIMENSIONS = "dimensions"


# Order matters: the first matching rule wins, so the most specific patterns
# are listed first. "Methods of test for safety of X" is a test-method standard,
# not a safety standard, and must not be caught by the safety rule.
TITLE_RULES: list[tuple[RefType, re.Pattern]] = [
    (RefType.TEST_METHOD, re.compile(
        r"\b(methods?\s+of\s+test|test\s+methods?|methods?\s+for\s+testing|"
        r"determination\s+of|measurement\s+of)\b", re.I)),
    (RefType.SAMPLING, re.compile(
        r"\b(methods?\s+of\s+sampling|sampling\s+(?:plan|procedure)|"
        r"inspection\s+by\s+attributes)\b", re.I)),
    (RefType.TERMINOLOGY, re.compile(
        r"\b(glossary\s+of\s+terms|terminology|definitions|"
        r"terms\s+and\s+definitions|nomenclature)\b", re.I)),
    (RefType.INSTALLATION, re.compile(
        r"\b(code\s+of\s+practice|installation|erection|"
        r"laying\s+of|selection.{0,20}installation|maintenance\s+of)\b", re.I)),
    (RefType.SAFETY, re.compile(
        r"\b(safety\s+(?:requirements?|code|rules)|protection\s+against|"
        r"hazard|fire\s+resistance|electrical\s+safety)\b", re.I)),
    (RefType.DIMENSIONS, re.compile(
        r"\b(dimensions?|tolerances?|preferred\s+(?:sizes|numbers)|"
        r"designation\s+system)\b", re.I)),
]

# Where the reference is cited within the citing document, used when the title
# is uninformative or unavailable.
CONTEXT_RULES: list[tuple[RefType, re.Pattern]] = [
    (RefType.TEST_METHOD, re.compile(r"\b(shall\s+be\s+tested|tested\s+in\s+accordance|"
                                     r"type\s+test|routine\s+test)\b", re.I)),
    (RefType.SAMPLING, re.compile(r"\b(sampl\w+|lot\s+acceptance)\b", re.I)),
    (RefType.SAFETY, re.compile(r"\b(safety|hazard|protective)\b", re.I)),
    (RefType.INSTALLATION, re.compile(r"\b(install\w+|erect\w+|commission\w+)\b", re.I)),
]


def classify_reference(
    title: Optional[str] = None, citing_context: Optional[str] = None
) -> RefType:
    """Classify one reference. Title evidence beats context evidence."""
    if title:
        for ref_type, pattern in TITLE_RULES:
            if pattern.search(title):
                return ref_type

    if citing_context:
        for ref_type, pattern in CONTEXT_RULES:
            if pattern.search(citing_context):
                return ref_type

    return RefType.RELATED_PRODUCT


def classify_all(
    references: list[str],
    title_lookup: Optional[dict[str, str]] = None,
    context_lookup: Optional[dict[str, str]] = None,
) -> list[dict]:
    """
    Classify a standard's full reference list.

    title_lookup lets already-ingested titles inform classification of
    references whose own records have not been crawled yet -- which is the
    common case during an incremental crawl, since references routinely point
    at standards in divisions not yet reached.
    """
    title_lookup = title_lookup or {}
    context_lookup = context_lookup or {}

    classified = []
    for ref in references:
        ref_type = classify_reference(
            title=title_lookup.get(ref), citing_context=context_lookup.get(ref)
        )
        classified.append(
            {
                "is_number": ref,
                "title": title_lookup.get(ref),
                "ref_type": ref_type.value,
            }
        )
    return classified


ROLE_LABELS = {
    RefType.TEST_METHOD.value: "Test method",
    RefType.TERMINOLOGY.value: "Terminology",
    RefType.SAFETY.value: "Safety",
    RefType.INSTALLATION.value: "Installation",
    RefType.SAMPLING.value: "Sampling",
    RefType.DIMENSIONS.value: "Dimensions",
    RefType.RELATED_PRODUCT.value: "Related product",
}
