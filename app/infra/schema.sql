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
