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
PACKAGES_CONFIG_FILE = os.path.join(settings.BASE_DIR, "data", "exam_packages_config.json")
PENDING_PAYMENTS_FILE = os.path.join(settings.BASE_DIR, "data", "pending_payments.json")


class ExamCreditService:
    """Manages practice exam credits and MoMo purchases for Guest/Public users."""

    PACKAGES = {
        "BASIC": {
            "key": "BASIC",
            "name": "Exam",
            "name_kinyarwanda": "Exam",
            "name_french": "Exam",
            "credits": 1,
            "min_exams": 1,
            "max_exams": 5,
            "default_exams": 1,
            "price_per_exam_rwf": 1000,
            "price_rwf": 1000,
            "badge": "Basic",
            "is_active": True,
            "isActive": True,
            "description": "Full 20-minute, 20-question timed exam with instant results and question rationale.",
        },
        "REGULAR": {
            "key": "REGULAR",
            "name": "Exam",
            "name_kinyarwanda": "Exam",
            "name_french": "Exam",
            "credits": 6,
            "min_exams": 6,
            "max_exams": 10,
            "default_exams": 6,
            "price_per_exam_rwf": 800,
            "price_rwf": 4800,
            "badge": "Regular",
            "is_active": True,
            "isActive": True,
            "description": "6 to 10 distinct randomly generated 20-question practice attempts across official domains.",
        },
        "PREMIUM": {
            "key": "PREMIUM",
            "name": "Exam",
            "name_kinyarwanda": "Exam",
            "name_french": "Exam",
            "credits": 11,
            "min_exams": 11,
            "max_exams": 20,
            "default_exams": 11,
            "price_per_exam_rwf": 700,
            "price_rwf": 7700,
            "badge": "Premium",
            "is_active": True,
            "isActive": True,
            "description": "11 to 20 full mock exams pulling from all official Rwanda Traffic Police theory domains.",
        },
        "ENTERPRISE": {
            "key": "ENTERPRISE",
            "name": "Exam",
            "name_kinyarwanda": "Exam",
            "name_french": "Exam",
            "credits": 9999,
            "min_exams": 1,
            "max_exams": 1,
            "default_exams": 1,
            "price_per_exam_rwf": 50000,
            "price_rwf": 50000,
            "badge": "Enterprise",
            "is_active": True,
            "isActive": True,
            "description": "Unlimited practice exam attempts for driving schools, academies, and institutional cohorts.",
        },
    }

    LEGACY_PACKAGES = {
        "SINGLE": {
            "key": "SINGLE",
            "name": "1 Exam",
            "name_kinyarwanda": "1 Exam",
            "name_french": "1 Exam",
            "credits": 1,
            "min_exams": 1,
            "max_exams": 5,
            "default_exams": 1,
            "price_per_exam_rwf": 1000,
            "price_rwf": 1000,
            "badge": "Basic",
            "description": "Full 20-minute, 20-question timed exam with instant results and question rationale.",
        },
        "BUNDLE_5": {
            "key": "BUNDLE_5",
            "name": "5 Exam",
            "name_kinyarwanda": "5 Exam",
            "name_french": "5 Exam",
            "credits": 5,
            "min_exams": 6,
            "max_exams": 10,
            "default_exams": 6,
            "price_per_exam_rwf": 800,
            "price_rwf": 4000,
            "badge": "Regular",
            "description": "5 distinct randomly generated 20-question practice attempts across official domains.",
        },
        "BUNDLE_10": {
            "key": "BUNDLE_10",
            "name": "10 Exam",
            "name_kinyarwanda": "10 Exam",
            "name_french": "10 Exam",
            "credits": 10,
            "min_exams": 6,
            "max_exams": 10,
            "default_exams": 10,
            "price_per_exam_rwf": 800,
            "price_rwf": 7000,
            "badge": "Regular",
            "description": "10 full mock exams pulling from all official Rwanda Traffic Police theory domains.",
        },
        "UNLIMITED_PASS": {
            "key": "UNLIMITED_PASS",
            "name": "Unlimited Exam",
            "name_kinyarwanda": "Unlimited Exam",
            "name_french": "Unlimited Exam",
            "credits": 50,
            "min_exams": 11,
            "max_exams": 20,
            "default_exams": 20,
            "price_per_exam_rwf": 700,
            "price_rwf": 15000,
            "badge": "Enterprise",
            "description": "Comprehensive 30-day exam readiness marathon with in-depth explanations.",
        },
    }

    @classmethod
    def _load_packages_config(cls) -> Dict[str, Dict[str, Any]]:
        packages_dict = {k: dict(v) for k, v in cls.PACKAGES.items()}
        if os.path.exists(PACKAGES_CONFIG_FILE):
            try:
                with open(PACKAGES_CONFIG_FILE, "r", encoding="utf-8") as f:
                    overrides = json.load(f)
                    if isinstance(overrides, dict):
                        for k, v in overrides.items():
                            k_upper = k.upper()
                            if k_upper in packages_dict and isinstance(v, dict):
                                packages_dict[k_upper].update(v)
                            elif isinstance(v, dict):
                                packages_dict[k_upper] = v
                    elif isinstance(overrides, list):
                        for item in overrides:
                            if isinstance(item, dict) and "key" in item:
                                k_upper = str(item["key"]).upper()
                                if k_upper in packages_dict:
                                    packages_dict[k_upper].update(item)
                                else:
                                    packages_dict[k_upper] = item
            except Exception as e:
                logger.error("Failed to load packages config: %s", e)
        return packages_dict

    @classmethod
    def save_packages_config(cls, packages: Any) -> Dict[str, Dict[str, Any]]:
        """Persists package overrides to data/exam_packages_config.json."""
        from apps.examinations.services.exam_service import ExamService
        is_published = ExamService.is_public_exam_published()

        current = cls._load_packages_config()
        if isinstance(packages, list):
            for item in packages:
                if isinstance(item, dict) and "key" in item:
                    k_upper = str(item["key"]).upper()
                    active_val = item.get("isActive", item.get("is_active", True)) if is_published else False
                    clean_item = dict(item)
                    clean_item["isActive"] = bool(active_val)
                    clean_item["is_active"] = bool(active_val)
                    if k_upper in current:
                        current[k_upper].update(clean_item)
                    else:
                        current[k_upper] = clean_item
        elif isinstance(packages, dict):
            for k, v in packages.items():
                if isinstance(v, dict):
                    k_upper = str(k).upper()
                    active_val = v.get("isActive", v.get("is_active", True)) if is_published else False
                    clean_v = dict(v)
                    clean_v["isActive"] = bool(active_val)
                    clean_v["is_active"] = bool(active_val)
                    if k_upper in current:
                        current[k_upper].update(clean_v)
                    else:
                        current[k_upper] = clean_v

        try:
            os.makedirs(os.path.dirname(PACKAGES_CONFIG_FILE), exist_ok=True)
            with open(PACKAGES_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2, ensure_ascii=False)
            logger.info("Exam packages config successfully saved to %s", PACKAGES_CONFIG_FILE)
        except Exception as e:
            logger.error("Failed to save packages config: %s", e)

        return current

    @classmethod
    def get_package_definition(cls, package_key: str) -> Optional[Dict[str, Any]]:
        k = (package_key or "").upper()
        all_pkgs = cls._load_packages_config()
        if k in all_pkgs:
            return all_pkgs[k]
        if k in cls.LEGACY_PACKAGES:
            return cls.LEGACY_PACKAGES[k]
        return None

    @classmethod
    def list_packages(cls) -> List[Dict[str, Any]]:
        from apps.examinations.services.exam_service import ExamService
        if not ExamService.is_public_exam_published():
            return []

        all_pkgs = cls._load_packages_config()
        return [
            pkg for pkg in all_pkgs.values()
            if pkg.get("is_active", True) is not False and pkg.get("isActive", True) is not False
        ]

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
    def _load_pending_payments(cls) -> Dict[str, Any]:
        if not os.path.exists(PENDING_PAYMENTS_FILE):
            return {}
        try:
            with open(PENDING_PAYMENTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load pending payments: %s", e)
            return {}

    @classmethod
    def _save_pending_payments(cls, pending: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(PENDING_PAYMENTS_FILE), exist_ok=True)
            temp = f"{PENDING_PAYMENTS_FILE}.tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(pending, f, indent=2, ensure_ascii=False)
            os.replace(temp, PENDING_PAYMENTS_FILE)
        except Exception as e:
            logger.error("Failed to save pending payments: %s", e)

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
        exam_count: Optional[int] = None,
        user: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Simulates MoMo payment processing and issues exam credits to candidate account/phone.
        Supports dynamic exam counts within tier limits:
          - Basic: 1 - 5 exams (1000 RWF / exam)
          - Regular: 6 - 10 exams (800 RWF / exam)
          - Premium: 11 - 20 exams (700 RWF / exam)
        """
        from apps.examinations.services.exam_service import ExamService
        if not ExamService.is_public_exam_published():
            raise ValueError("The Public Examination is currently unpublished. Practice exam plans and packages cannot be purchased.")

        pkg_key = (package_key or "").upper()
        pkg = cls.get_package_definition(pkg_key)

        if pkg and (not pkg.get("is_active", True) or not pkg.get("isActive", True)):
            raise ValueError(f"The plan '{pkg.get('badge', package_key)}' is currently not active on public pricing.")

        if pkg:
            tier_key = pkg.get("key", pkg_key)
            badge = pkg.get("badge", "Exam")
            rate = pkg.get("price_per_exam_rwf", 1000)
            min_c = pkg.get("min_exams", 1)
            max_c = pkg.get("max_exams", 100)
            default_c = pkg.get("default_exams", pkg.get("credits", min_c))
        elif pkg_key in ("BASIC", "SINGLE"):
            tier_key = "BASIC"
            badge = "Basic"
            rate = 1000
            min_c, max_c = 1, 5
            default_c = 1
        elif pkg_key in ("REGULAR", "BUNDLE_5", "BUNDLE_10"):
            tier_key = "REGULAR"
            badge = "Regular"
            rate = 800
            min_c, max_c = 6, 10
            default_c = 6
        elif pkg_key in ("PREMIUM", "UNLIMITED_PASS"):
            tier_key = "PREMIUM"
            badge = "Premium"
            rate = 700
            min_c, max_c = 11, 20
            default_c = 11
        else:
            raise ValueError(f"Unknown package key '{package_key}'. Available: {list(cls.PACKAGES.keys())}")

        if exam_count is not None and exam_count > 0:
            count = max(min_c, min(exam_count, max_c)) if min_c and max_c else exam_count
            price_rwf = count * rate
        else:
            if pkg_key in cls.LEGACY_PACKAGES and "price_rwf" in cls.LEGACY_PACKAGES[pkg_key]:
                count = cls.LEGACY_PACKAGES[pkg_key]["credits"]
                price_rwf = cls.LEGACY_PACKAGES[pkg_key]["price_rwf"]
            else:
                count = default_c
                price_rwf = count * rate

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

        record["credits"] += count
        record["total_purchased"] += count
        record["last_purchased_at"] = now.isoformat()

        package_name = f"{count} Exam"
        tx_entry = {
            "tx_id": tx_id,
            "package": tier_key,
            "package_name": package_name,
            "credits_added": count,
            "amount_rwf": price_rwf,
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
            "Issued %d credits to %s for package %s (tx: %s, paying: %s, amount: %d RWF)",
            count, key, tier_key, tx_id, clean_paying, price_rwf
        )

        return {
            "tx_id": tx_id,
            "status": "COMPLETED",
            "package": {
                "key": tier_key,
                "name": package_name,
                "credits": count,
                "price_rwf": price_rwf,
                "badge": badge,
            },
            "credits_added": count,
            "current_balance": record["credits"],
            "paying_number": clean_paying,
            "recipient_phone": key,
            "message": f"Successfully purchased {package_name}. {count} exam credits added.",
        }

    @classmethod
    def initiate_momo_purchase(
        cls,
        phone_number: str,
        paying_number: str,
        package_key: str,
        exam_count: Optional[int] = None,
        full_name: str = "",
        user: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Initiates real MoMo RequestToPay via MTN MoMo Collection API.
        Returns reference_id, amount_rwf, and status='PENDING'.
        """
        from apps.examinations.services.exam_service import ExamService
        from apps.payments.services.payment_service import PaymentService

        if not ExamService.is_public_exam_published():
            raise ValueError("The Public Examination is currently unpublished. Practice exam plans and packages cannot be purchased.")

        pkg_key = (package_key or "").upper()
        pkg = cls.get_package_definition(pkg_key)

        if pkg and (not pkg.get("is_active", True) or not pkg.get("isActive", True)):
            raise ValueError(f"The plan '{pkg.get('badge', package_key)}' is currently not active on public pricing.")

        if pkg:
            tier_key = pkg.get("key", pkg_key)
            badge = pkg.get("badge", "Exam")
            rate = pkg.get("price_per_exam_rwf", 1000)
            min_c = pkg.get("min_exams", 1)
            max_c = pkg.get("max_exams", 100)
            default_c = pkg.get("default_exams", pkg.get("credits", min_c))
        elif pkg_key in ("BASIC", "SINGLE"):
            tier_key = "BASIC"
            badge = "Basic"
            rate = 1000
            min_c, max_c = 1, 5
            default_c = 1
        elif pkg_key in ("REGULAR", "BUNDLE_5", "BUNDLE_10"):
            tier_key = "REGULAR"
            badge = "Regular"
            rate = 800
            min_c, max_c = 6, 10
            default_c = 6
        elif pkg_key in ("PREMIUM", "UNLIMITED_PASS"):
            tier_key = "PREMIUM"
            badge = "Premium"
            rate = 700
            min_c, max_c = 11, 20
            default_c = 11
        else:
            raise ValueError(f"Unknown package key '{package_key}'. Available: {list(cls.PACKAGES.keys())}")

        if exam_count is not None and exam_count > 0:
            count = max(min_c, min(exam_count, max_c)) if min_c and max_c else exam_count
            price_rwf = count * rate
        else:
            if pkg_key in cls.LEGACY_PACKAGES and "price_rwf" in cls.LEGACY_PACKAGES[pkg_key]:
                count = cls.LEGACY_PACKAGES[pkg_key]["credits"]
                price_rwf = cls.LEGACY_PACKAGES[pkg_key]["price_rwf"]
            else:
                count = default_c
                price_rwf = count * rate

        key = cls.normalize_identifier(phone_number)
        if not key:
            raise ValueError("Phone number is required to receive exam credits.")

        clean_paying = cls.normalize_identifier(paying_number) or key
        package_name = f"{count} Exam" if count == 1 else f"{count} Exams"
        external_id = f"SIFO-{uuid.uuid4().hex[:8].upper()}"

        # Trigger MTN MoMo RequestToPay
        momo_res = PaymentService.initiate_momo_charge(
            amount=price_rwf,
            payer_phone=clean_paying,
            external_id=external_id,
            payer_message=f"SifoDrive: Pay {price_rwf} RWF for {package_name}",
            payee_note=f"SifoDrive - {key}",
        )

        ref_id = momo_res["reference_id"]
        now = timezone.now()

        # Save pending purchase record
        pending = cls._load_pending_payments()
        pending[ref_id] = {
            "reference_id": ref_id,
            "external_id": external_id,
            "recipient_phone": key,
            "paying_number": clean_paying,
            "full_name": full_name or "",
            "user_id": str(getattr(user, "id", "")) if user else None,
            "package_key": tier_key,
            "package_name": package_name,
            "credits": count,
            "amount_rwf": price_rwf,
            "status": "PENDING",
            "created_at": now.isoformat(),
        }
        cls._save_pending_payments(pending)

        return {
            "reference_id": ref_id,
            "status": "PENDING",
            "package_name": package_name,
            "credits": count,
            "amount_rwf": price_rwf,
            "paying_number": clean_paying,
            "phone_number": key,
            "message": f"Payment request of {price_rwf} RWF sent to {clean_paying}. Please check your phone to confirm.",
        }

    @classmethod
    def check_payment_status(cls, reference_id: str) -> Dict[str, Any]:
        """
        Polls MTN MoMo for payment confirmation.
        Once SUCCESSFUL, automatically adds credits to the recipient phone ledger.
        """
        from apps.payments.services.payment_service import PaymentService

        ref = str(reference_id)
        pending = cls._load_pending_payments()
        record_info = pending.get(ref)

        if not record_info:
            # Check completed transactions in ledger as fallback
            ledger = cls._load_ledger()
            for recipient, rec in ledger.items():
                for tx in rec.get("transactions", []):
                    if tx.get("reference_id") == ref or tx.get("tx_id", "").endswith(ref[:8].upper()):
                        return {
                            "reference_id": ref,
                            "status": "SUCCESSFUL",
                            "credits_added": tx.get("credits_added", 0),
                            "current_balance": rec.get("credits", 0),
                            "amount_rwf": tx.get("amount_rwf", 0),
                            "message": "Payment confirmed! Your exam credits are ready.",
                        }
            return {
                "reference_id": ref,
                "status": "FAILED",
                "message": "Transaction reference not found.",
            }

        if record_info.get("status") == "COMPLETED":
            ledger = cls._load_ledger()
            rec = ledger.get(record_info["recipient_phone"], {})
            return {
                "reference_id": ref,
                "status": "SUCCESSFUL",
                "credits_added": record_info["credits"],
                "current_balance": rec.get("credits", 0),
                "amount_rwf": record_info["amount_rwf"],
                "message": "Payment confirmed! Your exam credits are ready.",
            }

        # Query MTN MoMo API
        momo_status = PaymentService.check_momo_status(ref)
        raw_status = (momo_status.get("status") or "PENDING").upper()

        if raw_status == "SUCCESSFUL":
            # Fulfill the purchase
            key = record_info["recipient_phone"]
            count = record_info["credits"]
            price_rwf = record_info["amount_rwf"]
            clean_paying = record_info["paying_number"]
            tier_key = record_info["package_key"]
            package_name = record_info["package_name"]
            now = timezone.now()
            tx_id = f"MOMO-{ref[:8].upper()}"

            ledger = cls._load_ledger()
            rec = ledger.setdefault(key, {
                "phone_number": key,
                "user_id": record_info.get("user_id"),
                "credits": 0,
                "total_purchased": 0,
                "total_consumed": 0,
                "transactions": [],
            })

            rec["credits"] += count
            rec["total_purchased"] += count
            rec["last_purchased_at"] = now.isoformat()

            tx_entry = {
                "tx_id": tx_id,
                "reference_id": ref,
                "financial_transaction_id": momo_status.get("financial_transaction_id"),
                "package": tier_key,
                "package_name": package_name,
                "credits_added": count,
                "amount_rwf": price_rwf,
                "paying_number": clean_paying,
                "recipient_phone": key,
                "status": "COMPLETED",
                "created_at": now.isoformat(),
            }
            rec.setdefault("transactions", []).append(tx_entry)

            # Map user_id if present
            u_id = record_info.get("user_id")
            if u_id and u_id != key:
                ledger[u_id] = rec

            cls._save_ledger(ledger)

            # Mark pending as COMPLETED
            record_info["status"] = "COMPLETED"
            record_info["completed_at"] = now.isoformat()
            record_info["financial_transaction_id"] = momo_status.get("financial_transaction_id")
            cls._save_pending_payments(pending)

            logger.info(
                "Fulfilled MoMo purchase: %d credits added to %s (ref: %s, amount: %d RWF)",
                count, key, ref, price_rwf
            )

            return {
                "reference_id": ref,
                "status": "SUCCESSFUL",
                "credits_added": count,
                "current_balance": rec["credits"],
                "amount_rwf": price_rwf,
                "tx_id": tx_id,
                "financial_transaction_id": momo_status.get("financial_transaction_id"),
                "message": f"Payment of {price_rwf} RWF confirmed! {count} exam credits have been added.",
            }

        elif raw_status == "FAILED":
            record_info["status"] = "FAILED"
            record_info["failed_at"] = timezone.now().isoformat()
            cls._save_pending_payments(pending)
            return {
                "reference_id": ref,
                "status": "FAILED",
                "message": momo_status.get("reason") or "Payment was rejected or timed out on your phone.",
            }

        return {
            "reference_id": ref,
            "status": "PENDING",
            "message": "Waiting for Mobile Money PIN confirmation on your phone...",
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
