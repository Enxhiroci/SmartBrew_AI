# Task B — Selection and Requirements Traceability

**Source of truth:** the uploaded *SmartBrew AI — Software Specification & Agile Planning*, Lab 2 Task 2b (nine pages), and three uploaded UML diagrams (use case, component, class). This implementation prioritizes selected Lab 2 features; not every UML actor or external interface is implemented.

| Implemented feature | User story | Requirement | Original backlog | Evidence in implementation | Automated test |
|---|---|---|---|---|---|
| Menu with stock-aware availability, category, price, kcal | US01 | R01 | PB01 | `GET /api/catalog`; Discover menu | `test_01_menu_category_nutrition_and_prices` |
| Drink customization and price/ingredient validation | US02 | R02 | PB02 | `POST /api/quote`; customization panel | `test_02_customization_validates_and_calculates_stock` |
| Place paid simulated order; preparation states and counters | US03 | R03 | PB03 | `POST /api/orders`, automatic timed order status via `GET /api/orders/{id}` | `test_03_order_preparation_state_and_single_deduction` |
| Three simulated payment choices with method-specific fields, masked details, scannable QR + PDF receipts, optional real SMTP email, declined path | US04 | R04 | PB04 | Checkout, receipt preview/email send and delivery status, payment-denial audit | `test_04_payment_denial_and_receipt_options` |
| Registration and email/password sign-in | US06 | R06 | PB06 | `/api/register`, `/api/login`, `/api/me` | `test_05_registration_login_and_bad_password` |
| Preferences, saved named recipes and editing | US07 | R07 | PB07 | `/api/preferences`, `/api/recipes` | `test_06_persistent_preferences_and_named_recipes` |
| Contextual recommendations using manual weather/mood, time and profile/history | US10 | R10 | PB10 | `POST /api/recommendations`, explanation cards | `test_07_context_changes_recommendation_ranking` |
| Technician PIN and role protection | US13 | R13 | PB13 | `/api/admin/login` and admin-only endpoints | `test_08_admin_pin_and_role_protection` |
| Stock, fault, waste monitoring and order blocking | US14 | R14 | PB14 | `/api/admin/status`; demo faults/waste simulation | `test_09_monitoring_stock_waste_and_fault_blocks_sales` |
| Admin ingredient refills and waste-bin reset | US15 | R15 | PB15 | `/api/admin/ingredients/{name}/refill`, `/api/admin/bin/empty` | `test_10_technician_refill_bin_reset_permissions` |

## Core behavioral invariants

- No confirmed simulated order is created if its payment simulator reports declined.
- No confirmed simulated order is created if required ingredients, waste capacity or machine health block preparation.
- Successful creation decrements the required ingredients *exactly once*.
- Automatic simulated brewing state transitions **never** decrement stock a second time.
- Guest orders are retrievable by an opaque tracking token; logged-in owners can also retrieve their own order.
- Customers cannot access technician inventory endpoints; technician sessions cannot place customer orders.
- Named recipes are scoped to the current logged-in customer.
- Saving or renaming a recipe does not create a payment or an order.
- Registered customers see only their own order history; guest orders are tracked separately by opaque access tokens.
- Opening a saved recipe/repeat order copies customization into a NEW checkout; it does not silently submit payment.
- Preference defaults are used for new drink selections; historical orders do not overwrite explicit saved preferences.
- Demonstration environment signals are manual values and simulated counters, not actual hardware readings.

## Specification features not claimed as implemented

These belong to the broader Lab 2 specification/diagrams and **are not included** in the Task B ten-feature selection: R05 offline service continuity, R08 *direct single-click purchase* from a saved recipe (this prototype instead loads a saved recipe into a new payment checkout), R11 camera-based mood analysis and frame disposal, R12 natural-language LLM drink agent, and R16 remote diagnostic log transmission. Likewise, NFC identification, physical coffee-machine actuator, a live weather API, genuine card/employee payment rails, and payment-terminal integration and externally verified QR receipts are not integrated. Email delivery is optional via configurable TLS SMTP (not a payment service). Their absence is **not** hidden by the simulated experiences.

## Additional end-to-end customer flows (beyond the ten selected feature groups)

- **R08 partial:** My saved drinks → Place as new order → existing options are copied into a new checkout; customer confirms simulated payment explicitly.
- **R09 implemented:** `/api/my/orders` returns up to 100 newest customer-owned purchases, including configurations and payment status; guest and other-customer histories are excluded.
- **R10 improved:** prior order frequencies affect explainable recommendation scores; user-controlled defaults are never silently rewritten by previous orders.
- The UI exposes **Save to My Dashboard** and **Place as a new order** as two separate actions immediately after customization, avoiding the prior ambiguous save/checkout flow.
