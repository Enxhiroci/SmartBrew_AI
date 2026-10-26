# Task B — Design Decisions, Critical Evaluation and Gaps

## Architecture

The supplied UML component diagram distinguishes the UI, mood detection, recommendation engine (preference and context subcomponents), beverage management, payment, user/profile management, local agent, sensor data, inventory, and technician administration. The Task B prototype follows the main separation in software, but a browser UI and one modularized-by-function FastAPI file replace separate deployed services. SQLite represents database persistence, user profiles, ingredient counters, recipes, payments and events. Real hardware and partner services are explicitly out of scope.

The supplied UML use-case diagram also has guest, user and admin roles. This prototype retains guests, authenticated customers and protected technicians. The implemented authorization boundary is on server endpoints; it does not depend on whether a menu tab is visible.

The class diagram shows `Person`, `User`, `Admin`, `PreferenceProfile`, `Order`, `Beverage`, `Recommendation`, `Transaction`, `PaymentMethod`, `CoffeeMachine`, `Bin`, and `Ingredient`. The database contains analogous rows (`users`, `orders`, `drinks`, `ingredients`, `machine`), but does not mirror every UML class into a 1:1 Python class. This was intentional: SQLite records model persistence while Pydantic input models validate API traffic.

## Important implementation choices

1. **One-page kiosk / API separation.** CSS/JS runs in a normal browser; FastAPI checks current stock, pricing and authorization. Client-side controls never determine the trustworthy amount or ingredient deduction.
2. **Transactional simulated ordering.** `BEGIN IMMEDIATE` locks writes before availability checks and inventory changes. The payment outcome is explicitly a simulator. Declined payments produce an audit entry but not an order or stock change.
3. **Stateful simulated preparation.** The order status advances automatically from queued to brewing at 3 seconds and ready at 12 seconds since order creation. The browser polls a protected order endpoint; the backend derives state from persisted timestamps (so it also works after a browser refresh). It is not a motor/controller integration.
4. **Stock-aware safety restrictions.** Active faults and waste-capacity thresholds prevent checkout. Admin replenishment/reset restores availability if no other problem exists.
5. **Role separation.** Customer tokens and technician tokens are distinct, expire after eight hours, and are stored hashed in the local database. Passwords/PINs are salted and hashed.
6. **Recommendations are explainable rules.** Weather and mood are manually selected; preferences and recent orders can affect scores. This reliably demonstrates the requirement's *ranking behavior* without misrepresenting a trained model or integrating a private camera feed. It only partially covers the full R10 envisioned implementation.
7. **Saved recipes can be reused and edited.** A saved recipe can populate the customizer; users can change and update it. One-click direct ordering (the separate R08 requirement) remains unimplemented.

## Critical limitations against full requirements

| Original requirement or concern | Prototype result | Limitation / rationale |
|---|---|---|
| R03 machine preparation | Simulated states | No machine SDK, hardware or actuator is provided. Demo is an honest software model of the workflow. |
| R04 payment options and receipts | Three selectable **mock** methods with method-specific non-sensitive fields; real QR PNG and PDF receipts | No real gateway, POS terminal or externally hosted QR verification. The QR encodes an offline demo receipt summary. Optional SMTP sends **real emails** when configured, but the payment on them is still simulated. Real transactions would require merchant integration and security controls. |
| R06 NFC login | Email/password only | No NFC reader or card provisioning was supplied; physical-device integration outside this standalone prototype. |
| R10 recommendation context | Deterministic score using manual weather/mood, time, saved preferences and last order | No weather API, trained recommendation model or actual sensor-based mood inference. Current clock time is not used. |
| R13 secured admin mode | Password-hashed PIN | Technician keys/NFC master cards are not supported. No rate limiting; not ready for public deployment. |
| R14 machine status | DB-based simulator | Values are simulated rather than transmitted from actual sensors. Alerts require manual refresh in technician console. |
| R15 physical refills | Technician records event/counter | Changing software counters does not physically refill a machine. |
| NFRs from Task A | Input validation, role checks, salted password storage, atomicity, basic responsive design | Full privacy/security/performance compliance has **not** been certified; evaluation requires more tests. |

## Risks / later work

Introduce dedicated SMTP delivery queues and retry monitoring (currently bounded and synchronous), hardware adapters for equipment, live context services with timeouts, richer configurable recommendation logic, card/NFC gateways, verified receipts, online/offline reconciliation, order-history page, uploadable fault diagnostics, stronger security (lockout/rate limiting, HTTPS, session revocation and secret configuration), usability/accessibility testing, and proper deployment packaging. Preserve the existing requirement mapping when expanding the prototype.

### Email preview-only mode

The email preview option (`email_preview`) is intentionally separate from `email` (SMTP delivery). Both require an email-looking recipient; only `email` calls `deliver_order_receipt`. The response for preview-only is marked `email_status=preview_only`, with a printable simulated email envelope and transaction summary. Server refuses SMTP retry for preview-only orders. No external email is queued, and no SMTP environment variables are needed.

### Checkout R04 — payment choices and QR receipt update

The UI now shows explicit method-specific mock payment fields rather than only a method dropdown. Backend `describe_simulated_payment` validates safe demo descriptors and stores only masked card suffix/provider/employee badge labels in `orders.payment_description`. A demo employee PIN is compared but never persisted or included in receipts. No genuine payment data or live gateway is accepted. Older SQLite databases gain the new field through migration.

When `receipt_method=qr`, the protected `/api/orders/{id}/receipt-qr.png` route uses qrcode/Pillow to create a real scannable code containing a brief offline receipt summary, excluding order access credentials and personal/contact information. ReportLab embeds the same QR graphic in the downloadable **one-page** PDF. The QR is not an online tax verification page. Other receipt methods retain their distinct email/no-receipt handling. Payment and receipt flows have regression tests under `tests/test_payment_details_qr.py`.
