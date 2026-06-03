#!/usr/bin/env python3
"""
scripts/validate.py
────────────────────
Validiert providers.json gegen das Datenschema und prüft auf:
  - Pflichtfelder
  - Doppelte IDs / Duplikate nach Name+Stadt
  - Ungültige Kategorien / Services
  - Fehlende Koordinaten
  - DEXA-spezifisch: body_composition vs. bone_density Unterscheidung

Aufruf:
  python scripts/validate.py
  python scripts/validate.py --file app/data/candidates.json --strict
"""

import argparse
import json
import sys
from pathlib import Path
from collections import Counter

# ── Schema ────────────────────────────────────────────────────────────────
VALID_CATEGORIES = {"dexa", "blood_lab", "both"}
VALID_SERVICES   = {"body_composition", "bone_density", "blood_test_self_pay"}
VALID_COUNTRIES  = {"DE", "AT", "CH"}

REQUIRED_FIELDS = ["id", "name", "category", "services", "address", "coordinates"]
REQUIRED_ADDRESS = ["street", "zip", "city", "country"]
REQUIRED_COORDS  = ["lat", "lng"]


# ── Validation ────────────────────────────────────────────────────────────
def validate_provider(p: dict, idx: int, strict: bool) -> list[str]:
    errors = []

    def err(msg):
        errors.append(f"  [#{idx} id={p.get('id','?')}] {msg}")

    # Pflichtfelder
    for field in REQUIRED_FIELDS:
        if field not in p or p[field] is None:
            err(f"Pflichtfeld fehlt: '{field}'")

    # Kategorie
    cat = p.get("category")
    if cat and cat not in VALID_CATEGORIES:
        err(f"Ungültige Kategorie: '{cat}'. Erlaubt: {VALID_CATEGORIES}")

    # Services
    services = p.get("services", [])
    if not isinstance(services, list):
        err("'services' muss eine Liste sein")
    else:
        for s in services:
            if s not in VALID_SERVICES:
                err(f"Unbekannter Service: '{s}'")

        # DEXA-spezifische Prüfung: body_composition vs. bone_density
        if cat in ("dexa", "both"):
            if "body_composition" not in services and "bone_density" not in services:
                err("DEXA-Anbieter hat weder 'body_composition' noch 'bone_density' in services")
            if "body_composition" not in services and strict:
                err("[STRICT] DEXA-Anbieter bietet kein 'body_composition' an – nur Knochendichte?")

        if cat in ("blood_lab", "both"):
            if "blood_test_self_pay" not in services:
                err("Blutlabor hat 'blood_test_self_pay' nicht in services")

    # Adresse
    addr = p.get("address", {})
    for field in REQUIRED_ADDRESS:
        if not addr.get(field):
            err(f"address.{field} fehlt oder leer")
    country = addr.get("country", "")
    if country and country not in VALID_COUNTRIES:
        err(f"Ungültiges Land: '{country}'. Erlaubt: {VALID_COUNTRIES}")

    # Koordinaten
    coords = p.get("coordinates", {})
    lat, lng = coords.get("lat"), coords.get("lng")
    if lat is None or lng is None:
        err("Koordinaten (lat/lng) fehlen")
    else:
        # Rough DACH bounding box
        if not (45.8 <= lat <= 55.1):
            err(f"lat={lat} außerhalb des DACH-Bereichs (45.8–55.1)")
        if not (5.9 <= lng <= 17.2):
            err(f"lng={lng} außerhalb des DACH-Bereichs (5.9–17.2)")

    # Kontakt
    contact = p.get("contact", {})
    if strict and not contact.get("website") and not contact.get("phone"):
        err("[STRICT] Kein Kontakt (weder Website noch Telefon)")

    # Verifikation
    if strict and not p.get("verified"):
        err("[STRICT] Eintrag ist nicht verifiziert")

    return errors


def check_duplicates(providers: list[dict]) -> list[str]:
    issues = []

    # Doppelte IDs
    ids = [p.get("id") for p in providers]
    for id_, count in Counter(ids).items():
        if count > 1:
            issues.append(f"  Doppelte ID: '{id_}' ({count}x)")

    # Duplikate nach Name + Stadt (case-insensitive)
    keys = [(p.get("name", "").lower(), p.get("address", {}).get("city", "").lower())
            for p in providers]
    for key, count in Counter(keys).items():
        if count > 1:
            name, city = key
            issues.append(f"  Mögliches Duplikat: '{name}' in '{city}' ({count}x)")

    return issues


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Providers JSON Validator")
    parser.add_argument(
        "--file",
        default=str(Path(__file__).parent.parent / "app" / "data" / "providers.json"),
        help="Pfad zur providers.json",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strenge Prüfung (fehlende Website, nicht-verifiziert etc.)",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        sys.exit(f"Datei nicht gefunden: {path}")

    with open(path, encoding="utf-8") as f:
        providers = json.load(f)

    print(f"Validiere {len(providers)} Einträge in {path} …\n")

    all_errors = []

    for idx, p in enumerate(providers, start=1):
        errs = validate_provider(p, idx, strict=args.strict)
        all_errors.extend(errs)

    dup_issues = check_duplicates(providers)

    # ── Summary ───────────────────────────────────────────────────────────
    cats    = Counter(p.get("category") for p in providers)
        
    verified = sum(1 for p in providers if p.get("verified"))
    missing_coords = sum(
        1 for p in providers
        if not p.get("coordinates", {}).get("lat")
    )

    print("── Statistik ────────────────────────────────────────────────")
    print(f"  Gesamt:           {len(providers)}")
    print(f"  DEXA:             {cats.get('dexa', 0)}")
    print(f"  Blutlabor:        {cats.get('blood_lab', 0)}")
    print(f"  Beides:           {cats.get('both', 0)}")
    print(f"  Verifiziert:      {verified}")
    print(f"  Fehlende Coords:  {missing_coords}")
    print()

    if dup_issues:
        print("── Duplikate ─────────────────────────────────────────────────")
        for issue in dup_issues:
            print(issue)
        print()

    if all_errors:
        print("── Fehler ───────────────────────────────────────────────────")
        for err in all_errors:
            print(err)
        print()
        print(f"❌ {len(all_errors)} Fehler gefunden.")
        sys.exit(1)
    else:
        print("✅ Alle Einträge valide.")


if __name__ == "__main__":
    main()
