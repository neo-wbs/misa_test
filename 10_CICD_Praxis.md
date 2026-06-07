# 10 · CI/CD — Praxis: GitHub Actions & Blue-Green Deploy

## Was wir in diesem Kapitel bauen
- pytest-Tests für auth-service und link-service
- Paketstruktur aufbauen
- GitHub Actions Pipeline: Test → Lint → Docker Build → Push → Deploy
- Blue-Green Deployment-Skript
- GitHub Secrets für sichere Credentials

---

## Schritt 1 - Tests schreiben

```text
# tests Verzeichnis: Mark as Test Root
# auth_service/requirements-dev.txt
# link_service/requirements-dev.txt
pytest
pytest-cov
httpx2
ruff
```

```python
# projekt/auth_service/tests/test_main.py
from fastapi.testclient import TestClient
from auth_service.main import app

client = TestClient(app)

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_register():
    resp = client.post("/users", json={"email": "test@example.com", "password": "pass123"})
    assert resp.status_code == 201
    assert resp.json()["email"] == "test@example.com"

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
```

```python
# projekt/link_service/tests/test_main.py
import os

from fastapi.testclient import TestClient

os.environ["JWT_SECRET_KEY"] = "dev-secret"
from link_service.main import app
from shared.jwt_utils import create_access_token

client = TestClient(app)  # ← root_path entfernen
token = create_access_token(user_id=1, role="user")
headers = {"Authorization": f"Bearer {token}"}

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200

def test_save_link():
    resp = client.post("/links", json={"url": "https://fastapi.tiangolo.com", "title": "FastAPI", "tags": ["python"]}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["url"] == "https://fastapi.tiangolo.com"

def test_save_link_ohne_token():
    resp = client.post("/links", json={"url": "https://example.com", "title": "Test"})
    assert resp.status_code == 422

def test_list_links():
    client.post("/links", json={"url": "https://pytest.org", "title": "pytest"}, headers=headers)
    resp = client.get("/links", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_get_link_nicht_gefunden():
    resp = client.get("/links/99999", headers=headers)
    assert resp.status_code == 404

def test_patch_link():
    create = client.post("/links", json={"url": "https://docs.python.org", "title": "Alt"}, headers=headers)
    link_id = create.json()["id"]
    resp = client.patch(f"/links/{link_id}", json={"title": "Neu"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Neu"

def test_delete_link():
    create = client.post("/links", json={"url": "https://loeschen.example.com", "title": "Löschen"}, headers=headers)
    link_id = create.json()["id"]
    resp = client.delete(f"/links/{link_id}", headers=headers)
    assert resp.status_code == 204
    assert client.get(f"/links/{link_id}", headers=headers).status_code == 404

def test_link_history():
    create = client.post("/links", json={"url": "https://history.example.com", "title": "History"}, headers=headers)
    link_id = create.json()["id"]
    resp = client.get(f"/links/{link_id}/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["type"] == "LinkGespeichert"
```

## Schritt 2: Einige Änderungen, damit Tests keine Fehler werfen
Zu Package Struktur: `...\trainer_my_courses\kurs_Python\vorbereitung\komplett_kurs\grundlagen`

```bash
# Refactoring Paketname auth-service in auth_service, link-service in link_service
# sonst meckert Test Paketnamen an (Dockerfile nicht vergessen)

# auth_service, link_service, shared werden als Package importiert: __init__.py einfügen (leer)

# Doppelte jwt_utils.py nach shared verschieben
# Evtl. import anpassen: from shared.jwt_utils import verify_token

# Dockerfiles anpassen:
# auth_service
COPY auth_service/requirements.txt .
COPY auth_service/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY shared ./shared
COPY . .
CMD ["uvicorn", "auth_service.main:app", "--host", "0.0.0.0", "--port", "8001"]

# link_service
COPY link_service/requirements.txt .
COPY link_service/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY shared ./shared
COPY . .
CMD ["uvicorn", "link_service.main:app", "--host", "0.0.0.0", "--port", "8002"]

# In link_service/main.py:
client = TestClient(app)  # ← root_path entfernen
# dafür dann bei Aufruf nicht mehr
# http://localhost/links/links, sondern: http://localhost/links
curl -X POST http://localhost/links \
   -H "Authorization: Bearer $TOKEN" \
   -H "Content-Type: application/json" \
   -d '{"url":"https://owasp.org","title":"OWASP","tags":["security"]}'
   
# Damit Tests und App dieselben *.db Dateien nutzen > in docker-compose.yml > bei volumes:
# auth-service:
- ./auth_service/auth.db:/app/auth_service/auth.db

# link-service:
- ./link_service/links.db:/app/link_service/links.db
```

Tests lokal ausführen:
```bash
cd auth_service
pip install -r requirements-dev.txt
python -m pytest  auth_service/tests/ -v --cov=. --cov-report=term-missing
# Coverage-Report zeigt welche Zeilen nicht getestet sind
```

