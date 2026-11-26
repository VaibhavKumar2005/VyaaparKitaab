"""
Real-Time Account Aggregator / Bank Sandbox Stream Simulator.

Provides an automated or on-demand transaction ingestion flow that models real RBI Account
Aggregator (AA) credit notifications:
1. Generates realistic, verified UPI / Bank credit transactions (Google Pay, PhonePe, Paytm, BHIM UPI).
2. Persists the transaction idempotently into PostgreSQL `bank_transactions` (with UniqueConstraint protection).
3. Emits a scoped `bank.credit.received` event on the Server-Sent Events (SSE) bus.
4. Allows starting an automated interval producer (e.g. every 10 seconds), stopping it, or
   triggering an instant single credit ("Emit One Test Credit") for live pitch demonstrations.
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import SessionLocal
from app.cores.money import money_to_float, to_money
from app.models.banking_consent import BankTransaction
from app.services.event_bus import publish_event
from app.services.unified_ledger import sync_bank_rows_to_unified

logger = logging.getLogger(__name__)

SIMULATED_TEMPLATES: list[dict[str, Any]] = [
    {
        "base_amount": 2480.0,
        "app": "Google Pay",
        "counterparty": "Rahul Sharma",
        "vpa": "rahul.sharma@okhdfcbank",
        "category": "Business Sales",
        "narration": "UPI/CR/402918291029/Rahul Sharma/Business Sales",
    },
    {
        "base_amount": 1250.0,
        "app": "PhonePe",
        "counterparty": "Priya Patel",
        "vpa": "priya.patel@ybl",
        "category": "Retail Inflow",
        "narration": "UPI/CR/419203810293/Priya Patel/Store Inflow",
    },
    {
        "base_amount": 3800.0,
        "app": "Paytm",
        "counterparty": "Vikram Malhotra",
        "vpa": "vikram.m@paytm",
        "category": "Wholesale Order",
        "narration": "UPI/CR/438291029384/Vikram/Bulk Goods",
    },
    {
        "base_amount": 850.0,
        "app": "Google Pay",
        "counterparty": "Meera Sen",
        "vpa": "meera.sen@okaxis",
        "category": "Retail Inflow",
        "narration": "UPI/CR/409281726354/Meera/Retail Payment",
    },
    {
        "base_amount": 5400.0,
        "app": "BHIM UPI",
        "counterparty": "Apex Enterprises",
        "vpa": "apex.ent@upi",
        "category": "Commercial Services",
        "narration": "UPI/CR/482910394827/Apex Enterprises/Consulting Settlement",
    },
    {
        "base_amount": 1690.0,
        "app": "PhonePe",
        "counterparty": "Amit Verma",
        "vpa": "amit.v@ibl",
        "category": "Business Sales",
        "narration": "UPI/CR/492019283746/Amit Verma/Grocery Order",
    },
    {
        "base_amount": 4200.0,
        "app": "Google Pay",
        "counterparty": "Kavita Rao",
        "vpa": "kavita.rao@oksbi",
        "category": "Store Settlement",
        "narration": "UPI/CR/410293847561/Kavita/Invoice Settlement",
    },
]

SIMULATED_DEBIT_TEMPLATES: list[dict[str, Any]] = [
    {
        "base_amount": 1850.0,
        "app": "Google Pay",
        "counterparty": "Metro Wholesale Distributors",
        "vpa": "metro.wholesale@okicici",
        "category": "Wholesale Inventory",
        "narration": "UPI/DR/510293847111/Metro Wholesale/Stock Restock",
    },
    {
        "base_amount": 640.0,
        "app": "PhonePe",
        "counterparty": "IndianOil Fuel Station",
        "vpa": "indianoil@ybl",
        "category": "Travel & Fuel",
        "narration": "UPI/DR/510293847222/IndianOil/Delivery Scooter Petrol",
    },
    {
        "base_amount": 1290.0,
        "app": "Paytm",
        "counterparty": "Tata Power Electricity",
        "vpa": "tatapower@paytm",
        "category": "Bills & Utilities",
        "narration": "UPI/DR/510293847333/Tata Power/Shop Electricity Bill",
    },
    {
        "base_amount": 420.0,
        "app": "Google Pay",
        "counterparty": "Swiggy Food Delivery",
        "vpa": "swiggy@okaxis",
        "category": "Food & Dining",
        "narration": "UPI/DR/510293847444/Swiggy/Staff Lunch Order",
    },
    {
        "base_amount": 999.0,
        "app": "PhonePe",
        "counterparty": "Jio Fiber Broadband",
        "vpa": "jiofiber@ibl",
        "category": "Bills & Utilities",
        "narration": "UPI/DR/510293847555/Jio Fiber/Store WiFi Recharge",
    },
]


async def emit_simulated_credit(
    db: AsyncSession,
    user_id: uuid.UUID,
    template_override: dict[str, Any] | None = None,
    direction: str = "CREDIT",
) -> dict[str, Any]:
    """
    Generates a single realistic sandbox bank transaction (CREDIT or DEBIT), saves it
    to PostgreSQL (`bank_transactions` + `unified_transactions`), and publishes the event on SSE.
    """
    now = datetime.now(UTC)
    resolved_dir = direction.strip().upper()
    if resolved_dir == "AUTO":
        resolved_dir = "DEBIT" if random.random() < 0.35 else "CREDIT"
    if resolved_dir not in ("CREDIT", "DEBIT"):
        resolved_dir = "CREDIT"

    pool = SIMULATED_DEBIT_TEMPLATES if resolved_dir == "DEBIT" else SIMULATED_TEMPLATES
    template = template_override or random.choice(pool)

    # Slight random variation in amount for realism (e.g. ± ₹10 to ₹50)
    variance = random.choice([-30, -15, 0, 15, 30, 50])
    amount_dec = max(to_money(100), to_money(template["base_amount"]) + to_money(variance))
    amount = money_to_float(amount_dec)

    prefix = "aa_demo_dr" if resolved_dir == "DEBIT" else "aa_demo"
    txn_id = f"{prefix}_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    date_str = now.date().isoformat()
    masked_acc = "XXXX-XXXX-4821"

    stmt = (
        pg_insert(BankTransaction)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            txn_id=txn_id,
            timestamp=now,
            date=date_str,
            amount=amount_dec,
            type=resolved_dir,
            mode="UPI",
            app=template["app"],
            vpa=template.get("vpa"),
            narration=template["narration"],
            category=template["category"],
            counterparty=template["counterparty"],
            masked_acc=masked_acc,
            source="aa_sandbox",
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "txn_id"])
    )
    await db.execute(stmt)
    await sync_bank_rows_to_unified(
        db,
        user_id,
        [
            {
                "txn_id": txn_id,
                "timestamp": now,
                "amount": amount_dec,
                "type": resolved_dir,
                "mode": "UPI",
                "app": template["app"],
                "narration": template["narration"],
                "category": template["category"],
                "counterparty": template["counterparty"],
                "source": "aa_sandbox",
            }
        ],
        commit=False,
    )
    await db.commit()

    event_name = "bank.debit.received" if resolved_dir == "DEBIT" else "bank.credit.received"
    event_payload = {
        "event": event_name,
        "txn_id": txn_id,
        "amount": amount,
        "currency": "INR",
        "type": resolved_dir,
        "mode": "UPI",
        "app": template["app"],
        "vpa": template.get("vpa"),
        "narration": template["narration"],
        "category": template["category"],
        "counterparty": template["counterparty"],
        "masked_acc": masked_acc,
        "source": "aa_sandbox",
        "timestamp": now.isoformat(),
    }

    # Broadcast to current user's SSE payment/bank stream
    await publish_event(
        event_type=event_name,
        data=event_payload,
        customer_id=str(user_id),
        event_id=f"evt_{txn_id}",
    )

    logger.info(
        "Emitted simulated bank %s: user=%s, txn_id=%s, amount=%s, app=%s",
        resolved_dir,
        user_id,
        txn_id,
        amount_dec,
        template["app"],
    )
    return event_payload


class BankStreamSimulatorManager:
    """
    Manages background simulation tasks per authenticated user.
    Enables starting/stopping an automatic producer loop that emits credits every N seconds.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._stats: dict[str, dict[str, Any]] = {}

    def is_running(self, user_id: uuid.UUID) -> bool:
        uid = str(user_id)
        task = self._tasks.get(uid)
        return bool(task and not task.done())

    def get_status(self, user_id: uuid.UUID) -> dict[str, Any]:
        uid = str(user_id)
        running = self.is_running(user_id)
        stats = self._stats.get(uid, {})
        return {
            "is_running": running,
            "interval_seconds": stats.get("interval_seconds", 10),
            "emitted_count": stats.get("emitted_count", 0),
            "last_emitted_at": stats.get("last_emitted_at"),
        }

    async def _producer_loop(self, user_id: uuid.UUID, interval_seconds: int) -> None:
        uid = str(user_id)
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                async with SessionLocal() as db:
                    payload = await emit_simulated_credit(db, user_id, direction="AUTO")
                    stats = self._stats.setdefault(
                        uid,
                        {
                            "interval_seconds": interval_seconds,
                            "emitted_count": 0,
                            "last_emitted_at": None,
                        },
                    )
                    stats["emitted_count"] += 1
                    stats["last_emitted_at"] = payload["timestamp"]
        except asyncio.CancelledError:
            logger.info("Bank simulator producer loop stopped for user %s", user_id)
            raise
        except Exception:
            logger.exception("Error in bank simulator loop for user %s", user_id)

    def start(self, user_id: uuid.UUID, interval_seconds: int = 10) -> dict[str, Any]:
        uid = str(user_id)
        if self.is_running(user_id):
            return self.get_status(user_id)

        # Initialize/reset stats
        self._stats[uid] = {
            "interval_seconds": interval_seconds,
            "emitted_count": self._stats.get(uid, {}).get("emitted_count", 0),
            "last_emitted_at": self._stats.get(uid, {}).get("last_emitted_at"),
        }

        task = asyncio.create_task(
            self._producer_loop(user_id, interval_seconds),
            name=f"bank-sim-{uid}",
        )
        self._tasks[uid] = task
        logger.info("Started bank simulator producer for user %s (interval=%ds)", user_id, interval_seconds)
        return self.get_status(user_id)

    def stop(self, user_id: uuid.UUID) -> dict[str, Any]:
        uid = str(user_id)
        task = self._tasks.pop(uid, None)
        if task and not task.done():
            task.cancel()
        logger.info("Stopped bank simulator producer for user %s", user_id)
        return self.get_status(user_id)


# Global singleton instance
simulator_manager = BankStreamSimulatorManager()
