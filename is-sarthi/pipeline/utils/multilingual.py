"""
Multilingual Query Processor for IS Sarthi.
Detects Indic scripts (Hindi, Marathi, Telugu, Tamil), preserves technical designators
(IS numbers, voltages, capacities, dimensions), and normalizes queries for semantic retrieval.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Common procurement vocabulary for offline resilience / fallback
OFFLINE_PROCUREMENT_DICT: dict[str, str] = {
    # Cables & Conductors
    "केबल": "cable",
    "केबल्स": "cables",
    "तार": "wire",
    "कंडक्टर": "conductor",
    "तांबा": "copper",
    "तांबे": "copper",
    "तांब्याचे": "copper",
    "एल्युमिनियम": "aluminium",
    "ॲल्युमिनियम": "aluminium",
    "बख्तरबंद": "armoured",
    "आर्मर्ड": "armoured",
    "कवच": "armour",
    "भूमिगत": "underground",
    "जमिनीखालील": "underground",
    "इन्सुलेटेड": "insulated",
    "इन्सुलेशन": "insulation",
    "रोधन": "insulation",
    "रोधी": "insulation",
    # Transformers & Power
    "ट्रांसफार्मर": "transformer",
    "ट्रान्सफॉर्मर": "transformer",
    "बिजली": "power",
    "विद्युत": "electric",
    "वितरण": "distribution",
    "तेल": "oil",
    "इमर्स्ड": "immersed",
    # Cement & Construction
    "सीमेंट": "cement",
    "सिमेंट": "cement",
    "कंक्रीट": "concrete",
    "फाउंडेशन": "foundation",
    "पाया": "foundation",
    "बांधकाम": "construction",
    "निर्माण": "construction",
    "स्टील": "steel",
    "लोखंड": "steel",
    "छड़": "bars",
    "सळया": "bars",
    # Pipes & Materials
    "पाइप": "pipes",
    "पाईप": "pipes",
    "प्लास्टिक": "plastic",
    "सौर": "solar",
    "बैटरी": "battery",
    "बॅटरी": "battery",
    # General adjectives & nouns
    "सुरक्षा": "safety",
    "परीक्षण": "testing",
    "चाचणी": "testing",
    "मानक": "standard",
    "विशिष्टता": "specification",
    "आवश्यकता": "requirements",
    "तीन": "three",
    "फेज": "phase",
}

# Regex to capture technical patterns that must be shielded from translation
TECHNICAL_TOKEN_REGEX = re.compile(
    r"\b("
    r"IS\s*:?\s*\d+(?:-\d+)?(?::\d{4})?|"
    r"\d+(?:\.\d+)?\s*(?:kV|kVA|MVA|kW|MW|V|A|Hz|mm2|sqmm|mm|cm|m|HP)\b|"
    r"\d+\s*core|"
    r"Fe\s*\d+|"
    r"XLPE|PVC|FRLS|TMT|OPC|PPC|LED|ACSR"
    r")\b",
    re.IGNORECASE,
)


def detect_query_language(text: str) -> str:
    """
    Detect whether the query is written in Hindi, Marathi, Telugu, Tamil, or English.
    Returns standard language codes: 'en-IN', 'hi-IN', 'mr-IN', 'te-IN', 'ta-IN'.
    """
    if not text:
        return "en-IN"

    # Devanagari range: \u0900 - \u097F
    if re.search(r"[\u0900-\u097F]", text):
        # Check for Marathi-specific markers
        marathi_markers = [
            "आहे", "करावे", "साठी", "मध्ये", "केबलचे", "प्रकारचे", "पावरसाठी",
            "बांधकामासाठी", "असलेले", "आणि", "किंवा", "जमिनीखालील", "ट्रान्सफॉर्मर"
        ]
        if any(marker in text for marker in marathi_markers):
            return "mr-IN"
        return "hi-IN"

    # Telugu range: \u0C00 - \u0C7F
    if re.search(r"[\u0C00-\u0C7F]", text):
        return "te-IN"

    # Tamil range: \u0B80 - \u0BFF
    if re.search(r"[\u0B80-\u0BFF]", text):
        return "ta-IN"

    return "en-IN"


def offline_normalize_text(text: str) -> str:
    """Fallback keyword normalization for Indic procurement terms."""
    result = text
    for indic_word, en_word in OFFLINE_PROCUREMENT_DICT.items():
        result = re.sub(re.escape(indic_word), en_word, result, flags=re.IGNORECASE)
    # Remove remaining non-ascii non-latin characters
    cleaned = re.sub(r"[\u0900-\u0D7F]+", " ", result)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_query_for_retrieval(query: str) -> Tuple[str, str, str]:
    """
    Prepares a user query for semantic retrieval.
    1. If English: returns (query, 'en-IN', query) with zero modifications.
    2. If Indic language:
       - Protects technical identifiers (IS numbers, voltages, dimensions).
       - Translates via speech_service (Sarvam AI Mayura) or offline glossary fallback.
       - Restores technical identifiers.
       - Returns (normalized_english_query, detected_language, original_query).
    """
    if not query or not query.strip():
        return "", "en-IN", ""

    trimmed = query.strip()
    lang = detect_query_language(trimmed)

    # English query -- preserve exactly as typed
    if lang == "en-IN":
        return trimmed, "en-IN", trimmed

    logger.info("Detected multilingual query in %s: '%s'", lang, trimmed)

    # Protect technical tokens
    tokens: list[str] = []

    def mask_token(match: re.Match) -> str:
        idx = len(tokens)
        token_str = match.group(0)
        tokens.append(token_str)
        return f"__TECH_{idx}__"

    masked = TECHNICAL_TOKEN_REGEX.sub(mask_token, trimmed)

    # Attempt Sarvam AI translation
    translated = ""
    try:
        from ui import speech_service

        if speech_service.is_voice_enabled():
            translated = speech_service.translate_text(
                masked,
                target_language_code="en-IN",
                source_language_code=lang,
            )
    except Exception as exc:
        logger.warning("Online translation failed (%s), falling back to offline normalization", exc)

    # If online translation was not available or produced no change on Indic text
    if not translated or re.search(r"[\u0900-\u0D7F]", translated):
        translated = offline_normalize_text(masked)

    # Restore technical tokens
    for idx, token_str in enumerate(tokens):
        placeholder = f"__TECH_{idx}__"
        translated = translated.replace(placeholder, token_str)
        # Also handle potential whitespace added around placeholders by translation
        translated = re.sub(rf"__\s*TECH\s*_\s*{idx}\s*__", token_str, translated, flags=re.IGNORECASE)

    normalized = re.sub(r"\s+", " ", translated).strip()
    if not normalized:
        normalized = trimmed

    logger.info("Normalized query for retrieval: '%s'", normalized)
    return normalized, lang, trimmed
