-- The only schema definition (AD-7). Applied at startup; idempotent.
-- Money is INTEGER cents (AD-3). Later stories add their own tables here.

CREATE TABLE IF NOT EXISTS products (
    sku  TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    sku     TEXT PRIMARY KEY REFERENCES products (sku),
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id       TEXT PRIMARY KEY,
    customer_email TEXT NOT NULL,
    status         TEXT NOT NULL
                   CHECK (status IN ('placed', 'shipped', 'delivered', 'cancelled')),
    placed_on      TEXT NOT NULL,
    delivered_on   TEXT,
    CHECK ((status = 'delivered') = (delivered_on IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS order_lines (
    line_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         TEXT NOT NULL REFERENCES orders (order_id),
    sku              TEXT NOT NULL REFERENCES products (sku),
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0)
);

CREATE TABLE IF NOT EXISTS returns (
    return_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     TEXT NOT NULL REFERENCES orders (order_id),
    reason       TEXT,
    refund_cents INTEGER NOT NULL CHECK (refund_cents >= 0),
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS return_lines (
    return_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id      INTEGER NOT NULL REFERENCES returns (return_id),
    line_id        INTEGER NOT NULL REFERENCES order_lines (line_id),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    refund_cents   INTEGER NOT NULL CHECK (refund_cents >= 0)
);

-- Append-only audit trail (AD-5). Only AuditRepository.record inserts here.
CREATE TABLE IF NOT EXISTS audit_entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    action       TEXT NOT NULL CHECK (action IN
                 ('ORDER_LOOKUP', 'RETURN_REQUESTED', 'REFUND_CALCULATED', 'RESTOCK_APPLIED')),
    outcome      TEXT NOT NULL CHECK (outcome IN ('success', 'rejected', 'not_found')),
    order_id     TEXT,
    masked_email TEXT,
    details      TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_entries_no_update
BEFORE UPDATE ON audit_entries
BEGIN
    SELECT RAISE(ABORT, 'audit_entries is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_entries_no_delete
BEFORE DELETE ON audit_entries
BEGIN
    SELECT RAISE(ABORT, 'audit_entries is append-only');
END;
