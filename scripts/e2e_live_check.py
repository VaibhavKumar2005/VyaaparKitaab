"""Live end-to-end check against a running uvicorn (port 8000) and Vite dev server (port 5173).

Exercises the real HTTP stack (including the Vite /api proxy) with fresh real accounts.
"""
from __future__ import annotations

import sys
import time
import uuid
from urllib.parse import urlparse

import httpx

API = "http://127.0.0.1:8000/api/v1"
UI = "http://127.0.0.1:5173"
results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def _csp_allows_https_host(csp_header: str, directive: str, expected_host: str) -> bool:
    for part in csp_header.split(";"):
        tokens = part.strip().split()
        if tokens and tokens[0].lower() == directive.lower():
            for src in tokens[1:]:
                parsed = urlparse(src)
                if parsed.scheme == "https" and parsed.hostname == expected_host:
                    return True
    return False


def wait_up() -> None:
    for _ in range(60):
        try:
            if httpx.get(f"{API}/health", timeout=2).status_code == 200 and httpx.get(UI, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit("stack did not come up")


def main() -> int:
    wait_up()
    tag = uuid.uuid4().hex[:6]
    owner_email = f"owner_{tag}@shop.in"
    owner_phone = f"97{uuid.uuid4().int % 10**8:08d}"
    cust_phone = f"98{uuid.uuid4().int % 10**8:08d}"

    # UI + proxy
    check("UI index served", "<div id=\"root\">" in httpx.get(UI).text or "root" in httpx.get(UI).text)
    via_proxy = httpx.get(f"{UI}/api/v1/health")
    check("Vite proxy reaches API", via_proxy.status_code == 200, str(via_proxy.status_code))

    # 1. Register real merchant through the proxy (like the browser)
    c = httpx.Client(base_url=f"{UI}/api/v1", timeout=15)
    r = c.post(
        "/auth/register",
        json={"email": owner_email, "password": "Str0ng!Pass1", "full_name": "Nisha Gupta", "phone": owner_phone, "role": "STORE_OWNER"},
    )
    check("Register store owner", r.status_code == 200, str(r.status_code))
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = c.post(
        "/businesses",
        headers=h,
        json={"name": "Nisha Electronics", "gstin": "27AABCN1234E1Z5", "address": "MG Road, Pune", "phone": "9988776655", "upi_vpa": "nisha.pay@okaxis"},
    )
    check("Create business with upi_vpa", r.status_code == 200 and r.json().get("upi_vpa") == "nisha.pay@okaxis", r.text[:120])
    biz = r.json()

    # 2. Honest empty AA state for a brand-new account
    r = c.get("/banking/income-stream", headers=h)
    d = r.json()
    check("New account: AA not falsely connected", r.status_code == 200 and d["is_connected"] is False and d["active_consent"] is None and d["total_credits_count"] == 0)
    r = c.get("/banking/income-graph", headers=h)
    check("New account: income graph honest label", r.status_code == 200 and r.json()["fip_name"] == "No Bank Connected Yet", r.json().get("fip_name", ""))

    # 3. Consent without a phone/VUA must not fabricate 9876543210
    r = c.post("/banking/consent/initiate", headers=h, json={"fip_id": "sbi_yono", "phone": ""})
    check("Consent initiate no longer defaults fake phone", r.status_code in (201, 400, 422), str(r.status_code))

    # 4. Live product / customer / invoice
    prod = c.post("/products", headers=h, json={"name": "LED Bulb 9W", "selling_price": 500, "stock_qty": 20, "business_id": biz["id"]}).json()
    cust = c.post("/customers", headers=h, json={"name": "Suresh Mehta", "phone": cust_phone, "business_id": biz["id"]}).json()
    inv_no = f"INV-{tag}"
    r = c.post(
        "/invoices",
        headers=h,
        json={
            "invoice_number": inv_no,
            "business_id": biz["id"],
            "customer_id": cust["id"],
            "type": "SALE",
            "status": "CONFIRMED",
            "payment_method": "CREDIT",
            "tax_amount": 50,
            "items": [{"product_id": prod["id"], "quantity": 2, "unit_price": 500, "discount": 0}],
        },
    )
    inv = r.json()
    check("Create invoice (real DB)", r.status_code == 200 and inv["total_amount"] == 1050.0, r.text[:150])
    check("Invoice carries real store identity", inv.get("store_name") == "Nisha Electronics" and inv.get("store_gstin") == "27AABCN1234E1Z5" and inv.get("store_upi_vpa") == "nisha.pay@okaxis")
    inv_list = c.get("/invoices", headers=h).json()
    check("Invoice list carries store_name", any(i["id"] == inv["id"] and i["store_name"] == "Nisha Electronics" for i in inv_list))

    # 5. UPI intent + CSP for Razorpay
    r = c.post("/payments/create-order", headers=h, json={"invoice_id": inv["id"]})
    o = r.json()
    check("create-order UPI intent uses store VPA + name", "pa=nisha.pay%40okaxis" in (o.get("upi_intent") or "") and "pn=Nisha%20Electronics" in (o.get("upi_intent") or ""), (o.get("upi_intent") or "")[:100])
    csp = httpx.get(f"{API}/health").headers.get("content-security-policy", "")
    check(
        "CSP allows Razorpay Checkout",
        _csp_allows_https_host(csp, "script-src", "checkout.razorpay.com")
        and _csp_allows_https_host(csp, "frame-src", "checkout.razorpay.com"),
    )

    # 6. Realistic bank CSV with preamble -> import -> reconcile
    csv_text = (
        "HDFC Bank Statement Export\nStatement Date: 01-11-2026 to 18-11-2026\nCustomer Description: Nisha Electronics Current Account\n\n"
        "Txn Date,Narration,Debit,Credit\n"
        "2026-11-15,UPI/CR/445566778899/Suresh Mehta/Bill 105/OKAXIS,,1050.00\n"
        "2026-11-16,UPI/DR/112233445566/Swiggy Order/OKICICI,320.00,\n"
    )
    r = c.post("/banking/import-statement", headers=h, json={"filename": "hdfc.csv", "content": csv_text})
    d = r.json()
    check("CSV with bank preamble imports 2 rows", r.status_code == 200 and d.get("imported_count") == 2 and d.get("credits_count") == 1 and d.get("debits_count") == 1, r.text[:150])
    spend = c.get("/banking/personal-spending", headers=h).json()
    check("No fabricated XXXX-XXXX-4821 account", all(t["masked_acc"] != "XXXX-XXXX-4821" for t in spend["transactions"]))
    inc = c.get("/banking/income-stream", headers=h).json()
    check("Income stream reflects imported credit", inc["total_credits_count"] == 1 and inc["total_inward_income"] == 1050.0)

    sug = c.get("/banking/reconcile/suggestions", headers=h).json()
    check("Reconcile suggests the matching invoice (HIGH)", sug["count"] == 1 and sug["suggestions"][0]["invoice_number"] == inv_no and sug["suggestions"][0]["confidence"] == "HIGH", str(sug)[:150])
    txn_id = sug["suggestions"][0]["txn_id"]
    r = c.post("/banking/reconcile/match", headers=h, json={"txn_id": txn_id, "invoice_id": inv["id"]})
    check("Reconcile match marks invoice PAID", r.status_code == 200 and r.json()["invoice_status"] == "PAID" and r.json()["reconciled"] is True, r.text[:150])
    r2 = c.post("/banking/reconcile/match", headers=h, json={"txn_id": txn_id, "invoice_id": inv["id"]})
    check("Re-matching is rejected (already settled)", r2.status_code == 400, str(r2.status_code))
    check("Suggestions cleared after match", c.get("/banking/reconcile/suggestions", headers=h).json()["count"] == 0)
    check("Invoice persisted as PAID", next(i for i in c.get("/invoices", headers=h).json() if i["id"] == inv["id"])["status"] == "PAID")

    # 7. Security: another merchant cannot reconcile against this invoice
    other = httpx.Client(base_url=f"{API}", timeout=15)
    tok = other.post("/auth/register", json={"email": f"x_{tag}@shop.in", "password": "Str0ng!Pass1", "role": "STORE_OWNER"}).json()["access_token"]
    oh = {"Authorization": f"Bearer {tok}"}
    other.post("/banking/import-statement", headers=oh, json={"filename": "a.csv", "content": csv_text})
    ob = other.get("/banking/reconcile/suggestions", headers=oh).json()
    check("Other tenant sees no suggestions for foreign invoices", ob["count"] == 0)
    r = other.post("/banking/reconcile/match", headers=oh, json={"txn_id": txn_id, "invoice_id": inv["id"]})
    check("Other tenant cannot settle foreign invoice", r.status_code in (403, 404), str(r.status_code))
    r = other.put(f"/businesses/{biz['id']}", headers=oh, json={"upi_vpa": "evil@upi"})
    check("Other tenant cannot edit foreign business", r.status_code == 404, str(r.status_code))

    # 8. Customer passbook sees store identity (OTP login via sandbox code)
    r = c.post(f"/auth/otp/send?phone={cust_phone}&purpose=LOGIN")
    otp = r.json().get("dev_otp")
    check("OTP send (sandbox) returns code", r.status_code == 200 and bool(otp), str(r.status_code))
    r = c.post("/auth/customer/otp-login", json={"phone": cust_phone, "otp": otp})
    check("Customer OTP login", r.status_code == 200)
    ch = {"Authorization": f"Bearer {r.json()['access_token']}"}
    bills = c.get("/portal/my-bills", headers=ch).json()
    mine = [b for b in bills if b["id"] == inv["id"]]
    check("Customer sees store bill with real store name/VPA", len(mine) == 1 and mine[0]["store_name"] == "Nisha Electronics" and mine[0]["store_upi_vpa"] == "nisha.pay@okaxis", str(bills)[:120])
    r = c.get(f"/portal/my-bills/{inv['id']}", headers=ch)
    check("Customer single-bill carries store identity", r.status_code == 200 and r.json().get("store_name") == "Nisha Electronics")

    # 9. Business edit applies to later orders
    r = c.put(f"/businesses/{biz['id']}", headers=h, json={"upi_vpa": "nisha.store@ybl"})
    check("Owner updates UPI VPA", r.status_code == 200 and r.json()["upi_vpa"] == "nisha.store@ybl")

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("FAILED:", *failed, sep="\n  - ")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
