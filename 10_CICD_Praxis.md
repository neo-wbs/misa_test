# 10 · CI/CD — Praxis: GitHub Actions & Blue-Green Deploy

## Was wir in diesem Kapitel bauen
- pytest-Tests für auth-service und link-service
- Paketstruktur aufbauen
- GitHub Actions Pipeline: Test → Lint → Docker Build → Push → Deploy
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
# links/ aus Routen entfernen
# statt @app.post("links/",...) nun @app.post("/",...)
# Andere Aufrufe dann:
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
python -m pytest  link_service/tests/ -v --cov=. --cov-report=term-missing
# Coverage-Report zeigt welche Zeilen nicht getestet sind
```

---

## Schritt 3 — GitHub Actions Pipeline: auth_service, link_service

```yaml
# .github/workflows/auth_service.yml
name: auth_service CI/CD

on:
  push:
    paths:
      - "auth_service/**"
      - "shared/**"
      - ".github/workflows/auth_service.yml"
  pull_request:
    paths:
      - "auth_service/**"
      - "shared/**"

jobs:

  test:
    name: Tests & Lint
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Python setup
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r auth_service/requirements.txt
          pip install -r auth_service/requirements-dev.txt

      - name: Lint (ruff)
        run: ruff check auth_service/

      - name: Tests mit Coverage
        run: pytest auth_service/tests/ --cov=auth_service --cov-fail-under=75
        env:
          JWT_SECRET_KEY: test-secret-key-for-ci
          PYTHONPATH: .

  build-and-push:
    name: Docker Build & Push
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    permissions:
      packages: write   # GHCR braucht explizite Schreibrechte

    steps:
      - uses: actions/checkout@v4

      - name: Login zu GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker Image bauen & pushen
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./auth_service/Dockerfile
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/auth-service:latest
            ghcr.io/${{ github.repository_owner }}/auth-service:${{ github.sha }}
```

```yaml
# .github/workflows/link_service.yml
name: link_service CI/CD

on:
  push:
    paths:
      - "link_service/**"
      - "shared/**"
      - ".github/workflows/link_service.yml"
  pull_request:
    paths:
      - "link_service/**"
      - "shared/**"

jobs:

  test:
    name: Tests & Lint
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Python setup
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r link_service/requirements.txt
          pip install -r link_service/requirements-dev.txt

      - name: Lint (ruff)
        run: ruff check link_service/

      - name: Tests mit Coverage
        run: pytest link_service/tests/ --cov=link_service --cov-fail-under=78
        env:
          JWT_SECRET_KEY: test-secret-key-for-ci
          PYTHONPATH: .

  build-and-push:
    name: Docker Build & Push
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    permissions:
      packages: write   # GHCR braucht explizite Schreibrechte

    steps:
      - uses: actions/checkout@v4

      - name: Login zu GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker Image bauen & pushen
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./link_service/Dockerfile
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/link_service:latest
            ghcr.io/${{ github.repository_owner }}/link_service:${{ github.sha }}
```

Für Docker Hub anstatt GHCR:
```yaml
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

## Schritt 4 — "Deploy" auf Windows-Rechner

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
curl http://localhost/auth/health
curl http://localhost/links/health
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

## Nutzung der Images aus GitHub Container Registry (GHCR)

Die Images liegen dauerhaft in der GitHub Container Registry (GHCR) — nicht temporär. 
Sichtbar im GitHub-UI: Repo → rechte Seite → "Packages". Oder unter:
```
ghcr.io/DEIN_USERNAME/auth-service:latest
ghcr.io/DEIN_USERNAME/link-service:latest
```
---

