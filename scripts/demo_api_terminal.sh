#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=================================================================="
echo " 1. HEALTH CHECK (FastAPI + PostgreSQL)"
echo "=================================================================="
curl -sS "$BASE_URL/api/v1/health/db" | python3 -m json.tool

echo ""
echo "=================================================================="
echo " 2. MERCHANT LOGIN (POST /api/v1/auth/login -> JWT Token)"
echo "=================================================================="
TOKEN_JSON=$(curl -sS -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@vyapaarkitaab.in","password":"Password123!"}')
echo "$TOKEN_JSON" | python3 -m json.tool
TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo ""
echo "=================================================================="
echo " 3. OTP DISPATCH & VERIFICATION (POST /api/v1/auth/otp/send & verify)"
echo "=================================================================="
OTP_JSON=$(curl -sS -X POST "$BASE_URL/api/v1/auth/otp/send?phone=9876543210&purpose=LOGIN")
echo "$OTP_JSON" | python3 -m json.tool
OTP_CODE=$(echo "$OTP_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dev_otp','123456'))")

curl -sS -X POST "$BASE_URL/api/v1/auth/otp/verify?phone=9876543210&otp=$OTP_CODE&purpose=LOGIN" | python3 -m json.tool

echo ""
echo "=================================================================="
echo " 4. IMPORT REAL GPAY / BANK STATEMENT CSV INTO POSTGRESQL"
echo "    (POST /api/v1/banking/import-statement)"
echo "=================================================================="
PAYLOAD=$(python3 -c "
import json
from pathlib import Path
csv_text = Path('data/real_gpay_and_bank_statement.csv').read_text()
print(json.dumps({'filename': 'real_gpay_and_bank_statement.csv', 'content': csv_text}))
")
curl -sS -X POST "$BASE_URL/api/v1/banking/import-statement" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" | python3 -m json.tool

echo ""
echo "=================================================================="
echo " 5. PERSONAL SPENDING & UPI ANALYTICS FROM POSTGRESQL"
echo "    (GET /api/v1/banking/personal-spending)"
echo "=================================================================="
curl -sS "$BASE_URL/api/v1/banking/personal-spending" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(json.dumps({
    'has_imported_data': d['has_imported_data'],
    'total_spent': d['total_spent'],
    'total_received': d['total_received'],
    'debits_count': d['debits_count'],
    'credits_count': d['credits_count'],
    'category_breakdown': d['category_breakdown'],
    'app_breakdown': d['app_breakdown'],
    'sample_transactions': d['transactions'][:3]
}, indent=2))
"

echo ""
echo "=================================================================="
echo " 6. ACCOUNT AGGREGATOR INWARD CREDITS STREAM"
echo "    (GET /api/v1/banking/income-stream)"
echo "=================================================================="
curl -sS "$BASE_URL/api/v1/banking/income-stream" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(json.dumps({
    'is_connected': d['is_connected'],
    'total_inward_income': d['total_inward_income'],
    'total_credits_count': d['total_credits_count'],
    'category_breakdown': d['category_breakdown'],
    'recent_inflows': d['recent_inflows'][:3]
}, indent=2))
"

echo ""
echo "=================================================================="
echo " 7. GPAY / UPI PAYMENT SUMMARY (GET /api/v1/payments/summary?period=30d)"
echo "=================================================================="
curl -sS "$BASE_URL/api/v1/payments/summary?period=30d" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=================================================================="
echo " 8. LIVE ACCOUNT AGGREGATOR DEMO STREAM (EMIT & STATUS)"
echo "    (POST /api/v1/banking/demo-stream/emit)"
echo "=================================================================="
echo "Emitting 1 real-time verified UPI credit event into PostgreSQL & SSE:"
curl -sS -X POST "$BASE_URL/api/v1/banking/demo-stream/emit" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "Stream Producer Status (GET /api/v1/banking/demo-stream/status):"
curl -sS "$BASE_URL/api/v1/banking/demo-stream/status" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

