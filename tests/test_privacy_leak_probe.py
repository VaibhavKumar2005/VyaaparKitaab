"""
Privacy / leakage probe.

Runs against the real app with REAL JWT logins (no dependency overrides) for two
independent accounts. A "canary" string planted in account A's data must never appear
in any response served to account B or to an anonymous caller, in application logs,
or in error bodies.
"""
from __future__ import annotations

import logging
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.database import SessionLocal, engine
from app.cores.log_redaction import RedactingFilter, redact_text
from app.cores.rate_limit import reset_rate_limits_async
from app.main import app
from app.models.banking_consent import BankTransaction

# Anonymous GET endpoints that are intentionally public (no user data).
PUBLIC_GET_ALLOWLIST = {
    "/",
    "/api/v1/health",
    "/api/v1/health/db",  # liveness probe: SELECT 1 only, returns no data
    "/api/v1/auth/otp/status",
    "/api/v1/banking/sample-statement.pdf",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}


async def _register(client: httpx.AsyncClient, tag: str) -> tuple[dict[str, str], str, str]:
    phone = f"96{uuid4().int % 10**8:08d}"
    email = f"{tag}_{uuid4().hex[:8]}@leakprobe.in"
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Pr0be!Passw0rd#1",
            "full_name": f"Probe {tag}",
            "phone": phone,
            "role": "STORE_OWNER",
        },
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, phone, email


def _public_get_paths(schema: dict) -> list[str]:
    paths = []
    for path, ops in schema["paths"].items():
        # SSE endpoints never terminate; they are probed separately (auth only) below.
        if "get" in ops and "{" not in path and not path.startswith("/api/v1/streams"):
            paths.append(path)
    return sorted(paths)


def test_log_redaction_scrubs_otp_phone_and_tokens():
    sample = "127.0.0.1 - POST /api/v1/auth/otp/verify?phone=9876543210&otp=842913&purpose=LOGIN HTTP/1.1 200"
    out = redact_text(sample)
    assert "842913" not in out and "9876543210" not in out
    assert "purpose=LOGIN" in out

    rec = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "POST", "/auth/otp/verify?phone=9876543210&otp=842913", "1.1", 200), None,
    )
    assert RedactingFilter().filter(rec) is True
    assert "842913" not in rec.getMessage() and "9876543210" not in rec.getMessage()
    assert "Bearer [REDACTED]" in redact_text("Authorization: Bearer abc.def.ghi")


@pytest.mark.anyio
async def test_static_123456_otp_backdoor_closed_outside_testing(monkeypatch):
    from app.cores.config import settings
    from app.services import otp as otp_mod

    async with SessionLocal() as db:
        monkeypatch.setattr(settings, "ENV", "development")
        assert await otp_mod.check_otp_code(db, f"95{uuid4().int % 10**8:08d}", "123456", "LOGIN") is False
        monkeypatch.setattr(settings, "ENV", "production")
        assert await otp_mod.check_otp_code(db, f"95{uuid4().int % 10**8:08d}", "123456", "LOGIN") is False
    await engine.dispose()


