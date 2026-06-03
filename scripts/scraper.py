#!/usr/bin/env python3
"""
scripts/scraper.py
──────────────────
Recherche-Skript für DEXA Body-Composition-Scanner und Selbstzahler-Blutlabore
im DACH-Raum.

Strategie:
  1. Google Maps / Places API (bevorzugt, wenn API-Key vorhanden)
  2. Statische Suchanfragen via requests + BeautifulSoup (Fallback)
  3. Ergebnisse werden als candidates.json gespeichert – manuelle Verifikation
     notwendig bevor ein Eintrag in providers.json aufgenommen wird.

Aufruf:
  python scripts/scraper.py --mode places --api-key <KEY> --query "DEXA Scan" --region München
  python scripts/scraper.py --mode web   --query "DEXA Body Composition" --region Hamburg
"""

import argparse
import json
import time
import uuid
import re
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Bitte installieren: pip install requests beautifulsoup4")

OUT_DIR  = Path(__file__).parent.parent / "app" / "data"
OUT_FILE = OUT_DIR / "candidates.json"

# ── Helpers ───────────────────────────────────────────────────────────────
def make_skeleton(name: str, city: str, category: str) -> dict:
    """Return an empty provider template to fill in."""
    return {
        "id": f"candidate-{uuid.uuid4().hex[:8]}",
        "name": name,
        "category": category,
        "services": [],
        "address": {"street": "", "zip": "", "city": city, "country": "DE"},
        "coordinates": {"lat": None, "lng": None},
        "contact": {"phone": "", "website": "", "email": ""},
        "self_pay": True,
        "prices": {
            "dexa_body_composition": None,
            "bone_density": None,
            "blood_test": None,
        },
        "verified": False,
        "last_verified": None,
        "notes": "TODO: manuell verifizieren",
        "source": "Web-Scraping / Kandidat",
    }


def load_existing() -> list[dict]:
    if OUT_FILE.exists():
        with open(OUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_candidates(candidates: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing   = load_existing()
    known_names = {e["name"].lower() for e in existing}
    new_entries = [c for c in candidates if c["name"].lower() not in known_names]

    merged = existing + new_entries
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[scraper] {len(new_entries)} neue Kandidaten hinzugefügt → {OUT_FILE}")
    print(f"[scraper] Gesamt: {len(merged)} Kandidaten")


# ── Mode 1: Google Places API ─────────────────────────────────────────────
def scrape_google_places(api_key: str, query: str, region: str) -> list[dict]:
    """
    Uses the Google Places Text Search API.
    Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
    """
    print(f"[google-places] Suche nach: '{query}' in {region}")
    url      = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    results  = []
    params   = {
        "query":  f"{query} {region}",
        "key":    api_key,
        "language": "de",
        "region": "de",
    }

    while True:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            print(f"[google-places] API-Status: {data.get('status')}")
            break

        for place in data.get("results", []):
            candidate = make_skeleton(
                name=place.get("name", ""),
                city=region,
                category=_guess_category(query),
            )
            # Enrich with Places data
            loc = place.get("geometry", {}).get("location", {})
            candidate["coordinates"]["lat"] = loc.get("lat")
            candidate["coordinates"]["lng"] = loc.get("lng")
            candidate["contact"]["website"] = place.get("website", "")
            candidate["contact"]["phone"]   = place.get("formatted_phone_number", "")
            addr_comps = place.get("address_components", [])
            candidate["address"]["street"]  = _extract_street(place.get("formatted_address", ""))
            candidate["address"]["zip"]     = _extract_from_components(addr_comps, "postal_code")
            candidate["address"]["city"]    = _extract_from_components(addr_comps, "locality") or region
            results.append(candidate)

        # Pagination
        next_token = data.get("next_page_token")
        if not next_token:
            break
        time.sleep(2)   # Google requires a short delay before using next_page_token
        params = {"pagetoken": next_token, "key": api_key}

    print(f"[google-places] {len(results)} Ergebnisse gefunden.")
    return results


def _extract_street(formatted: str) -> str:
    parts = formatted.split(",")
    return parts[0].strip() if parts else ""


def _extract_from_components(components: list, comp_type: str) -> str:
    for c in components:
        if comp_type in c.get("types", []):
            return c.get("long_name", "")
    return ""


# ── Mode 2: Simple Web Search (no API key) ────────────────────────────────
def scrape_web(query: str, region: str) -> list[dict]:
    """
    Führt eine einfache DuckDuckGo-HTML-Suche durch und extrahiert Treffer.
    Kein API-Key notwendig. Ergebnisse sind weniger präzise und müssen manuell
    verifiziert werden.
    """
    search_query = f"{query} {region} Selbstzahler"
    print(f"[web-scraper] Suche: '{search_query}'")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; LaborsuacheDACH/1.0; "
            "research-bot; kontakt@example.com)"
        )
    }

    # DuckDuckGo HTML endpoint
    resp = requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": search_query},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()

    soup    = BeautifulSoup(resp.text, "html.parser")
    results = []

    for result in soup.select(".result"):
        title_el = result.select_one(".result__title")
        url_el   = result.select_one(".result__url")
        snip_el  = result.select_one(".result__snippet")

        if not title_el:
            continue

        name    = title_el.get_text(strip=True)
        url     = url_el.get_text(strip=True) if url_el else ""
        snippet = snip_el.get_text(strip=True) if snip_el else ""

        # Only keep results that look relevant (basic keyword filter)
        combined = (name + snippet).lower()
        if not any(kw in combined for kw in ["dexa", "labor", "blut", "körper", "scan", "radiolog"]):
            continue

        candidate = make_skeleton(
            name=_clean_title(name),
            city=region,
            category=_guess_category(query),
        )
        candidate["contact"]["website"] = f"https://{url}" if url and not url.startswith("http") else url
        candidate["notes"] = f"Snippet: {snippet[:200]}"
        results.append(candidate)

    print(f"[web-scraper] {len(results)} Kandidaten extrahiert (ungeprüft).")
    return results


