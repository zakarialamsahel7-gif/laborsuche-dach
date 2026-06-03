from flask import Blueprint, jsonify, request, abort
from .models import Provider
from . import db

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

VALID_CATEGORIES = {"dexa", "blood_lab", "both"}
VALID_COUNTRIES = {"DE", "AT", "CH"}


# ── GET /api/v1/providers ────────────────────────────────────────────────────
@api_bp.get("/providers")
def list_providers():
    """
    Query params:
      category  – dexa | blood_lab | both
      country   – DE | AT | CH
      service   – body_composition | bone_density | blood_test_self_pay
      verified  – true | false
      q         – free-text search on name/city
    """
    query = Provider.query

    category = request.args.get("category")
    if category:
        if category not in VALID_CATEGORIES:
            abort(400, f"Invalid category. Choose from: {', '.join(VALID_CATEGORIES)}")
        # "both" providers should appear in dexa and blood_lab filters too
        if category == "dexa":
            query = query.filter(Provider.category.in_(["dexa", "both"]))
        elif category == "blood_lab":
            query = query.filter(Provider.category.in_(["blood_lab", "both"]))
        else:
            query = query.filter(Provider.category == "both")

    country = request.args.get("country")
    if country:
        if country.upper() not in VALID_COUNTRIES:
            abort(400, f"Invalid country. Choose from: {', '.join(VALID_COUNTRIES)}")
        query = query.filter(Provider.country == country.upper())

    verified = request.args.get("verified")
    if verified is not None:
        query = query.filter(Provider.verified == (verified.lower() == "true"))

    q = request.args.get("q", "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Provider.name.ilike(like),
                Provider.city.ilike(like),
                Provider.zip_code.ilike(like),
            )
        )

    providers = query.order_by(Provider.city, Provider.name).all()

    # Optional service filter (post-query, since services are JSON-serialised)
    service = request.args.get("service")
    if service:
        providers = [p for p in providers if service in p.services]

    return jsonify(
        {
            "count": len(providers),
            "providers": [p.to_dict() for p in providers],
        }
    )


# ── GET /api/v1/providers/<id> ───────────────────────────────────────────────
@api_bp.get("/providers/<string:provider_id>")
def get_provider(provider_id):
    provider = Provider.query.get_or_404(provider_id)
    return jsonify(provider.to_dict())


# ── POST /api/v1/providers ───────────────────────────────────────────────────
@api_bp.post("/providers")
def create_provider():
    data = request.get_json(force=True, silent=True)
    if not data:
        abort(400, "JSON body required")

    errors = _validate_provider(data)
    if errors:
        return jsonify({"errors": errors}), 422

    if Provider.query.get(data["id"]):
        abort(409, f"Provider with id '{data['id']}' already exists")

    provider = Provider.from_dict(data)
    db.session.add(provider)
    db.session.commit()
    return jsonify(provider.to_dict()), 201


# ── PUT /api/v1/providers/<id> ───────────────────────────────────────────────
@api_bp.put("/providers/<string:provider_id>")
def update_provider(provider_id):
    provider = Provider.query.get_or_404(provider_id)
    data = request.get_json(force=True, silent=True)
    if not data:
        abort(400, "JSON body required")

    # Partial update – only overwrite supplied top-level keys
    if "name" in data:
        provider.name = data["name"]
    if "category" in data:
        provider.category = data["category"]
    if "services" in data:
        provider.services = data["services"]
    if "address" in data:
        addr = data["address"]
        provider.street = addr.get("street", provider.street)
        provider.zip_code = addr.get("zip", provider.zip_code)
        provider.city = addr.get("city", provider.city)
        provider.country = addr.get("country", provider.country)
    if "coordinates" in data:
        provider.lat = data["coordinates"].get("lat", provider.lat)
        provider.lng = data["coordinates"].get("lng", provider.lng)
    if "contact" in data:
        c = data["contact"]
        provider.phone = c.get("phone", provider.phone)
        provider.website = c.get("website", provider.website)
        provider.email = c.get("email", provider.email)
    if "prices" in data:
        provider.prices = data["prices"]
    if "self_pay" in data:
        provider.self_pay = data["self_pay"]
    if "verified" in data:
        provider.verified = data["verified"]
    if "last_verified" in data:
        provider.last_verified = data["last_verified"]
    if "notes" in data:
        provider.notes = data["notes"]
    if "source" in data:
        provider.source = data["source"]

    db.session.commit()
    return jsonify(provider.to_dict())


# ── DELETE /api/v1/providers/<id> ────────────────────────────────────────────
@api_bp.delete("/providers/<string:provider_id>")
def delete_provider(provider_id):
    provider = Provider.query.get_or_404(provider_id)
    db.session.delete(provider)
    db.session.commit()
    return jsonify({"deleted": provider_id}), 200


# ── GET /api/v1/stats ────────────────────────────────────────────────────────
@api_bp.get("/stats")
def stats():
    total = Provider.query.count()
    dexa = Provider.query.filter(Provider.category.in_(["dexa", "both"])).count()
    blood = Provider.query.filter(Provider.category.in_(["blood_lab", "both"])).count()
    by_country = {
        c: Provider.query.filter(Provider.country == c).count()
        for c in VALID_COUNTRIES
    }
    verified = Provider.query.filter(Provider.verified == True).count()  # noqa: E712
    return jsonify(
        {
            "total": total,
            "dexa": dexa,
            "blood_lab": blood,
            "both": Provider.query.filter(Provider.category == "both").count(),
            "by_country": by_country,
            "verified": verified,
        }
    )


# ── Error handlers ────────────────────────────────────────────────────────────
@api_bp.errorhandler(400)
@api_bp.errorhandler(404)
@api_bp.errorhandler(409)
@api_bp.errorhandler(422)
def handle_error(e):
    return jsonify({"error": str(e)}), e.code


# ── Helpers ───────────────────────────────────────────────────────────────────
def _validate_provider(data: dict) -> list[str]:
    errors = []
    required = ["id", "name", "category", "address", "coordinates"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: '{field}'")
    if "category" in data and data["category"] not in VALID_CATEGORIES:
        errors.append(f"category must be one of: {', '.join(VALID_CATEGORIES)}")
    if "address" in data:
        for sub in ["street", "zip", "city", "country"]:
            if sub not in data["address"]:
                errors.append(f"address.{sub} is required")
    if "coordinates" in data:
        for sub in ["lat", "lng"]:
            if sub not in data["coordinates"]:
                errors.append(f"coordinates.{sub} is required")
    return errors
