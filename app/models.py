import json
from datetime import date
from . import db


class Provider(db.Model):
    """
    Central model for all providers (DEXA clinics and blood labs).
    Designed to be easily extensible with new fields and categories.
    """

    __tablename__ = "providers"

    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(256), nullable=False)

    # "dexa" | "blood_lab" | "both"
    category = db.Column(db.String(32), nullable=False)

    # JSON list: ["body_composition", "bone_density", "blood_test_self_pay"]
    _services = db.Column("services", db.Text, nullable=False, default="[]")

    # Address fields
    street = db.Column(db.String(256))
    zip_code = db.Column(db.String(16))
    city = db.Column(db.String(128))
    country = db.Column(db.String(4), default="DE")  # ISO 3166-1 alpha-2

    # Coordinates
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)

    # Contact
    phone = db.Column(db.String(64))
    website = db.Column(db.String(512))
    email = db.Column(db.String(256))

    # Pricing (stored as JSON dict)
    _prices = db.Column("prices", db.Text, default="{}")

    self_pay = db.Column(db.Boolean, default=True)
    verified = db.Column(db.Boolean, default=False)
    last_verified = db.Column(db.String(16))  # ISO date string
    notes = db.Column(db.Text)
    source = db.Column(db.String(256))

    # ---------- Properties ----------

    @property
    def services(self):
        return json.loads(self._services or "[]")

    @services.setter
    def services(self, value):
        self._services = json.dumps(value, ensure_ascii=False)

    @property
    def prices(self):
        return json.loads(self._prices or "{}")

    @prices.setter
    def prices(self, value):
        self._prices = json.dumps(value, ensure_ascii=False)

    # ---------- Serialization ----------

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "services": self.services,
            "address": {
                "street": self.street,
                "zip": self.zip_code,
                "city": self.city,
                "country": self.country,
            },
            "coordinates": {"lat": self.lat, "lng": self.lng},
            "contact": {
                "phone": self.phone,
                "website": self.website,
                "email": self.email,
            },
            "self_pay": self.self_pay,
            "prices": self.prices,
            "verified": self.verified,
            "last_verified": self.last_verified,
            "notes": self.notes,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Provider":
        obj = cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            street=data["address"]["street"],
            zip_code=data["address"]["zip"],
            city=data["address"]["city"],
            country=data["address"]["country"],
            lat=data["coordinates"]["lat"],
            lng=data["coordinates"]["lng"],
            phone=data["contact"].get("phone", ""),
            website=data["contact"].get("website", ""),
            email=data["contact"].get("email", ""),
            self_pay=data.get("self_pay", True),
            verified=data.get("verified", False),
            last_verified=data.get("last_verified"),
            notes=data.get("notes", ""),
            source=data.get("source", ""),
        )
        obj.services = data.get("services", [])
        obj.prices = data.get("prices", {})
        return obj

    def __repr__(self):
        return f"<Provider {self.id}: {self.name}>"