def _clean_title(raw: str) -> str:
    # Remove common suffixes like "– Praxis Dr. …"
    raw = re.sub(r"\s*[-–|]\s*.{0,60}$", "", raw).strip()
    return raw or raw


def _guess_category(query: str) -> str:
    ql = query.lower()
    if "dexa" in ql or "körper" in ql or "body" in ql or "scan" in ql:
        return "dexa"
    if "blut" in ql or "labor" in ql:
        return "blood_lab"
    return "dexa"


# ── Mode 3: Geocode existing providers without coordinates ─────────────────
def geocode_providers(providers_file: Optional[str] = None) -> None:
    """
    Adds lat/lng to providers that have an address but no coordinates.
    Uses the free Nominatim API (OpenStreetMap).
    Rate-limit: 1 request/second.
    """
    path = Path(providers_file) if providers_file else OUT_DIR / "providers.json"
    if not path.exists():
        print(f"[geocode] Datei nicht gefunden: {path}")
        return

    with open(path, encoding="utf-8") as f:
        providers = json.load(f)

    updated  = 0
    base_url = "https://nominatim.openstreetmap.org/search"
    headers  = {"User-Agent": "LaborsuacheDACH/1.0"}

    for p in providers:
        if p["coordinates"].get("lat") and p["coordinates"].get("lng"):
            continue  # already has coords

        addr  = p["address"]
        query = f'{addr.get("street","")}, {addr.get("zip","")} {addr.get("city","")}, {addr.get("country","DE")}'
        try:
            resp = requests.get(
                base_url,
                params={"q": query, "format": "json", "limit": 1},
                headers=headers,
                timeout=8,
            )
            resp.raise_for_status()
            results = resp.json()
            if results:
                p["coordinates"]["lat"] = float(results[0]["lat"])
                p["coordinates"]["lng"] = float(results[0]["lon"])
                updated += 1
                print(f"[geocode] ✓ {p['name']} → {p['coordinates']}")
            else:
                print(f"[geocode] ✗ Keine Koordinaten für: {query}")
        except Exception as e:
            print(f"[geocode] Fehler bei {p['name']}: {e}")

        time.sleep(1.1)  # Respect Nominatim usage policy

    with open(path, "w", encoding="utf-8") as f:
        json.dump(providers, f, ensure_ascii=False, indent=2)
    print(f"[geocode] {updated} Einträge mit Koordinaten versehen → {path}")


# ── CLI ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Laborsuche DACH – Scraper & Geocoder"
    )
    parser.add_argument(
        "--mode",
        choices=["places", "web", "geocode"],
        default="web",
        help="places = Google Places API | web = HTML-Scraping | geocode = Koordinaten ergänzen",
    )
    parser.add_argument("--api-key",   default="", help="Google Places API-Key (nur für --mode places)")
    parser.add_argument("--query",     default="DEXA Body Composition Scan", help="Suchbegriff")
    parser.add_argument("--region",    default="Deutschland", help="Region/Stadt")
    parser.add_argument("--file",      default=None, help="Pfad zur providers.json (für --mode geocode)")
    args = parser.parse_args()

    if args.mode == "places":
        if not args.api_key:
            sys.exit("--api-key benötigt für --mode places")
        candidates = scrape_google_places(args.api_key, args.query, args.region)
        save_candidates(candidates)

    elif args.mode == "web":
        candidates = scrape_web(args.query, args.region)
        save_candidates(candidates)
        print("\n⚠️  Kandidaten müssen manuell geprüft und in providers.json übertragen werden.")

    elif args.mode == "geocode":
        geocode_providers(args.file)


if __name__ == "__main__":
    main()
