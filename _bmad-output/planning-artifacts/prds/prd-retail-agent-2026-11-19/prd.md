---
title: retail-agent PRD
status: draft
created: 2026-11-19
updated: 2026-11-19
---

# PRD: Retail Returns Assistant (`retail-agent`)

## 0. Document Purpose
This PRD defines what the Retail Returns Assistant must do. It is the input for architecture and for the epic and story breakdown. It is scoped to its real purpose: a **learning and demo project for a developer lab**. The primary input is `docs/brief.md`. Technology and delivery constraints from the brief are in `addendum.md`. Terms in §3 are used exactly as defined. Inferred decisions are tagged `[ASSUMPTION]` inline and collected in §8.

## 1. Vision
The Retail Returns Assistant is a small REST service. A customer can look up an order, see its status, and return items within 30 days of delivery. The service then works out the refund, puts the returned stock back into inventory, and records every action in an audit trail.

It is not a real commerce system. Orders, payments and the warehouse are all mock data in a local database. What it offers is a realistic, self-contained domain with real business rules: a time window, quantity limits, money calculations and an append-only log. That gives lab participants something worth designing, testing and shipping with good engineering practice.

Despite the `agent` name, there is no AI or conversational component.

## 2. Target User

### 2.1 Jobs To Be Done
- **Customer (API caller):** check where my order is, and return something without arguing about whether I'm still eligible.
- **Lab participant (builder):** practise building a well-tested, containerised API with clear business rules, from PRD to CI.
- **Lab facilitator:** have a reference app that runs the same on every machine and shows good practice (tests, pinned dependencies, no secrets).

### 2.2 Key User Journeys
- **UJ-1. Asha returns a cracked mug.** Asha's order was delivered 12 days ago. She looks it up with her order ID and email, sees that both mugs can still be returned, and requests a return for one of them. She gets back a confirmed return with her refund amount. The mug's inventory count goes up by one.
- **UJ-2. Ben is too late.** Ben's order was delivered 41 days ago. When he looks it up, it shows that the return window closed on day 30. If he submits a return anyway, it is rejected with a clear reason. Nothing is refunded or restocked, but the rejected attempt still appears in the audit trail.
- **UJ-3. Ravi runs the lab.** Ravi clones the repo and starts the service with one command, either locally or in Docker. He opens the API docs, uses the seeded mock orders to try UJ-1 and UJ-2, and then reads the audit trail to see what happened.

## 3. Glossary
- **Customer** — The person who placed an Order. Identified only by the email on the Order; there are no accounts.
- **Order** — A purchase with a unique order ID, customer email, Order Status, delivery date (once delivered) and one or more Order Lines.
- **Order Line** — One Product on an Order, with the quantity purchased and the unit price paid.
- **Order Status** — One of `placed`, `shipped`, `delivered`, `cancelled`.
- **Product** — A sellable item with a SKU and an Inventory count.
- **Inventory** — The on-hand quantity of a Product in the mock stock store.
- **Return Window** — The 30 days after an Order's delivery date, with day 30 included.
- **Return** — An accepted request to send back one or more quantities of Order Lines. Each Return carries one Refund.
- **Returnable Quantity** — The quantity purchased on an Order Line minus the quantity already returned.
- **Refund** — The money owed for a Return, as worked out by the Refund rules. It is recorded, not paid out.
- **Restock** — Adding a Return's quantities back to Inventory.
- **Audit Entry** — An append-only record of one action: time, action type, Order ID, outcome, and details.

## 4. Features

### 4.1 Order Lookup
**Description:** A Customer finds an Order by giving its order ID and the email on it. If the pair doesn't match, the response is "not found", so callers can't probe which order IDs exist. Realises UJ-1, UJ-2. `[ASSUMPTION: order ID + email is the only identity check; no login.]`

#### FR-1: Look up an Order
A Customer can retrieve an Order by order ID and email.
- If the ID and email match, the response contains the Order Status, the Order Lines, the delivery date (if any) and the order total.
- If the ID is unknown or the email does not match, the response is the same "not found" in both cases.
- Matching the email ignores letter case. `[ASSUMPTION]`

#### FR-2: Show return eligibility
The lookup response tells the Customer whether they can return anything.
- It includes the Return Window end date and whether the Order is currently returnable.
- Each Order Line shows its Returnable Quantity.
- Any Returns already made on the Order are listed with their Refunds.

### 4.2 Returns
**Description:** A Customer asks to return chosen quantities of one or more Order Lines. Since there is no real warehouse, an eligible request is accepted straight away: the Return is created, the Refund is worked out, the Restock is applied and Audit Entries are written, all in one step. `[ASSUMPTION: no separate "item received" step.]` Realises UJ-1, UJ-2.

#### FR-3: Request a Return
A Customer can submit a return request with the order ID, email, and a list of Order Lines with quantities. A reason is optional.
- An eligible request creates exactly one Return and responds with the Return and its Refund.
- Multiple partial Returns on the same Order are allowed, as long as each one fits within the Returnable Quantity. `[ASSUMPTION]`

