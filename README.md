# SmartBrew AI — Lab 3

**Course:** DVA332 — Software Engineering 1  
**Project:** SmartBrew AI  
**Deliverable:** Lab Assignment 3, Task B 
**LLM assistance:** OpenAI ChatGPT, GPT-6 (assistance in code generation, test generation).  

SmartBrew AI is an **educational smart coffee vending kiosk prototype**. Customers can browse the current menu, configure drinks, order using **simulated** payments, watch automatic simulated preparation, download real PDF receipts, easily start new orders, register, save preferences and named recipes, review private order history, reorder saved drinks, and receive explainable context-sensitive recommendations. A separate PIN-protected technician dashboard handles simulated ingredient levels, waste and faults. The software implements a selected subset of the existing Lab 2 specification, rather than claiming to implement every UML component.

> **Important simulation notice:** No real payment is processed, no coffee is physically made, no weather API is contacted, and no sensor/camera is read. **Receipt previews can be generated without sending any email; real emails are optional through SMTP when configured.** They explicitly identify the payment as simulated. The "AI recommendations" module uses an explainable rule-based scoring algorithm, **not a trained ML model or an LLM**. Weather and mood inputs are manual. Selecting QR generates a real scannable PNG on screen and embeds the same code in the PDF; its content is an offline, non-sensitive demonstration summary, not an internet-hosted verification service. Prices are demonstration amounts in EUR.

## 1. Stack and project layout

- **Python:** 3.12 or 3.13 (tested with Python 3.13.5)
- **Backend:** FastAPI 0.128.2, Uvicorn 0.48.0, Pydantic 2.13.5
- **Database:** SQLite via Python standard library (`sqlite3`)
- **Frontend:** HTML5 + CSS3 + vanilla JavaScript (modern desktop/mobile browser); no Node.js required
- **Tests:** pytest 9.0.2, httpx 0.28.1 / FastAPI TestClient
- **Dependencies:** version pinned in `requirements.txt`; ReportLab generates downloadable PDF receipts; qrcode and Pillow produce real scannable QR graphics; pypdf verifies PDF contents in tests. SMTP credentials are optional and needed only for real receipt email delivery

