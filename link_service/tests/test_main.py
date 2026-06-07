import os

from fastapi.testclient import TestClient

os.environ["JWT_SECRET_KEY"] = "dev-secret"
from link_service.main import app
from shared.jwt_utils import create_access_token

# root_path im TestClient weglassen — root_path ist nur für Swagger/OpenAPI-Metadaten.
# Routen sind ohne /links-Prefix definiert, also direkt ansprechen.
client = TestClient(app)
token = create_access_token(user_id=1, role="user")
headers = {"Authorization": f"Bearer {token}"}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_save_link():
    resp = client.post(
        "/",
        json={"url": "https://fastapi.tiangolo.com", "title": "FastAPI", "tags": ["python"]},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["url"] == "https://fastapi.tiangolo.com"


def test_save_link_ohne_token():
    resp = client.post("/", json={"url": "https://example.com", "title": "Test"})
    assert resp.status_code == 422


def test_list_links():
    client.post("/", json={"url": "https://pytest.org", "title": "pytest"}, headers=headers)
    resp = client.get("/", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_link_nicht_gefunden():
    resp = client.get("/99999", headers=headers)
    assert resp.status_code == 404


def test_patch_link():
    create = client.post(
        "/",
        json={"url": "https://docs.python.org", "title": "Alt"},
        headers=headers,
    )
    link_id = create.json()["id"]
    resp = client.patch(f"/{link_id}", json={"title": "Neu"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Neu"


def test_delete_link():
    create = client.post(
        "/",
        json={"url": "https://loeschen.example.com", "title": "Löschen"},
        headers=headers,
    )
    link_id = create.json()["id"]
    resp = client.delete(f"/{link_id}", headers=headers)
    assert resp.status_code == 204
    assert client.get(f"/{link_id}", headers=headers).status_code == 404


def test_link_history():
    create = client.post(
        "/",
        json={"url": "https://history.example.com", "title": "History"},
        headers=headers,
    )
    link_id = create.json()["id"]
    resp = client.get(f"/{link_id}/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["type"] == "LinkGespeichert"