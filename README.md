# 🔬 Laborsuche DACH

Interaktive Karte für **DEXA Body-Composition-Scans** und **Selbstzahler-Blutlabore** in Deutschland, Österreich und der Schweiz.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey)
![Leaflet](https://img.shields.io/badge/Leaflet-1.9-green)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## Demo

![Screenshot Karte](docs/screenshot.png)

---

## Inhalt

- [Schnellstart](#schnellstart)
- [Docker](#docker)
- [Projektstruktur](#projektstruktur)
- [Architektur & Entscheidungen](#architektur--entscheidungen)
- [Datenmodell](#datenmodell)
- [REST API](#rest-api)
- [Daten beschaffen (Scraper)](#daten-beschaffen-scraper)
- [Daten validieren](#daten-validieren)
- [Was ich bei mehr Zeit noch tun würde](#was-ich-bei-mehr-zeit-noch-tun-würde)

---

## Schnellstart

### Voraussetzungen

- Python 3.11+

```bash
# 1. Repository klonen
git clone https://github.com/dein-name/laborsuche-dach.git
cd laborsuche-dach

# 2. Virtuelle Umgebung
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt

# 4. App starten
python run.py
```

Jetzt unter **http://localhost:5000** aufrufen.

Die SQLite-Datenbank wird automatisch beim ersten Start erstellt und mit den Daten aus `app/data/providers.json` befüllt.

---

## Docker

```bash
# Einmalig bauen und starten
docker compose up --build

# Im Hintergrund
docker compose up -d

# Stoppen
docker compose down
```

App läuft dann auf **http://localhost:5000**.

Die SQLite-DB wird in einem persistenten Docker-Volume gespeichert (`db_data`).

---

## Projektstruktur

```
laborsuche-dach/
├── run.py                      # Einstiegspunkt
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── app/
│   ├── __init__.py             # App-Factory, DB-Initialisierung, Seeding
│   ├── api.py                  # REST API (Blueprint /api/v1)
│   ├── models.py               # SQLAlchemy Provider-Modell
│   ├── views.py                # Frontend-Route (/)
│   └── data/
│       ├── providers.json      # Kuratierter Datensatz (Seed-Daten)
│       └── provider.schema.json # JSON Schema für Validierung
│
├── templates/
│   └── index.html              # Hauptseite (Leaflet-Karte)
│
├── static/
│   ├── css/style.css
│   └── js/map.js               # Karten-Logik, Filter, Detail-Panel
│
└── scripts/
    ├── scraper.py              # Daten-Recherche (Google Places / Web)
    └── validate.py             # Datenqualitäts-Prüfung
```

---

## Architektur & Entscheidungen

### Backend: Flask + SQLite

**Warum Flask?**
Schlanker, gut dokumentierter Micro-Framework. Für ein Projekt dieser Größe (ein Datentyp, ~20 Endpunkte) ist kein schwergewichtiges Framework nötig. Flask erlaubt klare Trennung: Models → API → Views.

**Warum SQLite?**
- Keine externe Datenbank notwendig – Zero-Setup für Reviewer
- Für die Datenmenge (hunderte bis wenige tausend Einträge) völlig ausreichend
- Einfacher Wechsel auf PostgreSQL möglich: nur `SQLALCHEMY_DATABASE_URI` ändern

**Warum SQLAlchemy?**
ORM verhindert SQL-Injection by default und macht einen späteren DB-Wechsel einfach.

### Frontend: Vanilla JS + Leaflet

**Warum kein React/Vue?**
Die Karte ist das primäre Interaktionselement, kein komplexes State-Management notwendig. Vanilla JS hält die Abhängigkeiten minimal und das Projekt für jeden verständlich.

**Warum Leaflet?**
- Open Source, keine API-Key-Pflicht
- Leaflet.markercluster löst das Clustering elegant
- OpenStreetMap-Tiles sind kostenlos

### Daten: JSON → SQLite (Seeding)

Der Datensatz liegt als `providers.json` im Repo. Beim App-Start wird die SQLite-DB automatisch befüllt (Seeding), falls sie leer ist. Das ermöglicht:
- Versionskontrolle der Daten über Git
- Einfaches Hinzufügen neuer Einträge (JSON editieren, App neu starten)
- Späterer Wechsel zu einer echten Admin-Oberfläche oder einem ETL-Prozess

---

## Datenmodell

Das vollständige Schema liegt in [`app/data/provider.schema.json`](app/data/provider.schema.json).

```json
{
  "id":       "dexa-001",
  "name":     "Sportklinik Stuttgart – Sportmedizin",
  "category": "dexa",           // "dexa" | "blood_lab" | "both"
  "services": [
    "body_composition",         // DEXA: Körperfett, Muskelmasse, etc.
    "bone_density"              // DEXA: reine Knochendichtemessung (DXA/DEXA)
    // "blood_test_self_pay"    // Bluttest ohne Überweisung
  ],
  "address": {
    "street":  "Taubenheimstraße 8",
    "zip":     "70372",
    "city":    "Stuttgart",
    "country": "DE"             // ISO 3166-1: "DE" | "AT" | "CH"
  },
  "coordinates": { "lat": 48.8031, "lng": 9.2337 },
  "contact": {
    "phone":   "+49 711 5535-0",
    "website": "https://www.sportklinik.de",
    "email":   ""
  },
  "self_pay":      true,
  "prices": {
    "dexa_body_composition": "ca. 80–120 €",
    "bone_density":          "ca. 60 €",
    "blood_test":            null
  },
  "verified":      true,
  "last_verified": "2024-11-01",
  "notes":  "Ganzkörper-DEXA inkl. Body-Composition-Report.",
  "source": "Website + Telefonische Bestätigung"
}
```

### Wichtige Unterscheidung: body_composition vs. bone_density

> Das ist die kritische Qualitätseigenschaft des Datensatzes.

Viele Praxen bieten DEXA **nur zur Knochendichtemessung** an (GKV-Leistung bei Osteoporose-Indikation). Nur ein Teil bietet auch **Body Composition** an – die Messung von Körperfett, Muskelmasse und deren regionaler Verteilung, die für Coaching relevant ist.

Dieses Projekt unterscheidet beides explizit im `services`-Array:
- `"bone_density"` → Knochendichte
- `"body_composition"` → Körperzusammensetzung (Coaching-relevant)

Ein Anbieter kann beides listen.

---

## REST API

| Methode | Endpunkt | Beschreibung |
|---------|----------|--------------|
| `GET` | `/api/v1/providers` | Alle Anbieter (filterbar) |
| `GET` | `/api/v1/providers/:id` | Einzelner Anbieter |
| `POST` | `/api/v1/providers` | Neuen Anbieter anlegen |
| `PUT` | `/api/v1/providers/:id` | Anbieter aktualisieren |
| `DELETE` | `/api/v1/providers/:id` | Anbieter löschen |
| `GET` | `/api/v1/stats` | Aggregierte Statistiken |

### Filter-Parameter (`GET /api/v1/providers`)

| Parameter | Werte | Beispiel |
|-----------|-------|---------|
| `category` | `dexa` \| `blood_lab` \| `both` | `?category=dexa` |
| `country` | `DE` \| `AT` \| `CH` | `?country=DE` |
| `service` | `body_composition` \| `bone_density` \| `blood_test_self_pay` | `?service=body_composition` |
| `verified` | `true` \| `false` | `?verified=true` |
| `q` | Freitext | `?q=München` |

**Beispiele:**

```bash
# Alle verifizierten DEXA Body-Composition-Anbieter in Deutschland
curl "http://localhost:5000/api/v1/providers?category=dexa&service=body_composition&country=DE&verified=true"

# Suche nach Anbietern in München
curl "http://localhost:5000/api/v1/providers?q=München"

# Statistiken
curl "http://localhost:5000/api/v1/stats"
```

**Response-Format:**
```json
{
  "count": 3,
  "providers": [ { ...provider }, ... ]
}
```

---

## Daten beschaffen (Scraper)

Der Scraper in `scripts/scraper.py` unterstützt drei Modi:

### Modus 1: Google Places API (empfohlen, API-Key erforderlich)

```bash
python scripts/scraper.py \
  --mode places \
  --api-key YOUR_GOOGLE_PLACES_API_KEY \
  --query "DEXA Body Composition Scan" \
  --region München
```

Liefert strukturierte Daten mit Koordinaten, Telefon und Website direkt aus Google Maps.

### Modus 2: Web-Scraping ohne API-Key

```bash
# DEXA-Anbieter
python scripts/scraper.py --mode web --query "DEXA Body Composition" --region Hamburg

# Blutlabore
python scripts/scraper.py --mode web --query "Bluttest Selbstzahler Labor" --region Köln
```

Ergebnisse landen in `app/data/candidates.json` zur **manuellen Prüfung**.

### Modus 3: Fehlende Koordinaten via Nominatim (OSM) ergänzen

```bash
python scripts/scraper.py --mode geocode
# oder für eine andere Datei:
python scripts/scraper.py --mode geocode --file app/data/candidates.json
```

### Recherche-Workflow

```
Scraper (candidates.json)
        │
        ▼
  Manuelle Prüfung        ← Wichtigster Schritt!
  - Bieten sie wirklich Body Composition an?
  - Selbstzahler möglich?
  - Adresse korrekt?
        │
        ▼
  providers.json          ← Nur verifizierte Einträge
        │
        ▼
  validate.py             ← Automatische Qualitätsprüfung
        │
        ▼
  App-Start / Seeding
```

---

## Daten validieren

```bash
# Standard-Validierung
python scripts/validate.py

# Strenge Prüfung (warnt bei fehlendem Kontakt, nicht-verifizierten Einträgen)
python scripts/validate.py --strict

# Kandidaten-Datei prüfen
python scripts/validate.py --file app/data/candidates.json
```

Beispiel-Ausgabe:
```
Validiere 20 Einträge in app/data/providers.json …

── Statistik ────────────────────────────────────────────────
  Gesamt:           20
  DEXA:             10
  Blutlabor:         8
  Beides:            2
  Verifiziert:      20
  Fehlende Coords:   0

✅ Alle Einträge valide.
```

---

## Was ich bei mehr Zeit noch tun würde

### Daten
- **Mehr Einträge**: Systematisches Scraping aller Großstädte im DACH-Raum mit Google Places API, danach manuelle Verifikation per Telefon/E-Mail
- **Automatisierter Re-Verifikations-Job**: Monatlich alle Einträge automatisch prüfen (Website erreichbar? Telefonnummer gültig?) und `last_verified` + `verified` Flag aktualisieren
- **Österreich & Schweiz** stärker ausbauen (aktuell wenige Einträge)
- **Preisstruktur** granularer: z.B. Ganzkörper vs. Teilkörper-DEXA

### Feature
- **Admin-Panel**: Einfaches passwortgeschütztes UI zum Hinzufügen/Bearbeiten von Einträgen, ohne JSON manuell zu editieren
- **Nutzer-Beiträge**: Formular "Anbieter vorschlagen" mit E-Mail-Benachrichtigung zur manuellen Freigabe
- **"In meiner Nähe"**: Geolokalisierung des Nutzers via Browser-API, Sortierung nach Entfernung
- **Direktlink pro Anbieter**: `/provider/dexa-001` → teilbarer Link mit geöffnetem Detail-Panel
- **Export**: CSV/PDF-Export der Filterergebnisse für Kunden

### Tech
- **PostgreSQL** statt SQLite für Multi-User-Betrieb und Volltextsuche
- **Caching** der API-Responses (Redis oder einfaches Flask-Caching)
- **CI/CD**: GitHub Actions für automatisches `validate.py` bei jedem PR auf `providers.json`
- **Bounding-Box-Query**: API-Endpunkt der nur Anbieter im sichtbaren Kartenausschnitt zurückgibt (für große Datensätze)

---

## Lizenz

MIT
