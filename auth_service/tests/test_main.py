from fastapi.testclient import TestClient
from auth_service.main import app

client = TestClient(app)

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_register():
    resp = client.post("/users", json={"email": "test3@example.com", "password": "pass123"})
    assert resp.status_code == 201
    assert resp.json()["email"] == "test3@example.com"

def test_register_duplicate():
    client.post("/users", json={"email": "dup@example.com", "password": "pass"})
    resp = client.post("/users", json={"email": "dup@example.com", "password": "pass"})
    assert resp.status_code == 409

def test_login_success():
    client.post("/users", json={"email": "login@example.com", "password": "mypass"})
    resp = client.post("/token", data={"username": "login@example.com", "password": "mypass"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()

def test_login_wrong_password():
    client.post("/users", json={"email": "wrong@example.com", "password": "correct"})
    resp = client.post("/token", data={"username": "wrong@example.com", "password": "wrong"})
    assert resp.status_code == 401