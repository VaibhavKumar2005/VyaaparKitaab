-- =============================================================================
-- VyaparKitaab PostgreSQL Row-Level Security (RLS) & Blind-Index Schema DDL
-- Enforces defense-in-depth multi-tenant isolation at the database layer.
-- =============================================================================

-- 1. Widen PII columns for AES-128 Fernet ciphertext storage (enc_v1:...)
ALTER TABLE businesses ALTER COLUMN gstin TYPE VARCHAR(512);
ALTER TABLE businesses ALTER COLUMN address TYPE VARCHAR(1024);
ALTER TABLE businesses ALTER COLUMN phone TYPE VARCHAR(512);

ALTER TABLE customers ALTER COLUMN phone TYPE VARCHAR(512);
ALTER TABLE customers ALTER COLUMN email TYPE VARCHAR(512);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS phone_hash VARCHAR(64);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS email_hash VARCHAR(64);
CREATE INDEX IF NOT EXISTS ix_customers_phone_hash ON customers (phone_hash);
CREATE INDEX IF NOT EXISTS ix_customers_email_hash ON customers (email_hash);

-- 2. Invoice pending order persistence for gateway/webhook reconciliation
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS pending_order_id VARCHAR(64);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS pending_order_amount NUMERIC(12, 2);
CREATE INDEX IF NOT EXISTS ix_invoices_pending_order_id ON invoices (pending_order_id);

-- 3. Enable Row-Level Security (RLS) on tenant-scoped tables
ALTER TABLE businesses ENABLE ROW LEVEL SECURITY;
ALTER TABLE personal_purchases ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS businesses_tenant_isolation ON businesses;
CREATE POLICY businesses_tenant_isolation ON businesses
    USING (
        current_setting('app.current_user_id', true) IS NULL
        OR current_setting('app.current_user_id', true) = ''
        OR owner_id::text = current_setting('app.current_user_id', true)
    );

DROP POLICY IF EXISTS personal_purchases_user_isolation ON personal_purchases;
CREATE POLICY personal_purchases_user_isolation ON personal_purchases
    USING (
        current_setting('app.current_user_id', true) IS NULL
        OR current_setting('app.current_user_id', true) = ''
        OR user_id::text = current_setting('app.current_user_id', true)
    );