### Was du damit machen kannst:
1. Lokal pullen & starten — statt lokal zu bauen:
```
ghcr.io/DEIN_USERNAME/auth-service:latest
ghcr.io/DEIN_USERNAME/link-service:latest
```
2. `docker-compose.yml` umstellen — statt build: einfach das fertige Image nehmen. 
Dann braucht der Server zum Deployen keinen Source-Code mehr, nur noch die `docker-compose.yml`.
```yaml
auth-service:
  image: ghcr.io/DEIN_USERNAME/auth-service:latest
  # build: ← weg
```
3. Auf einem Server deployen — das ist der eigentliche Nutzen. CI baut das Image, 
Server zieht es nur noch — kein Python, kein pip, kein Build auf dem Server. Auf einem 
VPS (Hetzner, DigitalOcean etc.) reicht dann:
```
docker compose pull
docker compose up -d
```
4. Rollback — du hast jedes Image auch mit dem Git-SHA getaggt. Kaputtes Deployment? 
Einfach auf einen alten SHA zurück.
```
docker pull ghcr.io/DEIN_USERNAME/auth-service:abc1234
```

## Blue-Green Deployment (Nicht praktisch, da kein Server)
Blue-Green bedeutet: Du hast immer zwei Umgebungen - eine live (Green), eine idle (Blue). 
Neues Image geht auf Blue, läuft, wird getestet, dann switcht der Load Balancer um. 
Keine Downtime, sofortiger Rollback. Geht hier nicht ohne Server.

Falls Server vorhanden:
```yaml
# auth_service.yml > neuer Job
deploy:
   name: Deploy zu Blue
   needs: build-and-push
   runs-on: ubuntu-latest
   if: github.ref == 'refs/heads/main'

   steps:
     - name: SSH auf Server — neues Image auf Blue starten
       run: |
         ssh user@SERVER "docker compose pull && docker compose up -d auth-service-blue"
       env:
         SSH_KEY: ${{ secrets.SSH_PRIVATE_KEY }}   # ← Secret in GitHub hinterlegen

# Traefik switcht automatisch sobald der Healthcheck auf Blue grün ist.
# Rollback: einfach auth-service-green wieder aktivieren (Label umsetzen).
```

```yaml
# link_service.yml > neuer Job
deploy:
   name: Deploy zu Blue
   needs: build-and-push
   runs-on: ubuntu-latest
   if: github.ref == 'refs/heads/main'
  
   steps:
     - name: SSH auf Server — neues Image auf Blue starten
       run: |
         ssh user@SERVER "docker compose pull && docker compose up -d link-service-blue"
       env:
         SSH_KEY: ${{ secrets.SSH_PRIVATE_KEY }}   # ← Secret in GitHub hinterlegen
  
# Traefik switcht automatisch sobald der Healthcheck auf Blue grün ist.
# Rollback: einfach link-service-green wieder aktivieren (Label umsetzen).
```

```yaml
# docker-compose.yml
# Statt build: dann image: aus GHCR verwenden:
auth-service-blue:
   image: ghcr.io/DEIN_USERNAME/auth-service:latest
   labels:
     - "traefik.enable=true"
     - "traefik.http.routers.auth-router.rule=PathPrefix(`/auth`)"
     - "traefik.http.services.auth-svc.loadbalancer.server.port=8001"

auth-service-green:
   image: ghcr.io/DEIN_USERNAME/auth-service:latest
   labels:
     - "traefik.enable=false"   # idle — kein Traffic bis zum Switch
       
link-service-blue:
   image: ghcr.io/DEIN_USERNAME/link_service:latest
   labels:
     - "traefik.enable=true"
     - "traefik.http.routers.link-router.rule=PathPrefix(`/links`)"
     - "traefik.http.services.link-svc.loadbalancer.server.port=8002"

link-service-green:
  image: ghcr.io/DEIN_USERNAME/link_service:latest
  labels:
     - "traefik.enable=false"   # idle — kein Traffic bis zum Switch

# Traefik switcht per Label-Änderung + compose up, kein Downtime.
# Rollback: green wieder auf enable=true, blue auf false.
```

