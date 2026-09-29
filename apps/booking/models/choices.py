from django.db import models
from django.utils.translation import gettext_lazy as _


class LicenseCategory(models.TextChoices):
    A = "A", _("Category A (Motorcycle / Pikipiki)")
    B = "B", _("Category B (Light Passenger Vehicle / Ikinyabiziga gisanzwe)")
    C = "C", _("Category C (Heavy Goods Vehicle / Truck / Ikamyo)")
    D = "D", _("Category D (Passenger Bus / Bisi)")
    E = "E", _("Category E (Trailer / Remorque)")
    F = "F", _("Category F (Specially Adapted / Special)")


class RwandaDistrict(models.TextChoices):
    # Kigali City
    GASABO = "GASABO", _("Gasabo")
    KICUKIRO = "KICUKIRO", _("Kicukiro")
    NYARUGENGE = "NYARUGENGE", _("Nyarugenge")

    # Northern Province
    BURERA = "BURERA", _("Burera")
    GAKENKE = "GAKENKE", _("Gakenke")
    GICUMBI = "GICUMBI", _("Gicumbi")
    MUSANZE = "MUSANZE", _("Musanze")
    RULINDO = "RULINDO", _("Rulindo")

    # Southern Province
    GISAGARA = "GISAGARA", _("Gisagara")
    HUYE = "HUYE", _("Huye")
    KAMONYI = "KAMONYI", _("Kamonyi")
    MUHANGA = "MUHANGA", _("Muhanga")
    NYAMAGABE = "NYAMAGABE", _("Nyamagabe")
    NYANZA = "NYANZA", _("Nyanza")
    NYARUGURU = "NYARUGURU", _("Nyaruguru")
    RUHANGO = "RUHANGO", _("Ruhango")

    # Eastern Province
    BUGESERA = "BUGESERA", _("Bugesera")
    GATSIBO = "GATSIBO", _("Gatsibo")
    KAYONZA = "KAYONZA", _("Kayonza")
    KIREHE = "KIREHE", _("Kirehe")
    NGOMA = "NGOMA", _("Ngoma")
    NYAGATARE = "NYAGATARE", _("Nyagatare")
    RWAMAGANA = "RWAMAGANA", _("Rwamagana")

    # Western Province
    KARONGI = "KARONGI", _("Karongi")
    NGORORERO = "NGORORERO", _("Ngororero")
    NYABIHU = "NYABIHU", _("Nyabihu")
    NYAMASHEKE = "NYAMASHEKE", _("Nyamasheke")
    RUBAVU = "RUBAVU", _("Rubavu")
    RUSIZI = "RUSIZI", _("Rusizi")
    RUTSIRO = "RUTSIRO", _("Rutsiro")


class KicukiroWorkingSite(models.TextChoices):
    BUSANZA_AUTOMATED = "BUSANZA AUTOMATED CENTER", _("BUSANZA AUTOMATED CENTER")
    BUSANZA_SITE_KIC = "BUSANZA SITE (KIC)", _("BUSANZA SITE (KIC)")


class BookingState(models.TextChoices):
    PENDING = "PENDING", _("Pending — Submitted to System Admin")
    PROCESSING = "PROCESSING", _("Processing — Agent Actively Booking Slot")
    COMPLETED = "COMPLETED", _("Completed — Slot Successfully Booked")
    SLOTS_UNAVAILABLE = "SLOTS_UNAVAILABLE", _("Slots Unavailable — Retained in Queue")
    CANCELLED = "CANCELLED", _("Cancelled")
