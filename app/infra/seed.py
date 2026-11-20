"""Fixed seed data (FR10), loaded only into an empty database.

Delivery dates are offsets from a reference date (the Clock's UTC date at first
start), so the in-window and day-30 scenarios work on a fresh database.
"""

import sqlite3
from datetime import date, timedelta

PRODUCTS: tuple[tuple[str, str, int], ...] = (
    # sku, name, on_hand
    ("MUG-001", "Ceramic mug", 40),
    ("TEE-002", "Cotton t-shirt", 25),
    ("BAG-003", "Canvas tote bag", 30),
    ("LMP-004", "Desk lamp", 10),
)

# order_id, email, status, placed offset (days before ref), delivered offset or None, lines
# lines: (sku, quantity, unit_price_cents)
ORDERS: tuple[tuple[str, str, str, int, int | None, tuple[tuple[str, int, int], ...]], ...] = (
    # UJ-1: delivered 12 days ago, inside the Return Window.
    ("ORD-1001", "asha@example.com", "delivered", 15, 12,
     (("MUG-001", 2, 1250), ("BAG-003", 1, 899))),
    # UJ-2: delivered 41 days ago, past the Return Window.
    ("ORD-1002", "ben@example.com", "delivered", 45, 41, (("TEE-002", 1, 1999),)),
    # Delivered exactly 30 days before the reference date: the last returnable day.
    ("ORD-1003", "chen@example.com", "delivered", 33, 30,
     (("LMP-004", 1, 4500), ("MUG-001", 1, 1250))),
    ("ORD-1004", "dana@example.com", "placed", 1, None, (("BAG-003", 2, 899),)),
    ("ORD-1005", "eli@example.com", "shipped", 3, None, (("TEE-002", 2, 1999),)),
    ("ORD-1006", "fatima@example.com", "cancelled", 10, None, (("LMP-004", 1, 4500),)),
)


def load_seed(conn: sqlite3.Connection, reference_date: date) -> int:
    """Insert the seed set in one transaction if ``orders`` is empty. Returns orders inserted."""
    with conn:  # commits on success, rolls back on any error
        (count,) = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        if count:
            return 0
        conn.executemany(
            "INSERT OR IGNORE INTO products (sku, name) VALUES (?, ?)",
            [(sku, name) for sku, name, _ in PRODUCTS],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO inventory (sku, on_hand) VALUES (?, ?)",
            [(sku, on_hand) for sku, _, on_hand in PRODUCTS],
        )
        for order_id, email, status, placed_ago, delivered_ago, lines in ORDERS:
            delivered_on = (
                None
                if delivered_ago is None
                else (reference_date - timedelta(days=delivered_ago)).isoformat()
            )
            conn.execute(
                "INSERT INTO orders (order_id, customer_email, status, placed_on, delivered_on)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    order_id,
                    email,
                    status,
                    (reference_date - timedelta(days=placed_ago)).isoformat(),
                    delivered_on,
                ),
            )
            conn.executemany(
                "INSERT INTO order_lines (order_id, sku, quantity, unit_price_cents)"
                " VALUES (?, ?, ?, ?)",
                [(order_id, sku, qty, price) for sku, qty, price in lines],
            )
    return len(ORDERS)
