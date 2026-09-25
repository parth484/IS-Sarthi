"""
Comprehensive test suite for IS Sarthi feature upgrades.
Tests:
1. Multi-format document text extraction (PDF, DOCX, TXT)
2. Empty, corrupted, and password-protected document error handling
3. Allied standard role taxonomy (Test method, Safety, Installation, Terminology, Related product)
4. Certification scheme granularity (ISI/QCO, CRS, Hallmarking) in tender clauses
5. Multilingual query normalization and technical token preservation
6. Procurement portal connector and recommendation ingestion flow
7. Verification of the 57 offline standards in the corpus
"""
from __future__ import annotations

import io
import json
import pytest
from pathlib import Path

from fastapi.testclient import TestClient
from api.index import app, corpus, generate_tender_clause
from pipeline.scrapers.doc_extractor import extract_document_text
from pipeline.utils.multilingual import (
    detect_query_language,
    normalize_query_for_retrieval,
)
from pipeline.procurement.service import ProcurementService
from pipeline.procurement.connector import GeMProcurementConnector

client = TestClient(app)


# =============================================================================
# 1. Multi-Format Document Extraction Tests
# =============================================================================
def test_txt_extraction():
    content = b"Technical specification for 1100V power cable with copper conductor."
    text = extract_document_text(content, "spec.txt")
    assert "1100V" in text
    assert "copper conductor" in text


def test_docx_extraction():
    import docx
    doc = docx.Document()
    doc.add_paragraph("Specification for Fe 500 grade TMT steel reinforcement bars.")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Standard"
    table.rows[0].cells[1].text = "IS 1786"
    buf = io.BytesIO()
    doc.save(buf)

    text = extract_document_text(buf.getvalue(), "tender.docx")
    assert "Fe 500" in text
    assert "IS 1786" in text


def test_pdf_extraction():
    import pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)

    # Empty blank PDF should report no readable text
    with pytest.raises(ValueError, match="No readable text found"):
        extract_document_text(buf.getvalue(), "blank.pdf")


def test_document_error_handling():
    # Empty 0-byte file
    with pytest.raises(ValueError, match="is empty"):
        extract_document_text(b"", "empty.txt")

    # Unsupported format
    with pytest.raises(ValueError, match="Unsupported document format"):
        extract_document_text(b"some content", "data.xlsx")

    # Corrupt DOCX
    with pytest.raises(ValueError, match="Corrupted or invalid DOCX"):
        extract_document_text(b"not a valid zip file", "corrupted.docx")

    # Encrypted PDF
    import pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("mypassword")
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(ValueError, match="password-protected"):
        extract_document_text(buf.getvalue(), "encrypted.pdf")


# =============================================================================
# 2. API Document Extraction Endpoints
# =============================================================================
def test_api_extract_document_txt():
    res = client.post(
        "/api/extract-document",
        files={"file": ("spec.txt", b"3 core armoured cable 1100 V", "text/plain")},
    )
    assert res.status_code == 200
    data = res.json()
    assert "cable 1100 V" in data["text"]
    assert data["format"] == "txt"


def test_api_extract_document_backward_compatibility():
    # /api/extract-pdf should forward to the extraction endpoint
    res = client.post(
        "/api/extract-pdf",
        files={"file": ("spec.txt", b"Testing backward compatibility", "text/plain")},
    )
    assert res.status_code == 200
    assert "Testing backward compatibility" in res.json()["text"]


# =============================================================================
# 3. Allied Standard Role Taxonomy Tests
# =============================================================================
def test_allied_role_taxonomy():
    from pipeline.classify import classify_all, ROLE_LABELS

    titles = {r["is_number"]: r.get("title", "") for r in corpus.records}
    all_roles = set()
    for r in corpus.records:
        classified = classify_all(r.get("normative_references", []), title_lookup=titles)
        for c in classified:
            role_label = ROLE_LABELS.get(c["ref_type"])
            all_roles.add(role_label)

    # Verify that explicit roles are present across the reference graph
    assert "Test method" in all_roles
    assert "Related product" in all_roles
    assert "Terminology" in all_roles
    assert "Safety" in all_roles
    assert "Installation" in all_roles


def test_dependency_graph_role_labels():
    res = client.get("/api/standards/IS%201554-1/graph?depth=1")
    assert res.status_code == 200
    data = res.json()
    assert "edges" in data
    assert len(data["edges"]) > 0
    # Edges should have capitalized taxonomy labels
    edge_roles = {e["role"] for e in data["edges"]}
    assert any(r in edge_roles for r in ["Test method", "Related product", "Safety", "Installation", "Terminology"])