@pytest.mark.anyio
async def test_cross_tenant_anonymous_log_and_error_leak_probe(caplog):
    await engine.dispose()
    await reset_rate_limits_async()
    canary_name = f"CANARYZEBRA{uuid4().hex[:6].upper()}"
    canary_vpa = f"{canary_name.lower()}@okaxis"
    csv_text = (
        "Txn Date,Narration,Debit,Credit\n"
        f"2026-11-15,UPI/CR/445566778899/{canary_name}/Secret Salary/{canary_vpa},,48000.00\n"
        f"2026-11-16,UPI/DR/112233445566/{canary_name} Clinic/Private Medical/OKICICI,3200.00,\n"
    )

    caplog.set_level(logging.DEBUG)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        a_hdr, a_phone, a_email = await _register(client, "owner_a")
        b_hdr, _b_phone, _b_email = await _register(client, "owner_b")

        # --- A loads personal data containing the canary
        imp = await client.post(
            "/api/v1/banking/import-statement",
            headers=a_hdr,
            json={"filename": "private.csv", "content": csv_text},
        )
        assert imp.status_code == 200, imp.text
        a_view = await client.get("/api/v1/banking/personal-spending", headers=a_hdr)
        assert canary_name in a_view.text, "sanity: owner A must see own data"

        schema = (await client.get("/openapi.json")).json()
        get_paths = _public_get_paths(schema)
        assert len(get_paths) >= 10

        # --- 1. Anonymous callers: every GET must be 401/403 unless allow-listed
        anon_open: list[str] = []
        for p in get_paths:
            r = await client.get(p)
            assert canary_name not in r.text
            if r.status_code == 200 and p not in PUBLIC_GET_ALLOWLIST:
                anon_open.append(p)
        assert not anon_open, f"Unauthenticated endpoints returning 200: {anon_open}"

        # --- 2. Account B: no endpoint may ever return A's canary, and nothing may 5xx
        for p in get_paths:
            r = await client.get(p, headers=b_hdr)
            assert r.status_code < 500, f"{p} -> {r.status_code}"
            assert canary_name not in r.text, f"CROSS-TENANT LEAK via GET {p}"
            assert a_phone not in r.text and a_email not in r.text, f"PII of A leaked via GET {p}"

        # --- 3. B cannot destroy A's data
        await client.delete("/api/v1/banking/transactions", headers=b_hdr)
        async with SessionLocal() as db:
            n = (
                await db.execute(
                    select(func.count()).select_from(BankTransaction).where(BankTransaction.narration.contains(canary_name))
                )
            ).scalar_one()
        assert n == 2, "Account B's DELETE removed Account A's transactions"

        # --- 4. Forged / garbage tokens are rejected
        for bad in ("Bearer null", "Bearer abc.def.ghi", "Bearer " + "A" * 300, "Basic YTpi"):
            r = await client.get("/api/v1/banking/personal-spending", headers={"Authorization": bad})
            assert r.status_code == 401

        # --- 4b. SSE streams: anonymous/forged rejected, and B cannot open A's store stream
        for stream_path in ("/api/v1/streams/payments", f"/api/v1/streams/store/{uuid4()}"):
            assert (await client.get(stream_path)).status_code == 401
            assert (
                await client.get(stream_path, headers={"Authorization": "Bearer abc.def.ghi"})
            ).status_code == 401
        biz = await client.post(
            "/api/v1/businesses",
            headers=a_hdr,
            json={"name": "Probe Store A", "gstin": "27AABCN1234E1Z5", "address": "Private Lane 1", "phone": a_phone},
        )
        assert biz.status_code == 200, biz.text
        foreign_stream = await client.get(f"/api/v1/streams/store/{biz.json()['id']}", headers=b_hdr)
        assert foreign_stream.status_code == 403, "Owner B could open Owner A's live store stream"
        biz_b_view = await client.get("/api/v1/businesses", headers=b_hdr)
        assert "Private Lane 1" not in biz_b_view.text and a_phone not in biz_b_view.text

        # --- 5. Error bodies must not expose stack traces / server paths / SQL
        probes = [
            client.post("/api/v1/banking/import-statement", headers=a_hdr, json={"filename": "x.csv", "content": "\x00\x01garbage"}),
            client.post("/api/v1/payments/verify", headers=a_hdr, json={"invoice_id": "not-a-uuid"}),
            client.post("/api/v1/auth/login", json={"email": "nobody@leakprobe.in", "password": "x"}),
            client.get("/api/v1/invoices/00000000-0000-0000-0000-000000000000", headers=b_hdr),
        ]
        for coro in probes:
            r = await coro
            body = r.text
            for needle in ("Traceback", "/home/", "site-packages", "sqlalchemy", "asyncpg", "SELECT ", "INSERT "):
                assert needle not in body, f"error body leaks '{needle}' ({r.status_code})"

        # --- 6. Security headers present
        h = (await client.get("/api/v1/health")).headers
        assert h.get("x-content-type-options") == "nosniff"
        assert h.get("x-frame-options") == "DENY"
        assert "frame-ancestors 'none'" in h.get("content-security-policy", "")

        # --- 7. OTP flow must not log the code or the raw phone number
        otp = await client.post(f"/api/v1/auth/otp/send?phone={a_phone}&purpose=LOGIN")
        assert otp.status_code == 200
        code = otp.json().get("dev_otp")
        if code:
            await client.post(f"/api/v1/auth/otp/verify?phone={a_phone}&otp={code}&purpose=LOGIN")

    # --- Log scan (everything captured at DEBUG across the whole probe)
    log_blob = "\n".join(rec.getMessage() for rec in caplog.records)
    forbidden = {
        "canary narration": canary_name,
        "canary vpa": canary_vpa,
        "owner A raw phone": a_phone,
        "owner A raw email": a_email,
        "password": "Pr0be!Passw0rd#1",
        "bearer token": "eyJ",
    }
    if code:
        forbidden["otp code"] = f"otp={code}"
    leaked = {label: needle for label, needle in forbidden.items() if needle in log_blob}
    assert not leaked, f"Sensitive data present in application logs: {list(leaked)}"

    await engine.dispose()
