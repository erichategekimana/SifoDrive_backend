"""
apps/examinations/services/credit_service.py
============================================
Manages exam purchase packages and credit ledger for Guest and Public candidates.
Enables paying per exam or purchasing multi-exam bundles via MoMo paying number.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

CREDITS_FILE = os.path.join(settings.BASE_DIR, "data", "exam_credits.json")


class ExamCreditService:
    """Manages practice exam credits and MoMo purchases for Guest/Public users."""

    PACKAGES = {
        "SINGLE": {
            "key": "SINGLE",
            "name": "1 Official Practice Exam",
            "name_kinyarwanda": "Ikizamini 1 cy'imyitozo",
            "name_french": "1 Examen Blanc Officiel",
            "credits": 1,
            "price_rwf": 1000,
            "description": "Full 20-minute, 20-question timed exam with instant results and question rationale.",
        },
        "BUNDLE_5": {
            "key": "BUNDLE_5",
            "name": "5 Official Practice Exams",
            "name_kinyarwanda": "Ibizamini 5 by'imyitozo (Save 20%)",
            "name_french": "Pack 5 Examens Blancs",
            "credits": 5,
            "price_rwf": 4000,
            "badge": "Popular",
            "description": "5 distinct randomly generated 20-question practice attempts across official domains.",
        },
        "BUNDLE_10": {
            "key": "BUNDLE_10",
            "name": "10 Official Practice Exams",
            "name_kinyarwanda": "Ibizamini 10 by'imyitozo (Best Value)",
            "name_french": "Pack 10 Examens Blancs",
            "credits": 10,
            "price_rwf": 7000,
            "badge": "Best Value",
            "description": "10 full mock exams pulling from all official Rwanda Traffic Police theory domains.",
        },
        "UNLIMITED_PASS": {
            "key": "UNLIMITED_PASS",
            "name": "30-Day Unlimited Exam Pass",
            "name_kinyarwanda": "Ubwishingizi bw'iminsi 30 bwo gukora ibizamini bitagira umupaka",
            "name_french": "Passe Illimité 30 Jours",
            "credits": 50,
            "price_rwf": 15000,
            "badge": "VIP Prep",
            "description": "Comprehensive 30-day exam readiness marathon with in-depth explanations.",
        },
    }

    @classmethod
    def list_packages(cls) -> List[Dict[str, Any]]:
        return list(cls.PACKAGES.values())

    @classmethod
    def _load_ledger(cls) -> Dict[str, Any]:
        if not os.path.exists(CREDITS_FILE):
            return {}
        try:
            with open(CREDITS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load exam credits ledger: %s", e)
            return {}

    @classmethod
    def _save_ledger(cls, ledger: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(CREDITS_FILE), exist_ok=True)
            temp = f"{CREDITS_FILE}.tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(ledger, f, indent=2, ensure_ascii=False)
            os.replace(temp, CREDITS_FILE)
        except Exception as e:
            logger.error("Failed to save exam credits ledger: %s", e)

    @classmethod
    def normalize_identifier(cls, phone_or_id: str) -> str:
        clean = (phone_or_id or "").strip()
        # Strip spaces and formatting
        return clean.replace(" ", "").replace("-", "")

    @classmethod
    def get_credit_balance(cls, phone_or_id: str) -> Dict[str, Any]:
        key = cls.normalize_identifier(phone_or_id)
        ledger = cls._load_ledger()
        record = ledger.get(key, {})
        credits_count = record.get("credits", 0)
        return {
            "identifier": key,
            "credits": credits_count,
            "total_purchased": record.get("total_purchased", 0),
            "total_consumed": record.get("total_consumed", 0),
            "last_purchased_at": record.get("last_purchased_at"),
            "transactions_count": len(record.get("transactions", [])),
        }

    @classmethod
    def purchase_package(
        cls,
        phone_number: str,
        paying_number: str,
        package_key: str,
        user: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Simulates MoMo payment processing and issues exam credits to candidate account/phone.
        """
        pkg = cls.PACKAGES.get(package_key.upper())
        if not pkg:
            raise ValueError(f"Unknown package key '{package_key}'. Available: {list(cls.PACKAGES.keys())}")

        key = cls.normalize_identifier(phone_number)
        if not key:
            raise ValueError("Phone number is required to credit exam attempts.")

        clean_paying = cls.normalize_identifier(paying_number) or key
        now = timezone.now()
        tx_id = f"MOMO-{uuid.uuid4().hex[:10].upper()}"

        ledger = cls._load_ledger()
        record = ledger.setdefault(key, {
            "phone_number": key,
            "user_id": str(getattr(user, "id", "")) if user else None,
            "credits": 0,
            "total_purchased": 0,
            "total_consumed": 0,
            "transactions": [],
        })

        record["credits"] += pkg["credits"]
        record["total_purchased"] += pkg["credits"]
        record["last_purchased_at"] = now.isoformat()

        tx_entry = {
            "tx_id": tx_id,
            "package": pkg["key"],
            "package_name": pkg["name"],
            "credits_added": pkg["credits"],
            "amount_rwf": pkg["price_rwf"],
            "paying_number": clean_paying,
            "recipient_phone": key,
            "status": "COMPLETED",
            "created_at": now.isoformat(),
        }
        record.setdefault("transactions", []).append(tx_entry)

        # If user id provided, map it also to user_id key
        if user and hasattr(user, "id"):
            u_id = str(user.id)
            if u_id != key:
                ledger[u_id] = record

        cls._save_ledger(ledger)
        logger.info(
            "Issued %d credits to %s for package %s (tx: %s, paying: %s)",
            pkg["credits"], key, pkg["key"], tx_id, clean_paying
        )

        return {
            "tx_id": tx_id,
            "status": "COMPLETED",
            "package": pkg,
            "credits_added": pkg["credits"],
            "current_balance": record["credits"],
            "paying_number": clean_paying,
            "recipient_phone": key,
            "message": f"Successfully purchased {pkg['name']}. {pkg['credits']} exam credits added.",
        }

    @classmethod
    def consume_credit(cls, phone_or_id: str) -> bool:
        """
        Consumes 1 exam credit upon launching an exam attempt.
        """
        key = cls.normalize_identifier(phone_or_id)
        ledger = cls._load_ledger()
        record = ledger.get(key)
        if not record or record.get("credits", 0) < 1:
            return False

        record["credits"] -= 1
        record["total_consumed"] = record.get("total_consumed", 0) + 1
        record["updated_at"] = timezone.now().isoformat()
        cls._save_ledger(ledger)
        logger.info("Consumed 1 exam credit for %s. Remaining: %d", key, record["credits"])
        return True

    @classmethod
    def get_all_transactions(cls) -> List[Dict[str, Any]]:
        """
        Retrieves all MoMo exam purchase transactions across all guest and public candidates.
        """
        ledger = cls._load_ledger()
        all_txs = []
        seen_tx_ids = set()
        for key, record in ledger.items():
            txs = record.get("transactions", [])
            for tx in txs:
                tx_id = tx.get("tx_id")
                if tx_id and tx_id in seen_tx_ids:
                    continue
                if tx_id:
                    seen_tx_ids.add(tx_id)
                item = dict(tx)
                if not item.get("recipient_phone"):
                    item["recipient_phone"] = record.get("phone_number", key)
                all_txs.append(item)
        all_txs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return all_txs
