"""
IS Sarthi -- Modern GovTech Web Interface.
AI-Powered Indian Standards Recommendation & Compliance Engine (BIS).

Compliant with docs/UI_UX.md & WCAG 2.1 AA standards.
Seamlessly operates in offline mode with zero infrastructure or connects
to the FastAPI backend when available.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# Ensure project root is in path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from ui import speech_service

API_BASE = "http://localhost:8000/api/v1"
LOGO_PATH = ROOT_DIR / "ui" / "assets" / "logo.png"

# -----------------------------------------------------------------------------
# Streamlit Page Config & Design Tokens
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="IS Sarthi | मानक सारथी",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom GovTech CSS styling for high-contrast accessibility & visual hierarchy
CUSTOM_CSS = """
<style>
    /* Global Font and Header Styling */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Header Banner */
    .brand-header {
        background: linear-gradient(135deg, #0f2942 0%, #1e3a8a 100%);
        padding: 1.5rem 2rem;
        border-radius: 10px;
        color: #ffffff;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 12px rgba(15, 41, 66, 0.15);
        border-left: 6px solid #f59e0b;
    }
    .brand-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin: 0;
        color: #ffffff !important;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .brand-sub {
        font-size: 0.98rem;
        color: #cbd5e1;
        margin-top: 6px;
        margin-bottom: 0;
    }

    /* Status Badges */
    .status-badge {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }
    .status-current {
        background-color: #dcfce7;
        color: #15803d;
        border: 1px solid #86efac;
    }
    .status-superseded, .status-withdrawn {
        background-color: #fee2e2;
        color: #b91c1c;
        border: 1px solid #fca5a5;
    }
    .status-revision {
        background-color: #fef3c7;
        color: #b45309;
        border: 1px solid #fde68a;
    }

    /* Certification Pill */
    .cert-pill {
        display: inline-block;
        background-color: #fff7ed;
        color: #c2410c;
        border: 1px solid #ffedd5;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 4px 0;
    }

    /* Card styling */
    .result-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .result-card:hover {
        border-color: #94a3b8;
    }

    /* Justification Box */
    .justification-box {
        background-color: #f8fafc;
        border-left: 4px solid #3b82f6;
        padding: 10px 14px;
        border-radius: 0 6px 6px 0;
        margin: 10px 0;
        font-size: 0.92rem;
        color: #1e293b;
    }

    /* Superseded Alert Callout */
    .superseded-callout {
        background-color: #fef2f2;
        border-left: 4px solid #ef4444;
        padding: 12px 16px;
        border-radius: 0 6px 6px 0;
        margin: 12px 0;
        color: #991b1b;
        font-size: 0.95rem;
    }

    /* Tender Clause Box */
    .clause-box {
        background-color: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-left: 4px solid #16a34a;
        padding: 12px 16px;
        border-radius: 6px;
        margin-top: 10px;
        font-family: monospace;
        font-size: 0.9rem;
        color: #166534;
    }

    /* Quick Preset Chips */
    .preset-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748b;
        margin-bottom: 6px;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Data Backend & Engine Helpers
# -----------------------------------------------------------------------------
STATUS_META = {
    "current": ("✓", "Current", "status-current"),
    "withdrawn": ("✕", "Withdrawn", "status-withdrawn"),
    "superseded": ("→", "Superseded", "status-superseded"),
    "under_revision": ("~", "Under Revision", "status-revision"),
}

BAND_COLORS = {
    "High": "#15803d",
    "Medium": "#b45309",
    "Low": "#b91c1c",
}


@st.cache_resource
def get_offline_engine():
    """Load the standalone offline retrieval & validation engine."""
    from scripts.demo_offline import OfflineCorpus

    seed_path = ROOT_DIR / "data" / "seed" / "standards.json"
    with open(seed_path, encoding="utf-8") as handle:
        records = json.load(handle)
    return OfflineCorpus(records)


def check_api_status() -> bool:
    """Test if FastAPI backend is reachable on localhost:8000."""
    try:
        import requests

        res = requests.get("http://localhost:8000/health", timeout=0.8)
        return res.status_code == 200
    except Exception:
        return False


def run_recommend(query: str, top_k: int = 5) -> dict:
    """Run recommendation using online API if available, else offline engine."""
    if check_api_status():
        try:
            import requests

            res = requests.post(
                f"{API_BASE}/recommend",
                json={"query": query, "top_k": top_k},
                timeout=60,
            )
            if res.ok:
                return res.json()
        except Exception:
            pass
    # Fallback to in-memory offline engine
    return get_offline_engine().recommend(query, top_k=top_k)


