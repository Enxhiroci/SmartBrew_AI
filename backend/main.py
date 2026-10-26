"""SmartBrew AI executable educational prototype.

Implements ten mapped Lab 2 requirements (R01, R02, R03, R04, R06,
R07, R10, R13, R14 and R15). All machine, payments and environment
integrations are simulations: no coffee machine, charge, or weather API.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, EmailStr, Field, model_validator
from dotenv import load_dotenv
from backend.receipts import send_receipt, smtp_is_configured
from backend.receipt_pdf import build_receipt_pdf
from backend.qr_receipts import generate_qr_png

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')  # OS environment variables take priority.
BREW_START_SECONDS = 3
BREW_READY_SECONDS = 12
ALLOWED_MILK = {'dairy', 'oat', 'none'}
ALLOWED_STRENGTH = {'mild', 'regular', 'strong'}
ALLOWED_TEMP = {'warm', 'hot', 'iced'}
ALLOWED_SYRUP = {'none', 'vanilla', 'caramel'}
PAYMENT_OPTIONS = {'bank_card', 'mobile_wallet', 'employee_card'}
RECEIPT_OPTIONS = {'none', 'qr', 'email'}

# Seed fixtures intentionally small and deterministic for repeatable demonstrations.
DRINKS = [
    ('Espresso', 'Coffee', 'Rich and concentrated', 2.30, 4, {'beans': 18, 'water': 45}, ['hot', 'warm']),
    ('Caffè Latte', 'Coffee', 'Espresso with silky milk', 3.90, 125, {'beans': 18, 'water': 30, 'milk_dairy': 180}, ['hot', 'warm', 'iced']),
    ('Cappuccino', 'Coffee', 'Balanced espresso and foam', 3.70, 95, {'beans': 18, 'water': 30, 'milk_dairy': 120}, ['hot', 'warm']),
    ('Mocha', 'Coffee', 'Coffee and chocolate blend', 4.20, 180, {'beans': 18, 'water': 35, 'milk_dairy': 150, 'cocoa': 12}, ['hot', 'warm']),
    ('Matcha Latte', 'Tea', 'Earthy and smooth', 4.10, 150, {'matcha': 8, 'water': 40, 'milk_dairy': 180}, ['hot', 'warm', 'iced']),
    ('Iced Latte', 'Cold drinks', 'Refreshingly chilled espresso', 4.00, 125, {'beans': 18, 'water': 35, 'milk_dairy': 180}, ['iced']),
]
INITIAL_INGREDIENTS = {
    'beans': (1400, 180, 'g'), 'water': (12000, 2000, 'ml'),
    'milk_dairy': (3500, 500, 'ml'), 'milk_oat': (2600, 300, 'ml'),
    'vanilla_syrup': (600, 100, 'ml'), 'caramel_syrup': (600, 100, 'ml'),
    'cocoa': (500, 75, 'g'), 'matcha': (300, 60, 'g'),
}


class RegisterIn(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=120)


class LoginIn(BaseModel):
    email: str
    password: str


class PinIn(BaseModel):
    pin: str


class CustomizeIn(BaseModel):
    milk: Literal['dairy', 'oat', 'none'] = 'dairy'
    strength: Literal['mild', 'regular', 'strong'] = 'regular'
    temperature: Literal['warm', 'hot', 'iced'] = 'hot'
    syrup: Literal['none', 'vanilla', 'caramel'] = 'none'
    size: Literal['small', 'medium', 'large'] = 'medium'


class QuoteIn(BaseModel):
    beverage_id: int
    customization: CustomizeIn = Field(default_factory=CustomizeIn)


class OrderIn(QuoteIn):
    payment_method: Literal['bank_card', 'mobile_wallet', 'employee_card'] = 'bank_card'
    receipt_method: Literal['none', 'qr', 'email', 'email_preview'] = 'qr'
    payment_approved: bool = True  # explicit simulator outcome; never real payment
    payment_details: dict[str, str] = Field(default_factory=dict)  # demo fields, sanitized below
    receipt_email: EmailStr | None = None

    @model_validator(mode='after')
    def validate_receipt_email(self) -> 'OrderIn':
        """Require an email recipient for email receipts; input parsed order, return validated order."""
        if self.receipt_method in {'email', 'email_preview'} and self.receipt_email is None:
            raise ValueError('Enter an email address for the email receipt')
        return self


def describe_simulated_payment(method: str, details: dict[str, str]) -> str:
    """Validate method-specific demo inputs; return safe public description without secrets.

    Args:
        method: Selected supported payment type.
        details: Optional non-sensitive demo-only fields from checkout.
    Returns:
        Masked payment label safe to store on receipts; never a real authorization.
    """
    if method == 'bank_card':
        brand = details.get('brand', 'Visa')
        last4 = details.get('last4', '4242')
        if brand not in {'Visa', 'Mastercard'} or len(last4) != 4 or not last4.isascii() or not last4.isdecimal():
            raise HTTPException(422, 'Select a demo card brand and enter exactly four demo digits')
        return f'{brand} demo card •••• {last4}'
    if method == 'mobile_wallet':
        provider = details.get('wallet', 'Apple Pay')
        if provider not in {'Apple Pay', 'Google Pay'}:
            raise HTTPException(422, 'Select Apple Pay or Google Pay (simulation)')
        if details and details.get('confirmed') != 'yes':
            raise HTTPException(422, 'Confirm this simulated wallet payment')
        return f'{provider} · demo wallet approval'
    if method == 'employee_card':
        badge = details.get('badge', 'EMP-1001')
        code = details.get('demo_pin', '1357')
        if not (4 <= len(badge) <= 16 and badge.isascii() and
                all(ch.isalnum() or ch == '-' for ch in badge)):
            raise HTTPException(422, 'Employee demo card ID must be 4–16 letters, digits or hyphens')
        if code != '1357':
            raise HTTPException(402, 'Employee demo PIN declined. Use the documented test PIN 1357')
        return f'Employee demo card {badge}'
    raise HTTPException(422, 'Unsupported payment method')


class PreferencesIn(BaseModel):
    coffee_strength: Literal['mild', 'regular', 'strong'] = 'regular'
    milk_type: Literal['dairy', 'oat', 'none'] = 'dairy'
    temperature: Literal['warm', 'hot', 'iced'] = 'hot'
    syrup_preference: Literal['none', 'vanilla', 'caramel'] = 'none'


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    beverage_id: int
    customization: CustomizeIn = Field(default_factory=CustomizeIn)


class ContextIn(BaseModel):
    weather: Literal['sunny', 'rainy', 'cold', 'mild'] = 'mild'
    mood: Literal['unspecified', 'tired', 'energetic', 'calm'] = 'unspecified'
    time_available_minutes: int = Field(default=10, ge=1, le=120)


class RefillIn(BaseModel):
    amount: int = Field(gt=0, le=100000)


class BinFillIn(BaseModel):
    amount: int = Field(gt=0, le=100)


class FaultIn(BaseModel):
    message: str = Field(min_length=3, max_length=150)


def digest_password(password: str) -> str:
    """Hash password/PIN with a random salt; input is secret text, output is encoded scrypt digest."""
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + ':' + derived.hex()


def verify_password(password: str, saved: str) -> bool:
    """Check candidate secret against encoded scrypt hash; return True for an exact match."""
    try:
        salt_hex, expected_hex = saved.split(':', 1)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(expected_hex))
    except (ValueError, TypeError):
        return False


@contextmanager
def connection(db_path: str) -> Iterator[sqlite3.Connection]:
    """Open database transaction for given path; yield connection and commit/rollback on exit."""
    db = sqlite3.connect(db_path, timeout=8)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def initialize_database(db_path: str) -> None:
    """Create storage and seed six drinks and inventory if empty; input DB filename, returns None."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connection(db_path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL, password_hash TEXT NOT NULL, preferences TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, role TEXT NOT NULL,
          user_id INTEGER, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS drinks(id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
          description TEXT NOT NULL, price REAL NOT NULL, calories INTEGER NOT NULL,
          ingredients TEXT NOT NULL, temperatures TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ingredients(name TEXT PRIMARY KEY, quantity INTEGER NOT NULL CHECK(quantity>=0),
          threshold INTEGER NOT NULL, unit TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS machine(id INTEGER PRIMARY KEY CHECK(id=1), bin_level INTEGER NOT NULL DEFAULT 0,
          bin_capacity INTEGER NOT NULL DEFAULT 100);
        CREATE TABLE IF NOT EXISTS faults(id INTEGER PRIMARY KEY, message TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER, drink_id INTEGER NOT NULL,
          customization TEXT NOT NULL, amount REAL NOT NULL, payment_method TEXT NOT NULL,
          receipt_method TEXT NOT NULL, payment_status TEXT NOT NULL, status TEXT NOT NULL,
          access_hash TEXT NOT NULL, created_at INTEGER NOT NULL,
          receipt_email TEXT, email_status TEXT NOT NULL DEFAULT 'not_requested',
          email_attempts INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS recipes(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
          name TEXT NOT NULL, drink_id INTEGER NOT NULL, customization TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, event TEXT NOT NULL,
          detail TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_config(id INTEGER PRIMARY KEY CHECK(id=1), pin_hash TEXT NOT NULL);
        ''')
        # Migrate existing demo databases without deleting customers, orders or inventory.
        existing_columns = {col['name'] for col in db.execute('PRAGMA table_info(orders)')}
        for name, definition in (
            ('receipt_email', 'TEXT'),
            ('email_status', "TEXT NOT NULL DEFAULT 'not_requested'"),
            ('email_attempts', 'INTEGER NOT NULL DEFAULT 0'),
            ('payment_description', "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in existing_columns:
                db.execute(f'ALTER TABLE orders ADD COLUMN {name} {definition}')
        if db.execute('SELECT COUNT(*) AS n FROM drinks').fetchone()['n'] == 0:
            for name, cat, description, price, calories, ingredients, temps in DRINKS:
                db.execute('INSERT INTO drinks(name,category,description,price,calories,ingredients,temperatures) VALUES(?,?,?,?,?,?,?)',
                           (name, cat, description, price, calories, json.dumps(ingredients), json.dumps(temps)))
        if db.execute('SELECT COUNT(*) AS n FROM ingredients').fetchone()['n'] == 0:
            for key, (quantity, threshold, unit) in INITIAL_INGREDIENTS.items():
                db.execute('INSERT INTO ingredients VALUES(?,?,?,?)', (key, quantity, threshold, unit))
        db.execute('INSERT OR IGNORE INTO machine(id,bin_level,bin_capacity) VALUES(1,0,100)')
        if not db.execute('SELECT id FROM admin_config WHERE id=1').fetchone():
            demo_pin = os.getenv('SMARTBREW_ADMIN_PIN', '2468')
            db.execute('INSERT INTO admin_config VALUES(1,?)', (digest_password(demo_pin),))


def log_event(db: sqlite3.Connection, event: str, detail: str) -> None:
    """Add audit event to active DB transaction; input connection, event and detail, output None."""
    db.execute('INSERT INTO events(event,detail,created_at) VALUES(?,?,?)', (event, detail, int(time.time())))


def issue_session(db: sqlite3.Connection, role: str, user_id: int | None) -> str:
    """Create expiring bearer session for role/user; return its un-hashed one-time-issued token."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token_hash, role, user_id, int(time.time()) + 8*3600))
    return token


def session_for(db: sqlite3.Connection, auth: str | None, role: str | None = None) -> sqlite3.Row | None:
    """Resolve optional Bearer header, optionally require role; return session row or raise 401/403."""
    if not auth or not auth.startswith('Bearer '):
        if role:
            raise HTTPException(401, 'Authentication required')
        return None
    digest = hashlib.sha256(auth[7:].encode()).hexdigest()
    user = db.execute('SELECT * FROM sessions WHERE token_hash=? AND expires_at>?',
                      (digest, int(time.time()))).fetchone()
    if not user:
        raise HTTPException(401, 'Invalid or expired session')
    if role and user['role'] != role:
        raise HTTPException(403, 'Insufficient permissions')
    return user


def drink_by_id(db: sqlite3.Connection, drink_id: int) -> sqlite3.Row:
    """Look up drink by numeric ID; return row or raise HTTP 404."""
    drink = db.execute('SELECT * FROM drinks WHERE id=?', (drink_id,)).fetchone()
    if not drink:
        raise HTTPException(404, 'Drink not found')
    return drink


def stock_snapshot(db: sqlite3.Connection) -> dict[str, int]:
    """Read ingredient quantities from DB; return name-to-quantity mapping."""
    return {r['name']: r['quantity'] for r in db.execute('SELECT name,quantity FROM ingredients')}


def active_faults(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """Load unresolved faults from DB; return serializable list of fault dictionaries."""
    return [dict(r) for r in db.execute('SELECT * FROM faults WHERE active=1 ORDER BY id DESC')]


def required_ingredients(drink: sqlite3.Row, opts: CustomizeIn) -> dict[str, int]:
    """Compute recipe ingredient demand for drink and options; return quantities per ingredient."""
    if opts.temperature not in json.loads(drink['temperatures']):
        raise HTTPException(422, f"{drink['name']} does not support {opts.temperature} temperature")
    demand = dict(json.loads(drink['ingredients']))
    if 'milk_dairy' in demand:
        qty = demand.pop('milk_dairy')
        if opts.milk != 'none':
            demand['milk_dairy' if opts.milk == 'dairy' else 'milk_oat'] = qty
    if opts.syrup != 'none':
        demand[f'{opts.syrup}_syrup'] = 15
    if opts.size == 'large':
        demand = {key: int(round(val * 1.30)) for key, val in demand.items()}
    elif opts.size == 'small':
        demand = {key: int(round(val * .75)) for key, val in demand.items()}
    if opts.strength == 'strong' and 'beans' in demand:
        demand['beans'] += 6
    if opts.strength == 'mild' and 'beans' in demand:
        demand['beans'] = max(4, demand['beans'] - 5)
    return demand


def calculate_price(drink: sqlite3.Row, opts: CustomizeIn) -> float:
    """Calculate drink price with milk, syrup and size modifiers; return rounded demo EUR amount."""
    return round(drink['price'] + (.40 if opts.milk == 'oat' and 'milk_dairy' in json.loads(drink['ingredients']) else 0)
                 + (.30 if opts.syrup != 'none' else 0)
                 + (.60 if opts.size == 'large' else -.30 if opts.size == 'small' else 0), 2)


def blocking_reasons(db: sqlite3.Connection, demand: dict[str, int]) -> list[str]:
    """Check stock, full waste bin and active faults; return list of blocking explanations."""
    stock = stock_snapshot(db)
    reasons = [f'Insufficient {key}' for key, qty in demand.items() if stock.get(key, 0) < qty]
    machine = db.execute('SELECT * FROM machine WHERE id=1').fetchone()
    if machine['bin_level'] + 8 > machine['bin_capacity']:
        reasons.append('Waste bin requires emptying')
    if active_faults(db):
        reasons.append('Machine has an active fault')
    return reasons


def serialize_drink(db: sqlite3.Connection, drink: sqlite3.Row) -> dict[str, Any]:
    """Build catalog representation from drink and current stock; return serializable drink object."""
    opts = CustomizeIn(temperature=json.loads(drink['temperatures'])[0])
    demand = required_ingredients(drink, opts)
    reasons = blocking_reasons(db, demand)
    return dict(id=drink['id'], name=drink['name'], category=drink['category'],
                description=drink['description'], price=drink['price'], calories=drink['calories'],
                supported_temperatures=json.loads(drink['temperatures']), available=not reasons,
                unavailable_reasons=reasons)


def receipt_for(order: sqlite3.Row, drink_name: str) -> dict[str, Any]:
    """Build complete receipt from order and drink name; return safe JSON for screen/email rendering."""
    method = order['receipt_method']
    status = order['email_status']
    details = {
        'method': method,
        'reference': f"SB-{order['id']:06d}",
        'created_at': datetime.fromtimestamp(order['created_at'], timezone.utc).isoformat(timespec='seconds'),
        'drink': drink_name,
        'customization': json.loads(order['customization']),
        'amount': float(order['amount']),
        'currency': 'EUR',
        'payment_method': order['payment_method'],
        'payment_description': order['payment_description'] or order['payment_method'].replace('_', ' ').title() + ' (demo)',
        'payment_status': order['payment_status'],
        'email_to': order['receipt_email'] if method in {'email', 'email_preview'} else None,
        'email_status': status,
        'email_attempts': order['email_attempts'],
        'simulation': 'Payment and beverage preparation are simulations; this is not a tax invoice.',
    }
    if method == 'email':
        details['message'] = {
            'sent': 'Email accepted by the SMTP provider (recipient delivery is not guaranteed).',
            'failed': 'Email could not be sent. Check the SMTP settings and retry.',
            'not_configured': 'Email not sent: SMTP must be configured in .env.',
            'pending': 'Email delivery is being attempted.',
        }.get(status, 'Email receipt has not been sent.')
    elif method == 'email_preview':
        details['message'] = 'Email preview only — no email was sent and SMTP was not contacted.'
    elif method == 'qr':
        details['message'] = f"QR receipt is ready: scan the code or download your PDF. No real charge occurred."
    else:
        details['message'] = 'No receipt was requested; the order summary is displayed.'
    return details


def automatic_status(db: sqlite3.Connection, order: sqlite3.Row) -> str:
    """Compute/persist idempotent simulated brewing state using order timestamp; return current state."""
    elapsed = max(0, int(time.time()) - order['created_at'])
    computed = 'ready' if elapsed >= BREW_READY_SECONDS else 'brewing' if elapsed >= BREW_START_SECONDS else 'queued'
    # Never regress a state manually advanced by an older API client.
    ranks = {'queued': 0, 'brewing': 1, 'ready': 2}
    status = max((computed, order['status']), key=lambda value: ranks[value])
    if status != order['status']:
        db.execute('UPDATE orders SET status=? WHERE id=?', (status, order['id']))
        log_event(db, 'ORDER_STATUS_AUTO', f"order={order['id']} status={status}")
    return status


def deliver_order_receipt(db_path: str, order_id: int) -> dict[str, Any]:
    """Attempt one SMTP delivery for existing email order; return updated receipt even on failure."""
    with connection(db_path) as db:
        row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
        if not row or row['receipt_method'] != 'email':
            raise HTTPException(404, 'Email receipt not available for this order')
        if not row['receipt_email']:
            raise HTTPException(409, 'This older order has no recipient email; place a new order for email delivery')
        if row['email_status'] == 'sent':
            return receipt_for(row, drink_by_id(db, row['drink_id'])['name'])
        if row['email_attempts'] >= 3:
            raise HTTPException(429, 'Maximum receipt delivery attempts reached')
        if not smtp_is_configured():
            db.execute("UPDATE orders SET email_status='not_configured' WHERE id=?", (order_id,))
            updated = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            return receipt_for(updated, drink_by_id(db, row['drink_id'])['name'])
        db.execute("UPDATE orders SET email_status='pending', email_attempts=email_attempts+1 WHERE id=?", (order_id,))
        receipt = receipt_for(db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone(),
                              drink_by_id(db, row['drink_id'])['name'])
    try:
        send_receipt(row['receipt_email'], receipt)
    except Exception:
        # Hide SMTP usernames/passwords and provider errors from the browser.
        status = 'failed'
    else:
        status = 'sent'
    with connection(db_path) as db:
        db.execute('UPDATE orders SET email_status=? WHERE id=?', (status, order_id))
        log_event(db, 'RECEIPT_EMAIL', f'order={order_id}; status={status}')
        updated = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
        return receipt_for(updated, drink_by_id(db, updated['drink_id'])['name'])


def compose_recommendation(drink: dict[str, Any], context: ContextIn,
                           preference: dict[str, Any], previous_orders: int) -> tuple[str, str]:
    """Write a friendly, evidence-grounded suggestion.

    Args:
        drink: Serialized catalog item including its name, ingredients and temperatures.
        context: User-selected demo weather, mood and available time.
        preference: Current customer's explicitly saved drink preferences, if any.
        previous_orders: Number of earlier orders for this exact beverage.
    Returns:
        A tuple containing a short editorial headline and a 2–3 sentence description.
    """
    name = drink['name']
    profiles = {
        'Espresso': ('Small cup, bold character.',
                     'Rich and concentrated, with everything you love about coffee in a beautifully simple pour.'),
        'Caffè Latte': ('A softer kind of coffee break.',
                       'Smooth espresso and silky milk make this an easy, comforting café classic.'),
        'Cappuccino': ('A little ritual, perfectly balanced.',
                       'Espresso beneath a cloud of foam brings just the right mix of depth and lightness.'),
        'Mocha': ('Coffee with a touch of indulgence.',
                  'Espresso and cocoa come together for something rich, mellow and a little special.'),
        'Matcha Latte': ('Take the gentle route.',
                        'Earthy matcha and creamy milk create a smooth, unhurried alternative to coffee.'),
        'Iced Latte': ('Your café moment, on ice.',
                       'Cool milk and espresso make this a refreshing take on a familiar favorite.'),
    }
    headline, opening = profiles.get(name, ('A cup worth discovering.',
                           f'{name} is one of our available drinks, ready to customize to your taste.'))
    temperatures = drink['supported_temperatures']
    moment = None
    if context.time_available_minutes <= 3 and name == 'Espresso':
        moment = 'With only a few minutes to spare, this is a wonderfully straightforward choice.'
    elif context.weather in {'cold', 'rainy'} and 'hot' in temperatures:
        moment = ('With the rainy weather you selected, a warm cup feels especially inviting.'
                  if context.weather == 'rainy' else
                  'On the cold day you selected, this is a lovely drink to enjoy warm.')
    elif context.weather == 'sunny' and 'iced' in temperatures:
        moment = 'For the sunny weather you selected, try it chilled for a lighter-feeling pause.'
    elif context.mood == 'calm' and drink['category'] == 'Tea':
        moment = 'For a calm moment, its gentle flavors are a thoughtful match.'
    elif context.mood == 'tired' and drink['category'] == 'Coffee':
        moment = 'If you are in the mood for coffee, its familiar espresso character is an appealing pick.'
    elif context.mood == 'energetic' and 'iced' in temperatures:
        moment = 'An iced version could be a fun match for the upbeat mood you selected.'

    personalization = None
    if previous_orders:
        personalization = ('You have ordered it before, so it could be a familiar favorite.' if previous_orders == 1
                           else f'You have chosen it {previous_orders} times before—a familiar favorite to revisit.')
    elif preference.get('milk_type') == 'oat' and 'milk_dairy' in drink['ingredients']:
        personalization = 'You can choose your preferred oat milk during customization, subject to stock.'
    elif preference.get('temperature') == 'iced' and 'iced' in temperatures:
        personalization = 'It is available iced, just as you prefer.'
    elif preference.get('coffee_strength') == 'strong' and drink['category'] == 'Coffee':
        personalization = 'You can personalize the coffee strength to match your saved taste.'

    sentences = [opening]
    if moment:
        sentences.append(moment)
    if personalization:
        sentences.append(personalization)
    return headline, ' '.join(sentences)



def create_app(db_path: str | None = None) -> FastAPI:
    """Construct FastAPI server using optional SQLite path; return fully initialized app for running/tests."""
    path = db_path or os.getenv('SMARTBREW_DB_PATH', str(ROOT / 'smartbrew.db'))
    initialize_database(path)
    app = FastAPI(title='SmartBrew AI – Educational Prototype', version='1.1.0')
    app.state.db_path = path

    @app.get('/')
    def home() -> FileResponse:
        """Serve the single-page kiosk frontend; no input, return HTML file response."""
        return FileResponse(ROOT / 'frontend' / 'index.html')

    @app.get('/assets/{filename}')
    def asset(filename: str) -> FileResponse:
        """Serve allowlisted local CSS/JS assets by filename; return file or HTTP 404."""
        if filename not in {'app.js', 'styles.css', 'smartbrew-logo.png'}:
            raise HTTPException(404, 'Asset not found')
        return FileResponse(ROOT / 'frontend' / filename)

    @app.get('/api/health')
    def health() -> dict[str, str]:
        """Return health probe and simulation disclaimer; no input, returns JSON object."""
        return {'status': 'ok', 'mode': 'educational simulation'}

    @app.get('/api/catalog')
    def catalog() -> list[dict[str, Any]]:
        """List stock-aware menu drinks; no input, return serialized drink list (R01)."""
        with connection(path) as db:
            return [serialize_drink(db, r) for r in db.execute('SELECT * FROM drinks ORDER BY id')]

    @app.post('/api/register', status_code=201)
    def register(data: RegisterIn) -> dict[str, Any]:
        """Create registered customer with hashed password; return user and token (R06)."""
        email = data.email.strip().lower()
        if '@' not in email or '.' not in email.split('@')[-1]:
            raise HTTPException(422, 'Enter a valid email address')
        with connection(path) as db:
            try:
                cursor = db.execute('INSERT INTO users(email,name,password_hash,preferences) VALUES(?,?,?,?)',
                                    (email, data.name.strip(), digest_password(data.password), json.dumps(PreferencesIn().model_dump())))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Email already registered')
            token = issue_session(db, 'customer', cursor.lastrowid)
            return {'token': token, 'name': data.name.strip(), 'role': 'customer'}

    @app.post('/api/login')
    def login(data: LoginIn) -> dict[str, Any]:
        """Authenticate email and password, issue expiring customer token; return token and display name."""
        with connection(path) as db:
            user = db.execute('SELECT * FROM users WHERE email=?', (data.email.strip().lower(),)).fetchone()
            if not user or not verify_password(data.password, user['password_hash']):
                raise HTTPException(401, 'Invalid email or password')
            return {'token': issue_session(db, 'customer', user['id']), 'name': user['name'], 'role': 'customer'}

    @app.get('/api/me')
    def me(authorization: str | None = Header(None)) -> dict[str, Any]:
        """Read authenticated user profile and preferences; return user object (R07)."""
        with connection(path) as db:
            session = session_for(db, authorization, 'customer')
            user = db.execute('SELECT id,email,name,preferences FROM users WHERE id=?', (session['user_id'],)).fetchone()
            return {'id': user['id'], 'email': user['email'], 'name': user['name'],
                    'preferences': json.loads(user['preferences'])}

    @app.get('/api/my/orders')
    def my_order_history(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
        """List authenticated customer's past purchases; input customer bearer token, return newest first (R09)."""
        with connection(path) as db:
            customer = session_for(db, authorization, 'customer')
            history = []
            for row in db.execute("""SELECT orders.*, drinks.name AS drink_name FROM orders
                JOIN drinks ON drinks.id=orders.drink_id
                WHERE orders.user_id=? ORDER BY orders.id DESC LIMIT 100""", (customer['user_id'],)).fetchall():
                history.append({
                    'id': row['id'], 'reference': f"SB-{row['id']:06d}",
                    'beverage_id': row['drink_id'], 'drink': row['drink_name'],
                    'customization': json.loads(row['customization']),
                    'price': float(row['amount']), 'payment_method': row['payment_method'],
                    'payment_description': row['payment_description'] or 'Demo payment',
                    'payment_status': row['payment_status'], 'status': automatic_status(db, row),
                    'created_at': datetime.fromtimestamp(row['created_at'], timezone.utc).isoformat(),
                })
            return history

    @app.put('/api/preferences')
    def save_preferences(data: PreferencesIn, authorization: str | None = Header(None)) -> dict[str, Any]:
        """Persist logged-in customer's preference settings; return saved preferences (R07)."""
        with connection(path) as db:
            session = session_for(db, authorization, 'customer')
            db.execute('UPDATE users SET preferences=? WHERE id=?', (json.dumps(data.model_dump()), session['user_id']))
            return {'preferences': data.model_dump()}

    @app.post('/api/recipes', status_code=201)
    def save_recipe(data: RecipeIn, authorization: str | None = Header(None)) -> dict[str, Any]:
        """Save a named beverage recipe for customer; return new recipe ID and name (R07)."""
        with connection(path) as db:
            user = session_for(db, authorization, 'customer')
            drink = drink_by_id(db, data.beverage_id)
            required_ingredients(drink, data.customization)
            cur = db.execute('INSERT INTO recipes(user_id,name,drink_id,customization) VALUES(?,?,?,?)',
                             (user['user_id'], data.name.strip(), data.beverage_id, data.customization.model_dump_json()))
            return {'id': cur.lastrowid, 'name': data.name.strip()}

    @app.get('/api/recipes')
    def recipes(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
        """Retrieve recipes for authenticated customer; return list, never another customer's recipes."""
        with connection(path) as db:
            user = session_for(db, authorization, 'customer')
            return [dict(id=r['id'], name=r['name'], beverage_id=r['drink_id'], drink=r['drink'],
                         customization=json.loads(r['customization']))
                    for r in db.execute('SELECT recipes.*,drinks.name AS drink FROM recipes JOIN drinks ON drinks.id=recipes.drink_id WHERE user_id=? ORDER BY recipes.id DESC',
                                        (user['user_id'],))]

    @app.put('/api/recipes/{recipe_id}')
    def edit_recipe(recipe_id: int, data: RecipeIn,
                    authorization: str | None = Header(None)) -> dict[str, Any]:
        """Edit owning customer's named recipe; inputs ID and new data, return update confirmation (R07)."""
        with connection(path) as db:
            session = session_for(db, authorization, 'customer')
            drink = drink_by_id(db, data.beverage_id)
            required_ingredients(drink, data.customization)
            cur = db.execute('UPDATE recipes SET name=?, drink_id=?, customization=? WHERE id=? AND user_id=?',
                             (data.name.strip(), data.beverage_id,
                              data.customization.model_dump_json(), recipe_id, session['user_id']))
            if cur.rowcount != 1:
                raise HTTPException(404, 'Recipe not found for this customer')
            return {'id': recipe_id, 'name': data.name.strip(), 'updated': True}

    @app.post('/api/quote')
    def quote(data: QuoteIn) -> dict[str, Any]:
        """Validate customization against recipes and inventory; return calculated price, demand, blockers (R02)."""
        with connection(path) as db:
            drink = drink_by_id(db, data.beverage_id)
            demand = required_ingredients(drink, data.customization)
            reasons = blocking_reasons(db, demand)
            return {'beverage': drink['name'], 'price': calculate_price(drink, data.customization),
                    'ingredients': demand, 'available': not reasons, 'blocking_reasons': reasons,
                    'customization': data.customization.model_dump()}

    @app.post('/api/orders', status_code=201)
    def order(data: OrderIn, authorization: str | None = Header(None)) -> dict[str, Any]:
        """Create paid demo order, deduct stock once, optionally send real email; return order and receipt (R03/R04)."""
        payment_description = describe_simulated_payment(data.payment_method, data.payment_details)
        with connection(path) as db:
            db.execute('BEGIN IMMEDIATE')
            customer = session_for(db, authorization) if authorization else None
            if customer and customer['role'] != 'customer':
                raise HTTPException(403, 'Technician session cannot place customer order')
            drink = drink_by_id(db, data.beverage_id)
            demand = required_ingredients(drink, data.customization)
            reasons = blocking_reasons(db, demand)
            if reasons:
                raise HTTPException(409, '; '.join(reasons))
            if not data.payment_approved:
                log_event(db, 'PAYMENT_DECLINED', f'drink={data.beverage_id}; simulated')
                db.commit()
                raise HTTPException(402, 'Simulated payment declined: no order or stock change')
            amount = calculate_price(drink, data.customization)
            access_token = secrets.token_urlsafe(24)
            cur = db.execute('''INSERT INTO orders(user_id,drink_id,customization,amount,payment_method,
                    receipt_method,payment_status,status,access_hash,created_at,receipt_email,email_status,payment_description)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (customer['user_id'] if customer else None, data.beverage_id,
                     data.customization.model_dump_json(), amount, data.payment_method,
                     data.receipt_method, 'approved_simulated', 'queued',
                     hashlib.sha256(access_token.encode()).hexdigest(), int(time.time()),
                     str(data.receipt_email) if data.receipt_method in {'email', 'email_preview'} else None,
                     'pending' if data.receipt_method == 'email' else 'preview_only' if data.receipt_method == 'email_preview' else 'not_requested',
                     payment_description))
            for ingredient, amount_used in demand.items():
                db.execute('UPDATE ingredients SET quantity=quantity-? WHERE name=?', (amount_used, ingredient))
            db.execute('UPDATE machine SET bin_level=bin_level+8 WHERE id=1')
            log_event(db, 'ORDER_PLACED', f'order={cur.lastrowid}; payment simulated; stock consumed once')
            row = db.execute('SELECT * FROM orders WHERE id=?', (cur.lastrowid,)).fetchone()
            order_id = row['id']
            receipt = receipt_for(row, drink['name'])
        # SMTP runs after transaction: email failures never undo paid demo orders or stock changes.
        if data.receipt_method == 'email':
            receipt = deliver_order_receipt(path, order_id)
        return {'id': order_id, 'status': 'queued', 'amount': amount,
                'payment_status': 'approved_simulated', 'tracking_token': access_token,
                'receipt': receipt, 'simulation': 'No real charge or physical brewing.'}

    def secured_order(db: sqlite3.Connection, oid: int, tracking_token: str | None,
                      auth: str | None) -> sqlite3.Row:
        """Authorize order by opaque tracking token or owning login; return order row or raise 401/404."""
        row = db.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
        if not row:
            raise HTTPException(404, 'Order not found')
        valid_token = bool(tracking_token and hmac.compare_digest(
            hashlib.sha256(tracking_token.encode()).hexdigest(), row['access_hash']))
        user = session_for(db, auth) if auth else None
        valid_owner = bool(user and user['role'] == 'customer' and row['user_id'] is not None
                           and user['user_id'] == row['user_id'])
        if not (valid_token or valid_owner):
            raise HTTPException(403, 'Not authorized to view this order')
        return row

    @app.get('/api/orders/{order_id}')
    def get_order(order_id: int, tracking_token: str | None = None,
                  authorization: str | None = Header(None)) -> dict[str, Any]:
        """Get protected order status and simulated receipt; return order view (R03/R04)."""
        with connection(path) as db:
            row = secured_order(db, order_id, tracking_token, authorization)
            drink = drink_by_id(db, row['drink_id'])
            status = automatic_status(db, row)
            return {'id': row['id'], 'drink': drink['name'], 'status': status,
                    'amount': row['amount'], 'payment_status': row['payment_status'],
                    'customization': json.loads(row['customization']),
                    'created_at': row['created_at'], 'brew_ready_seconds': BREW_READY_SECONDS,
                    'receipt': receipt_for(row, drink['name'])}

    @app.get('/api/orders/{order_id}/receipt.pdf')
    def download_receipt_pdf(order_id: int, tracking_token: str | None = None,
                             inline: bool = False,
                             authorization: str | None = Header(None)) -> Response:
        """Return PDF receipt to its owner; inputs order ID and access, output printable PDF (R04)."""
        with connection(path) as db:
            row = secured_order(db, order_id, tracking_token, authorization)
            receipt = receipt_for(row, drink_by_id(db, row['drink_id'])['name'])
        content = build_receipt_pdf(receipt)
        disposition = 'inline' if inline else 'attachment'
        return Response(content=content, media_type='application/pdf', headers={
            'Content-Disposition': f'{disposition}; filename="{receipt["reference"]}.pdf"',
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer',
        })

    @app.get('/api/orders/{order_id}/receipt-qr.png')
    def download_receipt_qr(order_id: int, tracking_token: str | None = None,
                            authorization: str | None = Header(None)) -> Response:
        """Return scannable PNG receipt QR to the order holder; require QR receipt choice."""
        with connection(path) as db:
            row = secured_order(db, order_id, tracking_token, authorization)
            if row['receipt_method'] != 'qr':
                raise HTTPException(404, 'QR receipt was not selected for this order')
            receipt = receipt_for(row, drink_by_id(db, row['drink_id'])['name'])
        content = generate_qr_png(receipt)
        return Response(content=content, media_type='image/png', headers={
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer',
        })

    @app.post('/api/orders/{order_id}/email-receipt')
    def retry_email_receipt(order_id: int, tracking_token: str | None = None,
                            authorization: str | None = Header(None)) -> dict[str, Any]:
        """Retry a failed/unconfigured email receipt for its owner; return status and full receipt."""
        with connection(path) as db:
            row = secured_order(db, order_id, tracking_token, authorization)
            if row['receipt_method'] != 'email':
                raise HTTPException(409, 'This order did not request an email receipt')
        return {'receipt': deliver_order_receipt(path, order_id)}

    @app.post('/api/orders/{order_id}/advance')
    def advance_order(order_id: int, tracking_token: str | None = None,
                      authorization: str | None = Header(None)) -> dict[str, Any]:
        """Advance simulated queue→brewing→ready state for authorized order; return updated status (R03)."""
        with connection(path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = secured_order(db, order_id, tracking_token, authorization)
            if row['status'] == 'ready':
                return {'id': order_id, 'status': 'ready', 'note': 'Already ready; no additional stock consumed'}
            next_status = {'queued': 'brewing', 'brewing': 'ready'}[row['status']]
            db.execute('UPDATE orders SET status=? WHERE id=?', (next_status, order_id))
            log_event(db, 'ORDER_STATUS', f'order={order_id} status={next_status}')
            return {'id': order_id, 'status': next_status,
                    'note': 'Simulated state only; no physical beverage prepared'}


    @app.post('/api/recommendations')
    def recommendations(data: ContextIn, authorization: str | None = Header(None)) -> dict[str, Any]:
        """Rank available drinks by manual weather, mood, time, and saved preferences; return explained top three (R10)."""
        with connection(path) as db:
            session = session_for(db, authorization) if authorization else None
            preference = {}
            history_counts = {}
            if session and session['role'] == 'customer':
                user = db.execute('SELECT preferences FROM users WHERE id=?', (session['user_id'],)).fetchone()
                preference = json.loads(user['preferences'])
                for past in db.execute('SELECT drink_id, COUNT(*) AS count FROM orders WHERE user_id=? GROUP BY drink_id',
                                       (session['user_id'],)):
                    history_counts[past['drink_id']] = past['count']
            ranked = []
            for drink in db.execute('SELECT * FROM drinks ORDER BY id'):
                item = serialize_drink(db, drink)
                if not item['available']:
                    continue
                score = 10.0
                reasons = []
                if data.weather in {'cold', 'rainy'} and 'hot' in item['supported_temperatures']:
                    score += 3; reasons.append('Warm-weather comfort')
                if data.weather == 'sunny' and 'iced' in item['supported_temperatures']:
                    score += 4; reasons.append('Great chilled on sunny days')
                if data.mood == 'tired' and drink['category'] == 'Coffee':
                    score += 3; reasons.append('Coffee-style favorite')
                if data.mood == 'calm' and drink['category'] == 'Tea':
                    score += 4; reasons.append('Matches a calm moment')
                if data.mood == 'energetic' and 'Iced' in drink['name']:
                    score += 3; reasons.append('Iced and refreshing')
                if data.time_available_minutes <= 3 and drink['name'] == 'Espresso':
                    score += 5; reasons.append('Good for a quick break')
                if preference.get('milk_type') == 'oat' and 'milk_dairy' in json.loads(drink['ingredients']):
                    score += 1; reasons.append('Oat milk customization')
                if history_counts.get(drink['id'], 0):
                    score += min(4, history_counts[drink['id']] * 2)
                    reasons.append(f"Picked before: {history_counts[drink['id']]}×")
                headline, description = compose_recommendation(
                    item, data, preference, history_counts.get(drink['id'], 0))
                item.update(score=score, reasons=reasons or ['Available now', 'Ready to personalize'],
                            headline=headline, description=description)
                ranked.append(item)
            ranked.sort(key=lambda obj: (-obj['score'], obj['id']))
            return {'recommendations': ranked[:3], 'context_source': 'Manual weather and mood simulation',
                    'engine': 'Local deterministic scoring (no camera or cloud LLM)'}

    @app.post('/api/admin/login')
    def admin_login(data: PinIn) -> dict[str, str]:
        """Check technician PIN and audit failure; issue admin-only token or raise 401 (R13)."""
        with connection(path) as db:
            stored = db.execute('SELECT pin_hash FROM admin_config WHERE id=1').fetchone()
            if not verify_password(data.pin, stored['pin_hash']):
                log_event(db, 'ADMIN_DENIED', 'Incorrect technician PIN')
                # Deliberately log and commit on failed PIN: do not raise inside transaction.
                result = None
            else:
                log_event(db, 'ADMIN_LOGIN', 'Technician entered protected mode')
                result = issue_session(db, 'technician', None)
        if result is None:
            raise HTTPException(401, 'Incorrect technician PIN')
        return {'token': result, 'role': 'technician'}

    @app.get('/api/admin/status')
    def admin_status(authorization: str | None = Header(None)) -> dict[str, Any]:
        """Return technician-only stock, waste, faults and safety alerts (R14)."""
        with connection(path) as db:
            session_for(db, authorization, 'technician')
            items = [dict(r) for r in db.execute('SELECT * FROM ingredients ORDER BY name')]
            waste = dict(db.execute('SELECT bin_level,bin_capacity FROM machine WHERE id=1').fetchone())
            faults = active_faults(db)
            alerts = ([f'Low stock: {r["name"]}' for r in items if r['quantity'] <= r['threshold']]
                      + (['Waste bin full or near capacity'] if waste['bin_level'] + 8 > waste['bin_capacity'] else [])
                      + [f'Active fault: {f["message"]}' for f in faults])
            return {'ingredients': items, 'waste': waste, 'faults': faults, 'alerts': alerts,
                    'simulation': 'Stock counters and faults are simulated, not hardware sensor readings.'}

    @app.post('/api/admin/ingredients/{name}/refill')
    def refill(name: str, data: RefillIn, authorization: str | None = Header(None)) -> dict[str, Any]:
        """Increase chosen simulated ingredient counter for authenticated technician; return updated quantity (R15)."""
        with connection(path) as db:
            session_for(db, authorization, 'technician')
            cur = db.execute('UPDATE ingredients SET quantity=quantity+? WHERE name=?', (data.amount, name))
            if cur.rowcount == 0:
                raise HTTPException(404, 'Unknown ingredient')
            quantity = db.execute('SELECT quantity FROM ingredients WHERE name=?', (name,)).fetchone()['quantity']
            log_event(db, 'REFILL', f'{name}+{data.amount}')
            return {'name': name, 'quantity': quantity}

    @app.post('/api/admin/bin/empty')
    def empty_bin(authorization: str | None = Header(None)) -> dict[str, int]:
        """Reset simulated waste bin to zero for authenticated technician; return new level (R15)."""
        with connection(path) as db:
            session_for(db, authorization, 'technician')
            db.execute('UPDATE machine SET bin_level=0 WHERE id=1')
            log_event(db, 'BIN_EMPTIED', 'Waste container emptied')
            return {'bin_level': 0}

    @app.post('/api/admin/bin/fill')
    def fill_bin(data: BinFillIn, authorization: str | None = Header(None)) -> dict[str, int]:
        """Simulate accumulating waste for evaluation; return new capped level (R14 test fixture)."""
        with connection(path) as db:
            session_for(db, authorization, 'technician')
            db.execute('UPDATE machine SET bin_level=MIN(bin_capacity,bin_level+?) WHERE id=1', (data.amount,))
            level = db.execute('SELECT bin_level FROM machine WHERE id=1').fetchone()['bin_level']
            log_event(db, 'DEMO_BIN_FILL', f'new_level={level}')
            return {'bin_level': level}

    @app.post('/api/admin/faults', status_code=201)
    def add_fault(data: FaultIn, authorization: str | None = Header(None)) -> dict[str, Any]:
        """Inject demo machine fault for technician monitoring; return new fault ID (R14)."""
        with connection(path) as db:
            session_for(db, authorization, 'technician')
            cur = db.execute('INSERT INTO faults(message,active,created_at) VALUES(?,1,?)',
                             (data.message, int(time.time())))
            log_event(db, 'FAULT_INJECTED', f'id={cur.lastrowid} {data.message}')
            return {'id': cur.lastrowid, 'active': True}

    @app.post('/api/admin/faults/{fault_id}/resolve')
    def resolve_fault(fault_id: int, authorization: str | None = Header(None)) -> dict[str, Any]:
        """Resolve existing simulated fault as technician; return ID and inactive status (R14)."""
        with connection(path) as db:
            session_for(db, authorization, 'technician')
            cur = db.execute('UPDATE faults SET active=0 WHERE id=? AND active=1', (fault_id,))
            if cur.rowcount == 0:
                raise HTTPException(404, 'Active fault not found')
            log_event(db, 'FAULT_RESOLVED', f'id={fault_id}')
            return {'id': fault_id, 'active': False}

    @app.get('/api/admin/events')
    def events(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
        """Fetch last 40 audit records for technician; return descending event dictionaries."""
        with connection(path) as db:
            session_for(db, authorization, 'technician')
            return [dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 40')]

    return app


app = create_app()