---

## Schritt 3 — GitHub Actions Pipeline: auth-service

Gleiche Datei für link_service — einfach auth_service durch link_service 
ersetzen.

```yaml
# .github/workflows/auth_service.yml
name: auth_service CI/CD

on:
  push:
    paths:
      - "auth_service/**"
      - ".github/workflows/auth_service.yml"
  pull_request:
    paths:
      - "auth_service/**"

jobs:

  test:
    name: Tests & Lint
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: auth_service

    steps:
      - uses: actions/checkout@v4

      - name: Python setup
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint (ruff)
        run: ruff check .

      - name: Tests mit Coverage
        run: pytest tests/ --cov=. --cov-fail-under=80
        env:
          JWT_SECRET_KEY: test-secret-key-for-ci

  build-and-push:
    name: Docker Build & Push
    needs: test                    # nur wenn Tests bestanden!
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'   # nur auf main-Branch

    steps:
      - uses: actions/checkout@v4

      - name: Login zu Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Docker Image bauen & pushen
        uses: docker/build-push-action@v5
        with:
          context: ./auth_service
          push: true
          tags: |
            ${{ secrets.DOCKER_USERNAME }}/auth-service:latest
            ${{ secrets.DOCKER_USERNAME }}/auth-service:${{ github.sha }}
```

---

## Schritt 3 — GitHub Secrets einrichten

GITHUB_TOKEN ist automatisch verfügbar — du brauchst kein manuelles Secret für 
GHCR (GitHub Container Registry) anlegen. Einfach pushen und die Pipeline läuft.
Es wird von GitHub automatisch für jeden Pipeline-Run generiert und ist nur 
innerhalb der Pipeline als ${{ secrets.GITHUB_TOKEN }} verfügbar. Aber 
Personal Access Token muss generiert werden:
- GitHub → rechts oben dein Profilbild → Settings
- ganz unten links: Developer settings
- Personal access tokens → Tokens (classic)
- Generate new token (classic)

---

## Schritt 4 — "Deploy" auf deinem Windows-Rechner

Das ist dein "Blue-Green Deploy" für die Lernumgebung - in Produktion würde 
ein Server das automatisch machen, aber das Prinzip ist identisch.
Nachdem die Pipeline durch ist, das neue Image lokal pullen:

```bash
# Einmalig: bei GHCR einloggen, Docker merkt sich die Credentials danach lokal.
docker login ghcr.io -u DEIN_GITHUB_USERNAME -p Personal_Access_Token

# Neues Image pullen und starten
docker compose pull

#Ausgabe
 ✔ auth-service                  Skipped No image to be pulled                                                                                                                                                              0.0s
 ✔ link-service                  Skipped No image to be pulled                                                                                                                                                              0.0s
 ✔ Image grafana/grafana:10.4.0  Pulled                                                                                                                                                                                     1.4s
 ✔ Image traefik:v3.6.2          Pulled                                                                                                                                                                                     1.4s
 ✔ Image prom/prometheus:v2.51.0 Pulled 
# auth-service und link-service → Skipped weil die lokal gebaut werden 
# (build: ./auth-service) — da gibt es nichts zu pullen
# grafana, traefik, prometheus → wurden von Docker Hub gepullt

# Um für deine eigenen Services das Image von GHCR zu nutzen, müsstest du in 
# der docker-compose.yml das build: durch image: ersetzen:
# 1. Erst lokal bauen:
auth-service:
  build: ./auth-service

# 2. Nach erfolgreichem Pipeline-Run (von GHCR pullen). Aber der GHCR-Pull 
# wäre nur relevant wenn du auf einem echten Server deployst.
auth-service:
  image: ghcr.io/DEIN_GITHUB_USERNAME/auth-service:latest

docker compose up -d
```

---

## Schritt 5 — Pipeline anstoßen & beobachten

Pipeline lokal testen ohne Push:
```bash
cd projekt
python -m pytest auth_service/tests/ -v
python -m pytest link_service/tests/ -v
python -m ruff check .

docker compose up --build
curl http://localhost:8001/health
```

Dann pushen:
```
git add .
git commit -m "feat: add CI/CD pipeline"
git push origin main

GitHub → Actions Tab → auth-service CI/CD
├── Tests & Lint          (ca. 45s)
└── Docker Build & Push   (ca. 90s)
```

---

## Projektstruktur nach diesem Kapitel

```
projekt/
├── .github/
│   └── workflows/
│       ├── auth-service.yml    ← neu
│       └── link-service.yml    ← neu
├── auth-service/
    ├── __init__.py             ← neu
    ├── requirements-dev.txt    ← neu
    └── tests/
        └── test_main.py        ← neu
├── link-service/
    ├── __init__.py             ← neu
    ├── requirements-dev.txt    ← neu
    └── tests/
        └── test_main.py        ← neu
└── shared/
    ├── jwt_utils.py            ← verschoben
    └── __init__.py             ← neu
```
---