```
smartbrew-ai/
├── backend/
│   ├── __init__.py
│   ├── main.py            # API, domain services, database, access control
│   ├── receipts.py        # Optional TLS SMTP receipt delivery
│   ├── receipt_pdf.py    # Protected on-demand PDF receipt generation
│   └── qr_receipts.py    # Scannable offline QR receipt summary
├── frontend/
│   ├── index.html         # All four kiosk pages
│   ├── app.js             # Client-side interaction and API requests
│   └── styles.css         # Responsive dashboard layout
├── tests/
│   ├── conftest.py        # Fresh isolated DB per test
│   ├── test_features.py   # Feature-focused acceptance tests
│   ├── test_receipts_and_progress.py  # Automatic brewing and SMTP tests
│   ├── test_pdf_and_repeat.py  # Protected PDF and multiple-order tests
│   ├── test_customer_dashboard_flow.py  # Personalization, saved drinks, history privacy
│   └── test_payment_details_qr.py  # Payment fields, authorization, QR and PDF
├── docs/
│   ├── FEATURE_MAPPING.md
│   ├── IMPLEMENTATION_NOTES.md
│   ├── LLM_INTERACTION_LOG.md
│   └── TEST_RESULTS.md
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 2. Installation and execution

Clone the repo, or unzip the submission, and open a terminal **in the `smartbrew-ai` directory** (the directory containing `requirements.txt`).

### Windows — PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

If Python 3.12 is not installed but Python 3.13 is available, use `py -3.13 -m venv .venv`. Run `py --list` to see installed versions. If PowerShell prevents script activation, run `.venv\Scripts\python -m pip install -r requirements.txt` and `.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` instead.

### Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Then open **http://127.0.0.1:8000/** in a browser. The server creates `smartbrew.db` on first startup, seeds six drinks and eight ingredients, and remembers database changes across restarts. Swagger API reference: **http://127.0.0.1:8000/docs**. Health probe: **http://127.0.0.1:8000/api/health**.

### Configuration

- The technician PIN defaults to **2468**. For a different PIN, set the `SMARTBREW_ADMIN_PIN` environment variable **before first starting with a new database**. This changes the initial seeded PIN, not an existing database's PIN.
- Optional `SMARTBREW_DB_PATH` overrides the database path. Use a separate DB file for experimental runs.
- `.env.example` documents these variables; the backend **automatically loads `.env`** from the project root if it exists. Already-set OS environment variables take precedence.
- The server uses local-only binding (`127.0.0.1`) on purpose; do not deploy this demonstration as an internet-facing payment or vending service.

### Customer dashboard and two distinct customization actions (new)

**Sign in before ordering** if you want the purchase to appear in **My account & recipes → My order history**. Guest purchases can be tracked by their private receipt/tracking token, but cannot be retroactively assigned to a newly created account.

1. Log in or create a customer account under **My account & recipes**. Set default milk, coffee strength, temperature and syrup; click **Save preferences**. These defaults are now preselected when you choose a new drink (if the beverage supports them); you can override them per drink. Order history does not automatically overwrite user-controlled defaults.
2. Open **Discover & order** and click **Customize** on a drink. Choose the drink options. Below the quoted price, there are **two separate actions**:
   - **Save to My Dashboard:** enter a memorable name (e.g. *My morning latte*) and click **Save named drink**. This stores a recipe without creating an order, processing a payment, or consuming ingredient stock. You are returned to **My saved drinks**.
   - **Place as a new order:** opens a separate simulated checkout with payment/receipt options. This does **not** modify a saved recipe. Only confirmation of payment creates the order; success adds it to **My order history** for signed-in customers.
3. In **My saved drinks**, each recipe provides **Edit / rename**, allowing a new name and changes to milk, temperature, etc., and **Place as new order**, which copies its saved settings into a fresh checkout. Nothing is charged until checkout confirmation. Saving changes does not edit past orders.
4. In **My order history**, each signed-in purchase displays reference, time, drink, price, configuration, masked payment details and current preparation state, with **Order again** to copy its historical settings into a new checkout. This does not repeat a payment automatically.
5. The recommendations engine accounts for counts of previously ordered drinks and identifies that signal among its explanations. Your explicit defaults are stored separately.

**Functional mapping:** stored preferences and editing = **US07 → R07 → PB07**; ordering a saved recipe via checkout = **US08 → R08 → PB08 (partial)**; private order history = **US09 → R09 → PB09**; history-driven recommendations = **US10 → R10 → PB10**. Backend `GET /api/my/orders` requires customer authentication and does not expose guest or other users' purchases.

### Payment options and real QR receipt (R04) — updated

Each checkout option now displays **its own details immediately below the payment selector**. These are teaching/demo fields only. **Never enter a real bank card number, payment credential, personal wallet password, or real staff access PIN.**

| Selected method | Visible inputs | Result displayed after ordering |
|---|---|---|
| **Bank card (simulated)** | Visa or Mastercard; only last **four sample digits** (default `4242`) | Receipt: `Visa demo card •••• 4242` (or selected brand/digits). No complete PAN, expiry, CVC, or payment gateway. |
| **Apple / Google Pay (simulated)** | Select Apple Pay / Google Pay; check explicit demo authorization box | Receipt names the selected wallet provider and indicates demo approval. No device wallet sheet opens. |
| **Employee card (simulated)** | Sample employee badge `EMP-1001`, demonstration PIN **`1357`** | Receipt shows the demo badge identifier but **never** the PIN. Invalid demo PIN is rejected; no real employee-card debit occurs. |

**Declined payment test:** Choose **Declined payment (test)** to verify no order is created and ingredient levels are unchanged. Successful demonstration payments are clearly marked `approved_simulated` in the backend.

**QR receipt:** Select **QR receipt preview** (not the email options). Complete an approved demo payment. The receipt area now displays a **scannable square QR code** with a **Download QR PNG** button, plus the ordinary **Download PDF receipt** button. The PDF embeds the actual QR on the same page as the detailed bill. Scanning the QR displays a compact, offline-friendly text summary with receipt reference, UTC date, drink, EUR total, and simulation disclaimer. The QR deliberately includes **no password, bank information, personal email, tracking token, or external URL**. This is a genuine scannable demonstration receipt but not a production tax-invoice or verification service. 

The QR PNG and PDFs are served only to the order holder with the order's tracking token (or authorized owner session for direct APIs). If you select Email or No receipt, a QR is not displayed. `qrcode[pil]` must be installed from `requirements.txt`.

### Simulated email receipt preview (no SMTP account needed)

1. In **Discover & order**, select a beverage and customization.
2. In the **Receipt option** dropdown, select **Email preview only (do not send)**.
3. Enter a valid recipient email. This address is used *only to display the simulated email*.
4. Click **Place as a new order**, then complete the simulated checkout. The system displays a realistic email with **From**, **To**, **Subject**, order reference, drink, customizations, time, total, and simulated-payment disclaimer.
5. The header says **EMAIL PREVIEW · NOT SENT**. You can print/save the preview as a PDF. The order progresses automatically.

**No SMTP login, email API or network email delivery is used in preview mode**, even if SMTP is configured. Use the distinct **Email receipt (send through SMTP)** option if you actually intend to send an email.

### Real email receipts (optional; works with any suitable SMTP provider)

1. In PowerShell inside the project folder, run `Copy-Item .env.example .env`.
2. Open `.env` in an editor and replace the sample SMTP settings with credentials from **your own email provider**. Provide the SMTP hostname, port, TLS mode (`starttls` for port 587 or `ssl` for port 465), username, sender address and provider-issued SMTP password. Normal account passwords may not work; some providers require a dedicated app password or SMTP credential.
3. **Restart the FastAPI server.** Do not commit `.env` to Git or share the SMTP password in screenshots/chats. Never enter your login password into the SmartBrew kiosk.
4. In **Discover & order**, choose a drink → **Email receipt (send through SMTP)** → enter the recipient email → **Place simulated order**.
5. Observe the printed/on-screen full receipt and the email state: `sent` means the SMTP provider accepted the message, **not a guarantee of inbox delivery**. If the server is not configured or delivery fails, the receipt is still available on screen and **Retry sending email** is offered.
6. For a safe first test, send the receipt to an address you control. The confirmation email explicitly states the payment and drink are simulations.

**Important:** Order creation succeeds even if SMTP sending fails. Email problems do not cancel orders or consume any additional ingredients. A resend uses the original recipient and order number, is limited to three delivery attempts, and cannot be used without an order-owner session or private tracking token. If SMTP is not configured, the on-screen receipt still works. Configure `.env`, restart and click **Retry sending email**.

The configuration example uses `smtp.gmail.com`, but another SMTP provider may be used. The system never sends from a sender email that you have not configured. If you previously placed an email-preview-only order in the old version, place a **new order** to provide the recipient address required by this version.

### Reset demo data

Stop the server, delete `smartbrew.db` in the project root, then restart. All accounts, custom recipes, orders, technician changes and logged events will be reset.


### Receipt PDF downloads and ordering again (updated)

After clicking **Place simulated order**, SmartBrew shows the automatic brewing timeline and a detailed on-screen receipt. The checkout form closes so you cannot accidentally resubmit it.

- **Download PDF receipt** produces a real `SB-000001.pdf`-style file, with the original order details; no browser-print configuration or SMTP account is needed.
- **Open PDF to print** opens the same receipt in a new browser tab, where you can use the PDF viewer’s Print button or `Ctrl + P`. Pop-ups may need to be permitted if your browser blocks new tabs.
- **Order another drink** clears only the on-screen current checkout, stops tracking polling in that browser tab, and returns to the menu. Previously created orders, inventory changes, transactions and account data remain in SQLite.
- PDF links require the private order tracking token or the authenticated order owner and are not publicly accessible by guessing an order number. Do not share private receipt links.

### Upgrade from the previous prototype

Stop the previous server with `Ctrl + C`. Extract the updated ZIP into a **new folder**, run the environment setup commands in that new `smartbrew-ai` folder, then restart the server. Install the latest dependencies again, including `qrcode[pil]`, for real QR image and PDF rendering. Refresh the browser with `Ctrl + F5`.

You may copy your old `smartbrew.db` into the updated project folder **while the server is stopped** to retain existing orders and accounts. Never overwrite the old copy before making a backup. The updated app can operate with a fresh database too.

## 3. Ten functionality demonstrations

Start the kiosk with a fresh database and follow these acceptance steps. The IDs match the **original Lab 2** (`USxx → Rxx → PBxx`) and the Task A shortlist.

| # | Requirement | Where to try it | Demonstration and expected result |
|---|---|---|---|
| 1 | **R01** Menu & availability | Discover & order | See six categorized drinks, indicative kcal, prices and live `Available/Unavailable` state. An active fault disables purchasing. |
| 2 | **R02** Customization | Discover & order → Customize | Choose milk, strength, temperature, syrup, size. Observe repricing and inventory feasibility; unsupported temperatures are rejected. |
| 3 | **R03** Ordering & preparation | Checkout → Place simulated order | Confirm order, the status advances automatically: Queued (about 3 s) → Brewing (about 9 s) → Ready (about 12 s total). No button is required. Click **Order another drink** to return to the menu and place a second separate order. Ingredient stock decreases **once** and the waste counter increases. |
| 4 | **R04** Payment & receipt | Checkout → Payment simulator | Choose the appropriate **method-specific demo fields** for bank card (brand and last four demo digits), Apple/Google Pay (provider and confirmation), or employee card (demo badge and test PIN). Choose no receipt/**real scannable QR receipt**/**email preview without sending**/**real SMTP email receipt**. Preview the complete receipt, use **Download PDF receipt** to save it, or **Open PDF to print** and print from your browser’s PDF viewer. For email, enter the recipient, configure SMTP and verify delivery status. Select **Declined payment** and verify no order or stock decrement occurs. |
| 5 | **R06** Account authentication | My account & recipes | Create an account (password ≥ 8 characters), log out, log in again. An incorrect password should be rejected. Email/password path only. |
| 6 | **R07** Preferences & recipes | My account & recipes | Save defaults. Customize from Discover, choose **Save to My Dashboard**, enter a name; use **Edit / rename** or **Place as new order**. |
| 7 | **R10** Contextual recommendations | Recommendations | Select **Tired** and a short time, or **Calm**, weather and time; click **Find my beverage**. Rankings and explanations change. Registered users' preferences/recent order influence some scores. |
| 8 | **R13** Admin authorization | Technician console | Incorrect PIN rejects entry and creates an audit event; the correct demo PIN `2468` unlocks the technician console. Customer credentials do not grant admin access. |
| 9 | **R14** Monitoring & safety | Technician console | Increase demo waste to near/full and verify menu disables; empty it. Inject an active test fault and verify orders blocked; **Resolve** restores availability. Inspect alerts and logs. |
| 10 | **R15** Service counters | Technician console | Select **+ Refill** for an ingredient, enter positive quantity, check new stock; click **Empty waste bin** and confirm counter resets. |

**Workflow note:** For features 3 and 4, test the declined case **before** the successful order. Creating a guest order is allowed. Technician role actions require the technician PIN, not just logging in as an ordinary customer.

## 4. Automated tests

From the project root, after dependencies are installed:

```bash
python -m pytest -q
```

The suite uses an isolated temporary SQLite database for each test and checks all 10 selected feature groups, including negative cases. The latest verified run displays `35 passed`. New tests cover readable, secured QR PNGs and one-page QR PDFs, method-specific simulated payment fields/validation, and automatic time-based order progress, validated email addresses, unavailable SMTP, receipt retries, mocked TLS email, protected PDFs, multiple orders, saved drinks, order-history isolation, and recommendation history. Tests do not send a real email to the internet. See `docs/TEST_RESULTS.md` for verification information.

For a quick runtime check while the server runs:

```bash
python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health').read().decode())"
```

## 5. Design, source comments and safety

Every Python function/API route has a docstring describing its purpose, input and output. Every JavaScript controller function has a JSDoc comment. The backend validates all order amounts and ingredients server-side. SMTP messages use Python standard-library `EmailMessage`, TLS transport, and an `.env` file kept outside Git. Passwords/PIN are stored using salted `scrypt` hashes; expiring bearer tokens are stored by hash in SQLite. Customer-owned recipes are scoped by authenticated user; the technician backend checks a different role. The database operation that places an order obtains a write lock, checks stock, then decrements it atomically.

`docs/IMPLEMENTATION_NOTES.md` states precisely how implementation choices relate to the user stories and UML diagrams and which functionality remains out of scope.