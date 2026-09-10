import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.text_processor import normalize_arabic_text, parse_law_articles, extract_article_number

client = TestClient(app)

def test_normalize_arabic_text():
    # Presentation form conversion test
    raw = "ﻣﺎﺩﺓ )٣( : ﻳﻌﻤﻞ ﺑﻬﺬﺍ ﺍﻟﻘﺎﻧﻮﻥ."
    normalized = normalize_arabic_text(raw)
    assert "مادة" in normalized
    assert "يعمل" in normalized

def test_extract_article_number():
    sample1 = "مادة (2): الإسلام دين الدولة"
    sample2 = "المادة الأولى: تعلن نتيجة الاستفتاء"
    sample3 = "مادة 206: كل من زور..."
    
    assert extract_article_number(sample1) in ["2", "٢"]
    assert extract_article_number(sample2) in ["الأولى"]
    assert extract_article_number(sample3) in ["206"]

def test_parse_law_articles():
    sample_law = """
    مادة (1): جمهورية مصر العربية دولة ذات سيادة.
    مادة (2): الإسلام دين الدولة واللغة العربية لغتها الرسمية.
    المادة (3): مبادئ شرائع المصريين من المسيحيين واليهود.
    """
    chunks = parse_law_articles(sample_law, "دستور مصر")
    assert len(chunks) == 3
    assert chunks[0]["article_number"] in ["1", "١"]
    assert chunks[1]["article_number"] in ["2", "٢"]

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "initializing", "online"]
    assert "vector_store_loaded" in data
    assert "total_chunks" in data

def test_query_endpoint_empty():
    response = client.post("/query", json={"question": ""})
    assert response.status_code == 400

def test_query_endpoint_valid():
    response = client.post("/query", json={
        "question": "ما هي اللغة الرسمية للدولة؟",
        "top_k": 3
    })
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "sources" in data
    assert len(data["sources"]) > 0
    assert "processing_time_sec" in data