Neue Datei `switch.yml`: Manueller Workflow (workflow_dispatch) der Blue ↔ Green umschaltet -
Traefik-Label ändern + compose neu starten.
```yaml
# .github/workflows/switch.yml
name: Blue-Green Switch

# Manueller Workflow - wird nicht automatisch getriggert.
# Aufruf: GitHub → Actions → "Blue-Green Switch" → "Run workflow"
# Dann auswählen welche Farbe live gehen soll.
on:
  workflow_dispatch:
    inputs:
      live:
        description: "Welche Farbe soll live gehen?"
        required: true
        default: "blue"
        type: choice
        options:
          - blue
          - green

jobs:
  switch:
    name: Traefik Switch
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: SSH-Key einrichten
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/id_rsa
          chmod 600 ~/.ssh/id_rsa
          # Server-Fingerprint vorab eintragen — verhindert interactive prompt
          ssh-keyscan -H ${{ secrets.SERVER_HOST }} >> ~/.ssh/known_hosts

      - name: Switch ausführen
        run: |
          # deploy.sh auf dem Server aufrufen mit der gewählten Farbe.
          # Das Script übernimmt: neue Farbe starten, Healthcheck abwarten,
          # Traefik-Label switchen, alte Farbe stoppen.
          ssh user@${{ secrets.SERVER_HOST }} "bash /app/scripts/deploy.sh ${{ github.event.inputs.live }}"
        # Benötigte GitHub Secrets (unter Settings → Secrets → Actions):
        #   SSH_PRIVATE_KEY  — privater SSH-Key für den Server
        #   SERVER_HOST      — IP oder Domain des Servers
```

Neue Datei `deploy.sh` (auf dem Server), ist Script, das:
- Neue Farbe startet
- Healthcheck abwartet (/health endpoint — bereits vorhanden)
- Traefik-Label switcht
- Alte Farbe stoppt
```shell
# projekt/scripts/deploy.sh 
#!/bin/bash
# deploy.sh — Blue-Green Switch Script (läuft auf dem Server)
#
# Aufruf: bash deploy.sh blue   oder   bash deploy.sh green
# Wird von switch.yml per SSH aufgerufen.
#
# Voraussetzung auf dem Server:
#   - Docker + Docker Compose installiert
#   - docker-compose.yml liegt unter /app/
#   - GHCR-Login einmalig: docker login ghcr.io

set -e   # bei Fehler sofort abbrechen

LIVE=$1   # "blue" oder "green" — von switch.yml übergeben

# Gegenfarbe bestimmen
if [ "$LIVE" = "blue" ]; then
    IDLE="green"
else
    IDLE="blue"
fi

echo "→ Neue Live-Farbe: $LIVE | Idle: $IDLE"

cd /app

# 1. Neues Image aus GHCR pullen
echo "→ Image pullen..."
docker compose pull auth-service-$LIVE link-service-$LIVE

# 2. Neue Farbe starten (läuft parallel zur alten — kein Downtime)
echo "→ $LIVE starten..."
docker compose up -d auth-service-$LIVE link-service-$LIVE

# 3. Healthcheck abwarten — erst switchen wenn die neue Farbe wirklich bereit ist
echo "→ Warte auf Healthcheck..."
for i in $(seq 1 20); do
    # /health Endpoint der neuen Instanz direkt prüfen (nicht über Traefik)
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' app-auth-service-$LIVE-1 2>/dev/null || echo "starting")
    if [ "$STATUS" = "healthy" ]; then
        echo "→ $LIVE ist healthy!"
        break
    fi
    echo "   Versuch $i/20 — Status: $STATUS"
    sleep 3
done

if [ "$STATUS" != "healthy" ]; then
    echo "✗ Healthcheck fehlgeschlagen — Switch abgebrochen, $IDLE bleibt live."
    exit 1
fi

# 4. Traefik-Label switchen:
#    Neue Farbe bekommt enable=true → Traefik leitet Traffic dorthin
#    Alte Farbe bekommt enable=false → idle, kein Traffic mehr
echo "→ Traefik Switch: $LIVE wird live, $IDLE wird idle..."
docker compose up -d \
    --no-deps \
    -e TRAEFIK_ENABLE_$LIVE=true \
    -e TRAEFIK_ENABLE_$IDLE=false \
    auth-service-$LIVE link-service-$LIVE

# Kurz warten damit Traefik die Änderung übernimmt
sleep 2

# 5. Alte Farbe stoppen (optional — kann auch idle laufen bleiben für Rollback)
echo "→ $IDLE stoppen..."
docker compose stop auth-service-$IDLE link-service-$IDLE

echo "Switch abgeschlossen. Live: $LIVE"
echo "Rollback: bash deploy.sh $IDLE"
```

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