#### FR-4: Enforce eligibility rules
The system rejects a return request, with a specific reason, if any of these is true:
- The Order Status is not `delivered`.
- The request falls after day 30 of the Return Window. Day 30 itself is accepted; day 31 is rejected.
- A requested quantity is zero or less, or more than the line's Returnable Quantity.
- An Order Line in the request is not on the Order.
- The order ID and email do not match, which gets the same "not found" as FR-1.

A rejected request changes nothing except the audit trail.

### 4.3 Refund Calculation
#### FR-5: Work out the Refund
For each returned Order Line, the Refund is unit price paid × quantity returned. The Return's Refund is the sum of those amounts.
- Money is exact to the cent and never uses floating-point rounding.
- There is no restocking fee, no shipping refund and no separate tax handling. Prices are treated as tax-inclusive. `[ASSUMPTION]`
- The Refund is recorded on the Return. No payment is made or simulated beyond that.

### 4.4 Inventory Restock
#### FR-6: Restock returned items
When a Return is accepted, each returned quantity is added to that Product's Inventory.
- Inventory changes only through an accepted Return or through seed data.
- A rejected request leaves Inventory unchanged.

### 4.5 Audit Trail
**Description:** Every action the service takes is recorded, so a lab participant can trace what happened. Realises UJ-3.

#### FR-7: Record every action
Each of these writes an Audit Entry: an Order lookup (found or not found), a return request (accepted or rejected, with the reason), Refund calculated, and Restock applied.
- Audit Entries can only be added. No API can change or delete them.
- An Audit Entry never stores the full customer email. It stores a masked email instead. `[ASSUMPTION]`

#### FR-8: Read the audit trail
A caller can list Audit Entries, newest first, and filter by order ID. `[ASSUMPTION: open endpoint, acceptable only because this is a demo with no auth.]`

### 4.6 Operability
#### FR-9: Health and API docs
- A health endpoint reports that the service is up and its database is reachable.
- Interactive API documentation is served and covers every endpoint.

#### FR-10: Seeded mock data
On first start, the service loads a small, fixed set of Orders. The set covers every Order Status, at least one order inside the Return Window, one past it, and one exactly on day 30. Each lab participant then gets the same scenarios.

## 5. Cross-Cutting Requirements
- **Consistency:** Return creation, Refund, Restock and their Audit Entries all succeed together or all fail together.
- **Testability:** The current date used for Return Window checks can be controlled in tests. Business logic has at least 90% test coverage.
- **Errors:** Errors use one consistent response shape, with a machine-readable code (for example `RETURN_WINDOW_EXPIRED`) and a message a person can read.
- **Hygiene:** There are no secrets in the repo. Dependencies are pinned and scanned. The service runs the same way locally, in Docker and in CI.

## 6. Scope

### 6.1 Non-Goals
- Real payments, a real warehouse, carriers or shipping labels.
- Customer accounts, authentication or admin roles.
- A web or mobile UI. The API docs are the only interface.
- AI or chat features.
- Exchanges, store credit, notifications or emails.
- Production hardening: scaling, uptime targets, multi-tenancy.

### 6.2 Deferred (possible lab extensions)
- Idempotency keys on return requests.
- Return reasons that affect the Refund, such as a fee for "changed mind".
- Authenticated admin access to the audit trail.

## 7. Success Metrics
- **SM-1:** A new participant can go from cloning the repo to running UJ-1 and UJ-2 in under 15 minutes, using only the README. Validates FR-9, FR-10.
- **SM-2:** CI passes on `main`, with at least 90% coverage on business logic. Every FR has at least one test that names it. Validates FR-1 to FR-8.
- **SM-C1 (counter-metric):** Don't push coverage up with tests that assert nothing, or with features beyond this PRD. Keeping the scope small and clear matters more for the lab than a high number. Counterbalances SM-2.

## 8. Assumptions
1. §4.1: Order ID plus email is the only identity check. Email matching ignores letter case.
2. §4.1: An unknown order ID and a wrong email both give the same "not found".
3. §3: The Return Window starts at the delivery date, and day 30 is included. Orders that haven't been delivered can't be returned.
4. §4.2: Returns are accepted straight away with no "item received" step, because the warehouse is mock.
5. §4.2: Partial and repeated Returns are allowed up to the Returnable Quantity.
6. §4.3: Refund = unit price paid × quantity. No fees, no shipping refund, prices tax-inclusive, exact to the cent.
7. §4.5: Audit Entries cover lookups as well as changes, and mask the customer email.
8. §4.5: The audit trail can be read without auth, which is acceptable only for the demo.
9. §4.6: The mock data is a fixed set loaded on first start.

## 9. Open Questions
1. Should looking up an Order count as an "action" for the audit trail? The PRD currently assumes yes. Drop it if it makes the log too noisy for the lab.
2. Does the lab want a deliberate extension exercise, such as idempotency or return fees? If so, should it be named in this PRD or kept in the lab materials?