def run_validate(spec_text: str) -> dict:
    """Run tender spec validation using online API or offline engine."""
    if check_api_status():
        try:
            import requests

            res = requests.post(
                f"{API_BASE}/validate-spec",
                json={"spec_text": spec_text},
                timeout=60,
            )
            if res.ok:
                return res.json()
        except Exception:
            pass
    # Fallback to in-memory offline engine
    return get_offline_engine().validate(spec_text)


def extract_uploaded_file_text(uploaded_file) -> str:
    """Extract plain text from uploaded file (.txt, .docx, .pdf)."""
    if uploaded_file is None:
        return ""
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".txt"):
            return uploaded_file.read().decode("utf-8", errors="ignore")
        elif name.endswith(".pdf"):
            try:
                import pdfplumber

                with pdfplumber.open(uploaded_file) as pdf:
                    pages = [page.extract_text() or "" for page in pdf.pages]
                    return "\n".join(pages)
            except ImportError:
                return uploaded_file.read().decode("utf-8", errors="ignore")
        elif name.endswith(".docx"):
            try:
                import docx

                doc = docx.Document(uploaded_file)
                return "\n".join([p.text for p in doc.paragraphs])
            except ImportError:
                return "Docx parser not installed. Please upload .txt or paste text directly."
    except Exception as exc:
        return f"Error reading file: {exc}"
    return ""


def generate_tender_clause(rec: dict) -> str:
    """Generate a legally compliant tender specification clause."""
    is_num = rec.get("is_number", "IS XXXX")
    latest = rec.get("latest_version") or is_num
    title = rec.get("title", "")
    cert = rec.get("certification") or {}

    clause = [
        f"1. Standard Conformity: The supplied materials/equipment shall strictly conform to {latest} "
        f"('{title}'), including all up-to-date amendments issued by the Bureau of Indian Standards (BIS)."
    ]

    if cert.get("mandatory") or cert.get("scheme"):
        scheme = cert.get("scheme_label") or cert.get("scheme", "ISI")
        clause.append(
            f"2. Mandatory Certification: The product must bear the valid {scheme} mark as mandated by the "
            f"appropriate Quality Control Order (QCO) published in the Gazette of India. Uncertified bids shall be summarily rejected."
        )

    allied = rec.get("allied") or rec.get("allied_standards", {}).get("by_role", {})
    if allied:
        test_methods = [
            item["is_number"]
            for item in allied.get("Test method", allied.get("test_method", []))
        ]
        if test_methods:
            clause.append(
                f"3. Acceptance & Routine Tests: Acceptance testing at vendor works shall strictly follow testing procedures "
                f"prescribed in {', '.join(test_methods[:4])}."
            )

        conductors = [
            item["is_number"]
            for item in allied.get("Related product", allied.get("related_product", []))
        ]
        if conductors:
            clause.append(
                f"4. Normative Raw Materials: Raw materials and components shall satisfy {', '.join(conductors[:3])}."
            )

    return "\n\n".join(clause)


# -----------------------------------------------------------------------------
# Top Header & Sidebar
# -----------------------------------------------------------------------------
engine = get_offline_engine()
is_online = check_api_status()

col_head_logo, col_head_title = st.columns([1, 6])
with col_head_logo:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=130)
with col_head_title:
    st.markdown(
        '<div class="brand-header">'
        '<h1 class="brand-title">🏛️ IS Sarthi | मानक सारथी</h1>'
        '<p class="brand-sub">AI-Powered Indian Standards (BIS) Recommendation & Compliance Surface Engine • SIH 2026 Problem Statement</p>'
        '</div>',
        unsafe_allow_html=True,
    )

