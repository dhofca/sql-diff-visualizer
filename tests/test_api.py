from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


def test_diff_endpoint():
    files = {
        "old": ("v1.sql", (FIXTURES / "v1.sql").read_bytes(), "application/sql"),
        "new": ("v2.sql", (FIXTURES / "v2.sql").read_bytes(), "application/sql"),
    }
    response = client.post("/api/diff", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["files"] == {"old": "v1.sql", "new": "v2.sql"}
    assert body["tree"]["status"] == "modified"


def test_requires_both_files():
    response = client.post("/api/diff", files={"old": ("v1.sql", b"", "application/sql")})
    assert response.status_code == 422


def test_serves_frontend():
    response = client.get("/")
    assert response.status_code == 200
    assert "SQL Schema Diff" in response.text
