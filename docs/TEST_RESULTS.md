# Lab 3 — Task B Test Verification

**Test command:** `python -m pytest -q --disable-warnings`  
**Environment used for verification:** Python 3.13.5; FastAPI 0.128.2; pytest 9.0.2; Pydantic 2.13.5; httpx 0.28.1.  
**Isolation:** Every pytest test gets a new temporary SQLite database via `tests/conftest.py`.

## Feature verification

| Test | Result | Requirement |
|---|---|---|
| `test_01_menu_category_nutrition_and_prices` | PASS | R01 |
| `test_02_customization_validates_and_calculates_stock` | PASS | R02 |
| `test_03_order_preparation_state_and_single_deduction` | PASS | R03 |
| `test_04_payment_denial_and_receipt_options` | PASS | R04 |
| `test_05_registration_login_and_bad_password` | PASS | R06 |
| `test_06_persistent_preferences_and_named_recipes` | PASS | R07 |
| `test_07_context_changes_recommendation_ranking` | PASS | R10 |
| `test_08_admin_pin_and_role_protection` | PASS | R13 |
| `test_09_monitoring_stock_waste_and_fault_blocks_sales` | PASS | R14 |
| `test_10_technician_refill_bin_reset_permissions` | PASS | R15 |

**Updated pytest result:** `35 passed` after payment-details and QR receipt improvements (October 25, 2026).  
**New regression coverage:** `tests/test_receipts_and_progress.py` verifies automatic queue/brew/ready progression without manual buttons; complete receipt data; validated recipient addresses; SMTP-not-configured behavior; failure/retry and no duplicate inventory changes; mocked STARTTLS message construction and content; and ensures preview-only email never invokes SMTP, requires a valid recipient and cannot be retried as real email. No real email is sent by automated tests.

**New customer journey regression tests:** `tests/test_customer_dashboard_flow.py` verifies saving/editing named recipes does not create an order, account-specific purchases appear in descending history, guest and other-customer orders do not appear in that history, saved preference values stay separate from order history, and recommendations recognize repeat-order frequency. A separate Chromium **static-DOM smoke test with mocked fetch responses** verified the visible customer flow (prefill → save recipe → edit name → new checkout → order history). This mock does not constitute a complete browser-to-backend test.

**Known test limitation:** These are API-level functional tests. The frontend JavaScript passed `node --check frontend/app.js`, and an HTML/JavaScript element-ID consistency check found no missing references. Automated browser navigation was restricted by the execution environment, so **browser end-to-end interaction is not claimed as verified**. This is not an exhaustive browser compatibility or physical device test. Email is tested against a mocked SMTP transport; real SMTP acceptance and inbox delivery must be verified manually with your own account. Payment, weather, camera and brewing hardware are simulated or absent.

## Review trace

The first test pass identified `PAYMENT_DECLINED` audit events disappearing on transaction rollback and a missing recipe-update endpoint. Those failures were used to improve the implementation and confirm the corrections in a subsequent test run. This is an example of evaluating LLM-generated software rather than accepting it without verification.

**Payment and QR regression:** `test_payment_details_qr.py` checks bank brand/masked sample digits, Google Pay confirmation, employee-card demo PIN rejection, simulated payment description visibility in PDFs, a true protected PNG QR endpoint, conditional QR availability, one-page itemized QR PDF, and frontend method-specific inputs. The QR PNG and a JPEG rendered from the PDF were decoded successfully with an independent QR scanner during manual artifact validation. No real payments were attempted.