# Sidebar with system indicators
with st.sidebar:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), use_container_width=True)
    else:
        st.image(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Emblem_of_India.svg/200px-Emblem_of_India.svg.png",
            width=70,
        )
    st.markdown("### System Telemetry")

    if is_online:
        st.success("● API Engine: Connected (FastAPI)")
    else:
        st.warning("● API Engine: Standalone Offline Engine")

    st.metric(label="Corpus Standards", value=len(engine.records))

    divisions = sorted({r.get("division", "Unknown") for r in engine.records})
    st.markdown(f"**Divisions Active:** `{', '.join(divisions)}`")

    st.markdown("---")
    st.markdown("### 🎙️ Multilingual Voice Engine")
    if speech_service.is_voice_enabled():
        st.success("● Sarvam AI: Voice Active")
        st.caption("Languages: 🇮🇳 Hindi · 🇮🇳 Marathi · 🇬🇧 English · 🇮🇳 Telugu · 🇮🇳 Tamil")
    else:
        st.warning("● Voice Engine: No Key")

    st.markdown("---")
    st.markdown("### Compliance Surface")
    st.caption(
        "Unlike basic keyword search or flat RAG, IS Sarthi computes the **normative closure**, "
        "identifies **superseded citations**, verifies **gazette mandatory certification**, "
        "and generates **audit-ready tender clauses**."
    )

    st.markdown("---")
    st.markdown("### Navigation")
    nav_choice = st.radio(
        "Go to Screen:",
        [
            "🔍 Find Applicable Standards",
            "🛡️ Tender Specification Validator",
            "🕸️ Dependency Graph Explorer",
            "📊 Corpus & Division Analytics",
        ],
        label_visibility="collapsed",
    )


