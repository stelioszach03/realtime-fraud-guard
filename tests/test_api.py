from fastapi.testclient import TestClient

from services.inference_api.main import app


def test_health_and_config():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    cfg = client.get("/config").json()
    assert "threshold" in cfg and "topics_in" in cfg


def test_score_sources():
    client = TestClient(app)
    for source, payload in [
        ("payments", {"amount": 12.5, "merchant_name": "ACME", "user_id": "u1"}),
        ("sms", {"message_text": "Your OTP is 123456", "user_id": "u2"}),
        ("email", {"subject": "Hello", "body": "Hi", "sender_domain": "news.com", "user_id": "u3"}),
    ]:
        r = client.post("/score", json={"source": source, "payload": payload})
        assert r.status_code == 200
        body = r.json()
        assert 0.0 <= body["score"] <= 1.0
        assert "reasons" in body and isinstance(body["reasons"], list)