# =============================================================================
# 4. Certification Scheme Granularity Tests
# =============================================================================
def test_tender_clause_certification_schemes():
    # 1. ISI / QCO
    rec_isi = {
        "is_number": "IS 1554-1",
        "latest_version": "IS 1554 (Part 1):1988",
        "title": "PVC Insulated Electric Cables",
        "certification": {
            "scheme": "ISI",
            "scheme_label": "BIS Product Certification (ISI mark)",
            "mandatory": True,
            "product": "PVC insulated cables",
        },
    }
    clause_isi = generate_tender_clause(rec_isi)
    assert "Standard ISI Mark" in clause_isi
    assert "Quality Control Order (QCO)" in clause_isi

    # 2. CRS (Compulsory Registration Scheme)
    rec_crs = {
        "is_number": "IS 16046-1",
        "latest_version": "IS 16046 (Part 1):2018",
        "title": "Secondary Cells and Batteries Containing Alkaline or Other Non-Acid Electrolytes",
        "certification": {
            "scheme": "CRS",
            "scheme_label": "BIS Compulsory Registration Scheme",
            "mandatory": True,
            "product": "Lithium ion batteries",
        },
    }
    clause_crs = generate_tender_clause(rec_crs)
    assert "Compulsory Registration Scheme (CRS)" in clause_crs
    assert "R-number" in clause_crs

    # 3. Hallmarking
    rec_hallmark = {
        "is_number": "IS 1417",
        "latest_version": "IS 1417:2016",
        "title": "Gold and Gold Alloys, Jewellery/Artefacts - Fineness and Marking",
        "certification": {
            "scheme": "Hallmarking",
            "scheme_label": "BIS Hallmarking",
            "mandatory": True,
            "product": "Gold jewellery and artefacts",
        },
    }
    clause_hallmark = generate_tender_clause(rec_hallmark)
    assert "BIS Hallmarking" in clause_hallmark
    assert "HUID" in clause_hallmark


# =============================================================================
# 5. Multilingual Query Support Tests
# =============================================================================
def test_multilingual_language_detection():
    assert detect_query_language("3 core armoured copper cable 1100 V") == "en-IN"
    assert detect_query_language("भूमिगत बिजली वितरण के लिए 3 core केबल") == "hi-IN"
    assert detect_query_language("बांधकामासाठी 43 ग्रेड सिमेंट आणि स्टील बार") == "mr-IN"


def test_multilingual_query_normalization():
    # English query should remain unmodified
    en_q = "3 core armoured copper cable for underground power 1100 V"
    norm_en, lang_en, _ = normalize_query_for_retrieval(en_q)
    assert lang_en == "en-IN"
    assert norm_en == en_q

    # Hindi query with technical tokens preserved
    hi_q = "भूमिगत बिजली वितरण के लिए 3 core armoured copper cable up to 1100 V"
    norm_hi, lang_hi, orig_hi = normalize_query_for_retrieval(hi_q)
    assert lang_hi == "hi-IN"
    assert "3 core" in norm_hi
    assert "1100 V" in norm_hi
    assert orig_hi == hi_q

    # Marathi query with IS number preserved
    mr_q = "बांधकामासाठी सिमेंट आणि स्टील सळया IS 1786"
    norm_mr, lang_mr, _ = normalize_query_for_retrieval(mr_q)
    assert lang_mr == "mr-IN"
    assert "IS 1786" in norm_mr


def test_api_multilingual_recommend():
    # Query in Hindi
    res = client.post("/api/recommend", json={"query": "भूमिगत बिजली के लिए 3 core armoured cable 1100 V", "top_k": 3})
    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "ok"
    assert data["detected_language"] == "hi-IN"
    # Original user query is preserved for display
    assert data["query"] == "भूमिगत बिजली के लिए 3 core armoured cable 1100 V"
    assert len(data["recommendations"]) > 0


# =============================================================================
# 6. Procurement Portal Integration Tests
# =============================================================================
def test_procurement_service_sample_tenders():
    service = ProcurementService(corpus)
    samples = service.get_sample_tenders()
    assert len(samples) >= 3
    for s in samples:
        assert "tender_id" in s
        assert "raw_specification" in s


def test_procurement_ingest_flow():
    service = ProcurementService(corpus)
    res = service.ingest_and_recommend("GEM/2026/B/892104")
    assert res["state"] == "ok"
    assert len(res["recommendations"]) > 0
    top = res["recommendations"][0]
    # Cable tender should surface cable standards
    assert "IS 7098-1" in top["is_number"] or "IS 1554-1" in top["is_number"]
    assert "tender" in res
    assert res["tender"]["portal"] == "Government e-Marketplace (GeM)"


def test_api_procurement_endpoints():
    # 1. GET sample tenders
    res_samples = client.get("/api/procurement/sample-tenders")
    assert res_samples.status_code == 200
    samples = res_samples.json()
    assert len(samples) >= 3

    # 2. POST ingest tender
    res_ingest = client.post(
        "/api/procurement/ingest",
        json={"tender_id_or_data": "GEM/2026/B/452189", "portal": "gem", "top_k": 3},
    )
    assert res_ingest.status_code == 200
    data = res_ingest.json()
    assert data["state"] == "ok"
    assert len(data["recommendations"]) > 0


# =============================================================================
# 7. Verification of 57 Seed Standards & Amendments
# =============================================================================
def test_seed_standards_count_and_integrity():
    assert len(corpus.records) == 57
    for r in corpus.records:
        assert "is_number" in r
        assert "title" in r
        assert "division" in r


def test_recommendation_amendments_surfaced():
    res = client.post("/api/recommend", json={"query": "PVC insulated electric cables 1100 V", "top_k": 3})
    assert res.status_code == 200
    recs = res.json()["recommendations"]
    target = next((r for r in recs if r["is_number"] == "IS 1554-1"), None)
    assert target is not None
    # Amendments must be surfaced in recommendation object
    assert "amendments" in target
    assert isinstance(target["amendments"], list)
    assert len(target["amendments"]) > 0
    assert target["amendments"][0]["number"] == "1"