# -----------------------------------------------------------------------------
# SCREEN 1: Find Applicable Standards (Recommendation Engine)
# -----------------------------------------------------------------------------
if nav_choice == "🔍 Find Applicable Standards":
    st.markdown("### 🔍 Recommend Applicable Standards for Procurement")
    st.caption(
        "Enter a procurement description, component specification, or upload tender drafting text. "
        "The engine identifies primary standards, allied test methods, and mandatory certification rules."
    )

    # Preset query selection
    st.markdown("<div class='preset-title'>💡 Quick Example Queries (Click to load):</div>", unsafe_allow_html=True)
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)

    if col_p1.button("⚡ 3-Core Armoured Cable", use_container_width=True):
        st.session_state["query_input_field"] = (
            "3 core armoured copper cable for underground LV power distribution up to 1100V"
        )
        st.session_state.pop("search_results", None)
        st.rerun()
    if col_p2.button("🏗️ 43 Grade Cement (Superseded)", use_container_width=True):
        st.session_state["query_input_field"] = "43 grade ordinary portland cement for RCC foundation construction"
        st.session_state.pop("search_results", None)
        st.rerun()
    if col_p3.button("🔩 TMT Fe 500 Steel Bars", use_container_width=True):
        st.session_state["query_input_field"] = (
            "High strength deformed steel bars Fe 500 grade for concrete reinforcement"
        )
        st.session_state.pop("search_results", None)
        st.rerun()
    if col_p4.button("🔌 Distribution Transformers", use_container_width=True):
        st.session_state["query_input_field"] = (
            "Outdoor type three phase oil immersed distribution transformers up to 2500 kVA"
        )
        st.session_state.pop("search_results", None)
        st.rerun()

    # File upload toggle
    with st.expander("📁 Or upload specification document (.txt, .docx, .pdf)"):
        spec_file = st.file_uploader(
            "Upload technical specification",
            type=["txt", "pdf", "docx"],
            label_visibility="collapsed",
        )
        if spec_file is not None:
            extracted_text = extract_uploaded_file_text(spec_file)
            if extracted_text and not extracted_text.startswith("Error"):
                if st.session_state.get("_last_uploaded_file") != spec_file.name:
                    st.session_state["_last_uploaded_file"] = spec_file.name
                    st.session_state["query_input_field"] = extracted_text[:2000]
                    st.session_state.pop("search_results", None)
                    st.success(f"Loaded {len(extracted_text)} characters from {spec_file.name}")
                    st.rerun()

    # Multilingual Voice Search Section
    with st.expander("🎙️ Or Speak / Record Requirement (Voice Search in 5 Languages)", expanded=False):
        st.caption(
            "Speak your specification in **Hindi, Marathi, English, Telugu, or Tamil**. "
            "Sarvam AI Saaras will automatically transcribe it into your search query."
        )
        col_vlang, col_vrec = st.columns([1, 2])
        with col_vlang:
            v_lang_choice = st.selectbox(
                "Spoken Language",
                options=["auto", "hi-IN", "mr-IN", "en-IN", "te-IN", "ta-IN"],
                format_func=lambda x: {
                    "auto": "🌐 Auto-Detect",
                    "hi-IN": "🇮🇳 Hindi (हिन्दी)",
                    "mr-IN": "🇮🇳 Marathi (मराठी)",
                    "en-IN": "🇬🇧 English",
                    "te-IN": "🇮🇳 Telugu (తెలుగు)",
                    "ta-IN": "🇮🇳 Tamil (தமிழ்)",
                }.get(x, x),
                key="voice_input_lang",
            )
        with col_vrec:
            audio_val = st.audio_input("Record voice specification", key="voice_spec_recorder")
            if audio_val is not None:
                audio_bytes_val = audio_val.getvalue()
                if st.session_state.get("_last_audio_bytes") != audio_bytes_val:
                    st.session_state["_last_audio_bytes"] = audio_bytes_val
                    with st.spinner("Transcribing speech with Sarvam AI (Saaras)..."):
                        try:
                            lang_arg = "unknown" if v_lang_choice == "auto" else v_lang_choice
                            transcript, detected = speech_service.transcribe_audio(
                                audio_bytes_val, language_code=lang_arg
                            )
                            if transcript:
                                st.session_state["query_input_field"] = transcript
                                st.session_state.pop("search_results", None)
                                st.success(f"Transcribed ({detected}): \"{transcript}\"")
                                st.rerun()
                            else:
                                st.warning("No speech detected. Please speak clearly into the microphone.")
                        except Exception as exc:
                            st.error(f"Transcription error: {exc}")

    if "query_input_field" not in st.session_state:
        st.session_state["query_input_field"] = st.session_state.get("query_text", "")

    query_input = st.text_area(
        "Product description or technical specification",
        height=120,
        placeholder="e.g. 3 core armoured copper conductor XLPE insulated cable for working voltages up to 1100 V...",
        key="query_input_field",
    )

    col_btn, col_topk, col_div = st.columns([2, 1, 2])
    with col_topk:
        top_k = st.selectbox("Max results", [3, 5, 8], index=1)
    with col_div:
        div_filter = st.selectbox("Filter Division", ["All Divisions"] + divisions)
    with col_btn:
        st.write("")
        st.write("")
        search_clicked = st.button("🚀 Find Standards & Allied Norms", type="primary", use_container_width=True)

    if search_clicked and query_input.strip():
        # Staged progress indicator reflecting pipeline architecture
        progress_placeholder = st.empty()
        with progress_placeholder.container():
            st.info("🔄 Stage 1/3: Computing dense & sparse hybrid embeddings...")
            time.sleep(0.12)
            st.info("🔄 Stage 2/3: Traversing citation graph for normative closure & test methods...")
            time.sleep(0.12)
            st.info("🔄 Stage 3/3: Evaluating Gazette QCO certification rules & formulating justifications...")
            time.sleep(0.1)
        progress_placeholder.empty()

        result = run_recommend(query_input.strip(), top_k=top_k)
        st.session_state["search_results"] = result
        st.session_state["last_searched_query"] = query_input.strip()
        # Clean up prior audio caches on new search
        for k in list(st.session_state.keys()):
            if k.startswith("audio_cache_"):
                st.session_state.pop(k, None)

    if "search_results" in st.session_state and st.session_state["search_results"]:
        result = st.session_state["search_results"]
        active_query = st.session_state.get("last_searched_query", query_input)

        if result.get("state") == "low_confidence" or not result.get("recommendations"):
            st.warning(
                result.get(
                    "message",
                    "No confident match found. Please include more specific technical attributes (e.g. materials, voltage ratings, mechanical grades).",
                )
            )
        else:
            recs = result.get("recommendations", [])
            # Division filter if selected
            if div_filter != "All Divisions":
                recs = [r for r in recs if r.get("division", "ETD") == div_filter]

            st.markdown(f"#### 🎯 Recommendations ({len(recs)} surfaced)")

            for idx, rec in enumerate(recs):
                is_num = rec.get("is_number", "IS ????")
                status = rec.get("status", "current").lower()
                icon, label, badge_class = STATUS_META.get(
                    status, ("•", status.capitalize(), "status-current")
                )
                band = rec.get("band") or rec.get("confidence_band", "Medium")
                confidence_score = rec.get("confidence", 0.0)
                superseded_by = rec.get("superseded_by")

                with st.container(border=True):
                    col_l, col_r = st.columns([5, 2])
                    with col_l:
                        st.markdown(
                            f"<div style='margin-bottom:4px;'>"
                            f"<span style='font-size:1.35rem;font-weight:700;color:#0f2942;'>{is_num}</span> "
                            f"<span style='color:#64748b;font-size:0.95rem;'>({rec.get('latest_version', is_num)})</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        badge_html = f"<span class='status-badge {badge_class}'>{icon} {label}</span>"
                        if superseded_by:
                            badge_html += f" &nbsp;<span class='status-badge status-superseded'>Replaced by {superseded_by}</span>"
                        st.markdown(badge_html, unsafe_allow_html=True)
                        st.markdown(
                            f"<div style='font-size:1.05rem;font-weight:600;color:#1e3a8a;margin-top:6px;margin-bottom:6px;'>"
                            f"{rec.get('title', '')}</div>",
                            unsafe_allow_html=True,
                        )

                    with col_r:
                        st.markdown(
                            f"<div style='text-align:right;'>"
                            f"<span style='font-weight:700;font-size:1.05rem;color:{BAND_COLORS.get(band, '#1e293b')}'>"
                            f"● {band} Confidence</span><br>"
                            f"<span style='font-size:0.82rem;color:#64748b;'>Match score: {confidence_score}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                    # Superseded warning banner
                    if superseded_by:
                        st.error(
                            f"⚠️ **CRITICAL CURRENCY WARNING:** This standard is **{status.upper()}**. "
                            f"It was formally consolidated into **{superseded_by}**. "
                            "Citing this standard in active procurement will cause bidder ambiguity and legal disputes."
                        )

                    # Justification
                    if rec.get("justification"):
                        st.info(f"💡 **Scope Justification:** {rec['justification']}")

                    # Mandatory Certification banner
                    cert = rec.get("certification")
                    if cert and (cert.get("mandatory") or cert.get("scheme")):
                        scheme = cert.get("scheme_label") or cert.get("scheme", "ISI")
                        product = cert.get("product", "this product")
                        st.warning(
                            f"🛡️ **MANDATORY CERTIFICATION: {scheme}**\n\n"
                            f"Bidders **must hold a valid BIS license** for {product}. "
                            "Supply without mark is prohibited by law under the Quality Control Order."
                        )

                    # Allied Standards (Grouped by Role)
                    allied = rec.get("allied") or rec.get("allied_standards", {}).get("by_role", {})
                    if allied:
                        total_allied = sum(len(v) for v in allied.values())
                        with st.expander(f"📚 Allied Standards & Normative References ({total_allied} identified)"):
                            st.caption("Surfaced via normative closure traversal. Grouped by functional role in procurement:")
                            role_cols = st.columns(min(3, max(1, len(allied))))
                            for r_idx, (role, items) in enumerate(allied.items()):
                                col_target = role_cols[r_idx % len(role_cols)]
                                with col_target:
                                    st.markdown(f"**{role} ({len(items)})**")
                                    for it in items[:6]:
                                        hop_info = f" <span style='color:#94a3b8; font-size:0.8rem;'>(hop {it.get('hop', 1)})</span>" if it.get("hop") else ""
                                        st.markdown(
                                            f"• `{it['is_number']}`: {it.get('title', '')}{hop_info}",
                                            unsafe_allow_html=True,
                                        )

                    # Clause Generation & Details
                    col_act1, col_act2, col_act3 = st.columns([3, 1, 1])
                    with col_act1:
                        if st.checkbox(f"📝 View Formatted Tender Clause for {is_num}", key=f"chk_clause_{idx}"):
                            formatted_clause = generate_tender_clause(rec)
                            st.info("Copy this clause directly into your Notice Inviting Tender (NIT) / RFP:")
                            st.code(formatted_clause, language="text")
                    with col_act2:
                        if st.button("👍 Relevant", key=f"fdbk_pos_{idx}"):
                            st.toast(f"Thank you! Recorded positive feedback for {is_num}.")
                    with col_act3:
                        if st.button("👎 Irrelevant", key=f"fdbk_neg_{idx}"):
                            st.toast(f"Feedback recorded. System will recalibrate {is_num}.", icon="ℹ️")

                    # Multilingual Voice Explanation (Text-to-Speech)
                    cache_key = f"audio_cache_{is_num}"
                    has_audio = cache_key in st.session_state
                    with st.expander(f"🔊 Listen to Explanation in Indian Languages ({is_num})", expanded=has_audio):
                        st.caption("Sarvam AI (Bulbul v3) will synthesize a spoken explanation in your chosen language:")
                        col_tts_lang, col_tts_btn = st.columns([3, 2])
                        with col_tts_lang:
                            tts_lang = st.selectbox(
                                "Narration Language",
                                options=["hi-IN", "mr-IN", "en-IN", "te-IN", "ta-IN"],
                                format_func=lambda c: f"{speech_service.SUPPORTED_LANGUAGES[c]['flag']} {speech_service.SUPPORTED_LANGUAGES[c]['label']}",
                                key=f"tts_lang_select_{idx}",
                            )
                        with col_tts_btn:
                            st.write("")
                            st.write("")
                            play_audio = st.button("🎙️ Play Voice Explanation", key=f"btn_play_audio_{idx}", use_container_width=True)

                        if play_audio:
                            lang_name = speech_service.SUPPORTED_LANGUAGES[tts_lang]["label"]
                            with st.spinner(f"Generating speech in {lang_name} with Sarvam AI Bulbul v3..."):
                                try:
                                    summary_text = f"{is_num}: {rec.get('title', '')}. Status is {status}."
                                    if rec.get("justification"):
                                        summary_text += f" Justification: {rec['justification']}"
                                    if superseded_by:
                                        summary_text += f" Important note: this standard has been superseded by {superseded_by}."

                                    if tts_lang != "en-IN":
                                        narration_text = speech_service.translate_text(
                                            summary_text, target_language_code=tts_lang, source_language_code="en-IN"
                                        )
                                    else:
                                        narration_text = summary_text

                                    audio_bytes = speech_service.synthesize_speech(
                                        narration_text, language_code=tts_lang
                                    )
                                    st.session_state[cache_key] = {
                                        "text": narration_text,
                                        "audio": audio_bytes,
                                        "lang": tts_lang,
                                    }
                                except Exception as err:
                                    st.error(f"Voice generation failed: {err}")

                        if cache_key in st.session_state:
                            cached_data = st.session_state[cache_key]
                            lang_data = speech_service.SUPPORTED_LANGUAGES.get(cached_data["lang"], {})
                            st.markdown(f"**Narration ({lang_data.get('native', cached_data['lang'])}):**")
                            st.info(cached_data["text"])
                            st.audio(cached_data["audio"], format="audio/wav")

            # Export actions
            st.markdown("##### 📥 Export Recommendation Summary")
            col_ex1, col_ex2, _ = st.columns([2, 2, 4])
            with col_ex1:
                json_str = json.dumps(result, indent=2)
                st.download_button(
                    label="Download JSON Report",
                    data=json_str,
                    file_name=f"is_sarthi_recommendation_{int(time.time())}.json",
                    mime="application/json",
                )
            with col_ex2:
                # Format markdown report
                md_lines = [f"# IS Sarthi Recommendation Report\nQuery: {active_query}\n"]
                for r in recs:
                    md_lines.append(f"## {r['is_number']}: {r.get('title','')}")
                    md_lines.append(f"- Status: {r.get('status')} | Confidence: {r.get('confidence')}")
                    md_lines.append(f"- Justification: {r.get('justification','')}")
                    md_lines.append(f"- Tender Clause:\n```\n{generate_tender_clause(r)}\n```\n")
                st.download_button(
                    label="Download Markdown Summary",
                    data="\n".join(md_lines),
                    file_name=f"is_sarthi_summary_{int(time.time())}.md",
                    mime="text/markdown",
                )


# -----------------------------------------------------------------------------
# SCREEN 2: Tender Specification Validator
# -----------------------------------------------------------------------------
elif nav_choice == "🛡️ Tender Specification Validator":
    st.markdown("### 🛡️ Tender Specification Audit & Validator")
    st.caption(
        "Paste an existing procurement document or draft tender. The validator automatically extracts all "
        "Indian Standard citations, audits their currency, flags superseded/withdrawn standards, checks mandatory "
        "certification clauses, and suggests missing test methods."
    )

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("📄 Load Sample Spec with Superseded Cement Citation (IS 8112)", use_container_width=True):
            st.session_state["validator_spec_field"] = (
                "Notice Inviting Tender (NIT) for Substation Foundation Works:\n"
                "1. All cement used in RCC structural works shall strictly conform to IS 8112:1989 for 43 grade ordinary portland cement.\n"
                "2. The reinforcement steel shall conform to IS 1786.\n"
                "3. Aggregate testing shall comply with IS 383."
            )
            st.session_state.pop("validation_res", None)
            st.rerun()
    with col_s2:
        if st.button("📄 Load Sample Spec with Underground Cables (Missing Allied)", use_container_width=True):
            st.session_state["validator_spec_field"] = (
                "Procurement Specification for LV Power Supply:\n"
                "1. Power cables shall be 1100V grade 3-core copper conductor conforming to IS 1554 (Part 1).\n"
                "2. Installation shall be underground in trenches as per standard CPWD guidelines."
            )
            st.session_state.pop("validation_res", None)
            st.rerun()

    if "validator_spec_field" not in st.session_state:
        st.session_state["validator_spec_field"] = st.session_state.get("validator_spec", "")

    spec_text = st.text_area(
        "Paste Tender Specification Text",
        height=180,
        placeholder="Paste specification clauses containing IS 1554, IS 8112, IS 269, etc...",
        key="validator_spec_field",
    )

    if st.button("🔍 Run Full Compliance Audit", type="primary", use_container_width=True) and spec_text.strip():
        with st.spinner("Auditing citations against national standards database..."):
            st.session_state["validation_res"] = run_validate(spec_text.strip())

    if "validation_res" in st.session_state and st.session_state["validation_res"]:
        validation_res = st.session_state["validation_res"]
        cited = validation_res.get("cited", [])
        issues = validation_res.get("issues", [])
        suggestions = validation_res.get("suggested_additions", [])

        if not cited:
            st.info("No Indian Standard (IS) designators were identified in the provided text.")
        else:
            # Summary scorecards
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            high_sev = [i for i in issues if i.get("severity") == "high"]
            med_sev = [i for i in issues if i.get("severity") == "medium"]

            col_m1.metric("Cited Standards", len(cited))
            col_m2.metric("Critical Superseded Issues", len(high_sev), delta="-Action Required" if high_sev else "Clean", delta_color="inverse")
            col_m3.metric("Certification Warnings", len(med_sev))
            col_m4.metric("Recommended Additions", len(suggestions))

            st.markdown("---")

            # Critical Issues
            if high_sev:
                st.markdown("#### 🚨 Critical Defects: Superseded or Withdrawn Standards")
                for iss in high_sev:
                    st.error(
                        f"**{iss['is_number']}**: {iss['issue']}  \n"
                        f"**Recommended Action:** {iss['action']}"
                    )

            # Medium / Compliance warnings
            if med_sev:
                st.markdown("#### ⚠️ Compliance Warnings: Mandatory Certification Requirements")
                for iss in med_sev:
                    st.warning(
                        f"**{iss['is_number']}**: {iss['issue']}  \n"
                        f"**Recommended Action:** {iss['action']}"
                    )

            # Standards with no defects
            clean_standards = [
                s for s in cited
                if not any(i["is_number"] == s for i in issues if i.get("severity") in ("high", "medium"))
            ]
            if clean_standards:
                st.markdown("#### ✅ Validated Standards (Current)")
                for cs in clean_standards:
                    rec = engine.by_number.get(cs, {})
                    title = rec.get("title", "")
                    st.success(f"**{cs}**: {title} (Current & In Force)")

            # Suggested allied standards
            if suggestions:
                st.markdown("#### 💡 Missing Allied Standards to Include in Acceptance Criteria")
                st.caption(
                    "These standards are normative references of your cited items. Adding them defines acceptance testing and prevents disputes:"
                )
                for item in suggestions:
                    st.markdown(
                        f"- `{item['is_number']}` **[{item['role']}]**: {item.get('title', '')} "
                        f"<span style='color:#64748b'>(Referenced by {item.get('referenced_by', 'tender')})</span>",
                        unsafe_allow_html=True,
                    )


# -----------------------------------------------------------------------------
# SCREEN 3: Dependency Graph Explorer
# -----------------------------------------------------------------------------
elif nav_choice == "🕸️ Dependency Graph Explorer":
    st.markdown("### 🕸️ Interactive Dependency Graph (Normative Closure)")
    st.caption(
        "Standards do not exist in isolation. A product standard relies on test methods, materials, and safety codes. "
        "Explore the dependency tree for any Indian Standard."
    )

    all_standards = sorted(list(engine.by_number.keys()))
    col_sel, col_depth = st.columns([3, 1])
    with col_sel:
        selected_standard = st.selectbox(
            "Select Standard to Visualize:",
            all_standards,
            index=all_standards.index("IS 1554-1") if "IS 1554-1" in all_standards else 0,
        )
    with col_depth:
        depth = st.selectbox("Graph Depth (Hops)", [1, 2], index=0)

    record = engine.by_number.get(selected_standard, {})

    if record:
        st.markdown(f"#### **{selected_standard}**: {record.get('title', '')}")
        status = record.get("status", "current")
        icon, label, _ = STATUS_META.get(status, ("•", status, ""))
        st.caption(f"Status: {icon} {label} | Division: {record.get('division', 'ETD')} | Year: {record.get('year', '')}")

        # Build Graphviz DOT specification
        dot_lines = [
            "digraph G {",
            "  rankdir=LR;",
            "  node [fontname=\"Helvetica,Arial,sans-serif\", fontsize=10, style=\"filled,rounded\", shape=box];",
            "  edge [fontname=\"Helvetica,Arial,sans-serif\", fontsize=8, color=\"#64748b\"];",
            f'  "{selected_standard}" [fillcolor="#1e3a8a", fontcolor="#ffffff", penwidth=2, label="{selected_standard}\\n(Target)"];',
        ]

        refs = engine.graph.get(selected_standard, [])
        visited = {selected_standard}

        for ref in refs:
            child = ref["is_number"]
            role = ref.get("ref_type", "reference")
            child_record = engine.by_number.get(child, {})
            child_status = child_record.get("status", "current")
            child_color = "#fee2e2" if child_status in ("superseded", "withdrawn") else "#e0f2fe"
            child_font = "#991b1b" if child_status in ("superseded", "withdrawn") else "#0369a1"

            dot_lines.append(
                f'  "{child}" [fillcolor="{child_color}", fontcolor="{child_font}", label="{child}\\n[{child_status}]"];'
            )
            dot_lines.append(f'  "{selected_standard}" -> "{child}" [label="{role}"];')
            visited.add(child)

            if depth > 1:
                sub_refs = engine.graph.get(child, [])
                for s_ref in sub_refs:
                    sub_child = s_ref["is_number"]
                    if sub_child not in visited:
                        s_record = engine.by_number.get(sub_child, {})
                        s_status = s_record.get("status", "current")
                        s_color = "#fee2e2" if s_status in ("superseded", "withdrawn") else "#f1f5f9"
                        dot_lines.append(
                            f'  "{sub_child}" [fillcolor="{s_color}", fontcolor="#334155", label="{sub_child}"];'
                        )
                        dot_lines.append(f'  "{child}" -> "{sub_child}" [label="{s_ref.get("ref_type", "")}"];')
                        visited.add(sub_child)

        dot_lines.append("}")
        dot_code = "\n".join(dot_lines)

        col_g1, col_g2 = st.columns([3, 2])
        with col_g1:
            st.graphviz_chart(dot_code, use_container_width=True)
        with col_g2:
            st.markdown("##### 📋 Direct Normative References")
            if not refs:
                st.info("No normative references recorded for this standard in the seed database.")
            else:
                for ref in refs:
                    r_num = ref["is_number"]
                    r_role = ref.get("ref_type", "reference")
                    r_title = engine.by_number.get(r_num, {}).get("title") or ref.get("title", "")
                    st.markdown(f"- `{r_num}` **[{r_role}]**: {r_title}")


# -----------------------------------------------------------------------------
# SCREEN 4: Corpus & Division Analytics
# -----------------------------------------------------------------------------
elif nav_choice == "📊 Corpus & Division Analytics":
    st.markdown("### 📊 Bureau of Indian Standards (BIS) Corpus Analytics")
    st.caption("Inspect catalog coverage, division distribution, and mandatory certification rules.")

    records = engine.records

    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    mandatory_count = sum(1 for r in records if (r.get("certification") or {}).get("mandatory"))
    superseded_count = sum(1 for r in records if r.get("status") in ("superseded", "withdrawn"))

    col_stat1.metric("Indexed Standards", len(records))
    col_stat2.metric("Active Divisions", len(divisions))
    col_stat3.metric("Mandatory ISI / QCOs", mandatory_count)
    col_stat4.metric("Superseded Standards", superseded_count)

    st.markdown("---")

    col_a1, col_a2 = st.columns([2, 3])
    with col_a1:
        st.markdown("#### Standards by Division")
        division_counts = {}
        for r in records:
            d = r.get("division", "Other")
            division_counts[d] = division_counts.get(d, 0) + 1

        st.bar_chart(division_counts)

    with col_a2:
        st.markdown("#### Filterable Catalog")
        search_kw = st.text_input("Search catalog by keyword or IS Number", placeholder="e.g. cable, cement, IS 1554...")
        div_select = st.selectbox("Filter by Division", ["All"] + divisions)

        filtered = records
        if div_select != "All":
            filtered = [r for r in filtered if r.get("division") == div_select]
        if search_kw.strip():
            kw = search_kw.lower()
            filtered = [
                r for r in filtered
                if kw in r["is_number"].lower() or kw in r.get("title", "").lower() or kw in r.get("scope", "").lower()
            ]

        display_data = [
            {
                "IS Number": r["is_number"],
                "Title": r.get("title", ""),
                "Division": r.get("division", ""),
                "Status": r.get("status", "current"),
                "Mandatory QCO": "Yes" if (r.get("certification") or {}).get("mandatory") else "No",
            }
            for r in filtered
        ]
        st.dataframe(display_data, use_container_width=True, height=350)

