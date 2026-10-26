"""Automated order-timing, full-preview, SMTP and retry regression tests."""
from __future__ import annotations

import os

from backend.main import connection
from backend import receipts


def test_automatic_brewing_progress_without_button(client):
    """Given a paid order, advance clock via DB timestamps; verify automatic queued→brewing→ready."""
    created = client.post('/api/orders', json={'beverage_id': 1, 'receipt_method': 'qr'}).json()
    token = created['tracking_token']
    url = f"/api/orders/{created['id']}?tracking_token={token}"
    assert client.get(url).json()['status'] == 'queued'
    path = client.app.state.db_path
    with connection(path) as db:
        db.execute('UPDATE orders SET created_at=created_at-5 WHERE id=?', (created['id'],))
    assert client.get(url).json()['status'] == 'brewing'
    with connection(path) as db:
        db.execute('UPDATE orders SET created_at=created_at-9 WHERE id=?', (created['id'],))
    status = client.get(url).json()
    assert status['status'] == 'ready'
    assert status['receipt']['reference'].startswith('SB-')
    assert status['receipt']['drink'] == 'Espresso'
    assert status['receipt']['amount'] == 2.30
    assert status['receipt']['customization']['strength'] == 'regular'
    assert status['receipt']['payment_method'] == 'bank_card'
    assert client.get(url).json()['status'] == 'ready'


def test_email_requires_valid_recipient(client):
    """Email choice must provide a syntactically valid address or result in 422 without ordering."""
    for payload in [
        {'beverage_id': 1, 'receipt_method': 'email'},
        {'beverage_id': 1, 'receipt_method': 'email', 'receipt_email': 'not-an-address'},
    ]:
        assert client.post('/api/orders', json=payload).status_code == 422


def test_email_not_configured_still_places_order_and_preview(client, monkeypatch):
    """SMTP absent yields clear unsent state while receipt preview and order stay available."""
    for name in ('SMARTBREW_SMTP_HOST', 'SMARTBREW_SMTP_FROM', 'SMARTBREW_SMTP_USER', 'SMARTBREW_SMTP_PASSWORD'):
        monkeypatch.delenv(name, raising=False)
    result = client.post('/api/orders', json={
        'beverage_id': 2, 'receipt_method': 'email', 'receipt_email': 'buyer@example.org',
        'customization': {'milk': 'oat', 'temperature': 'iced', 'size': 'large'},
    })
    assert result.status_code == 201, result.text
    receipt = result.json()['receipt']
    assert receipt['email_status'] == 'not_configured'
    assert receipt['email_to'] == 'buyer@example.org'
    assert receipt['amount'] == 4.90
    assert receipt['customization']['milk'] == 'oat'
    assert 'not sent' in receipt['message'].lower()
    token = result.json()['tracking_token']
    assert client.get(f"/api/orders/{result.json()['id']}?tracking_token={token}").status_code == 200
    assert client.post(f"/api/orders/{result.json()['id']}/email-receipt").status_code == 403


def test_real_smtp_attempt_and_retry_without_duplicate_order(client, monkeypatch, technician):
    """Mock SMTP success/failure, verify authenticated retry and no repeat ingredient deduction."""
    monkeypatch.setenv('SMARTBREW_SMTP_HOST', 'smtp.example.org')
    monkeypatch.setenv('SMARTBREW_SMTP_FROM', 'smartbrew@example.org')
    monkeypatch.setenv('SMARTBREW_SMTP_USER', 'smartbrew@example.org')
    monkeypatch.setenv('SMARTBREW_SMTP_PASSWORD', 'test-only')
    calls = []

    def fake_send(address, receipt):
        """Mock network sender; input destination and receipt, return None after recording attempt."""
        calls.append((address, receipt['reference']))
        if len(calls) == 1:
            raise OSError('Provider unavailable')

    monkeypatch.setattr('backend.main.send_receipt', fake_send)
    initial_stock = client.get('/api/admin/status', headers=technician).json()
    response = client.post('/api/orders', json={'beverage_id': 1,
        'receipt_method': 'email', 'receipt_email': 'buyer@example.org'})
    assert response.status_code == 201
    order = response.json()
    assert order['receipt']['email_status'] == 'failed'
    url = f"/api/orders/{order['id']}/email-receipt?tracking_token={order['tracking_token']}"
    assert client.post(url).json()['receipt']['email_status'] == 'sent'
    assert client.post(url).json()['receipt']['email_status'] == 'sent'  # idempotent
    assert len(calls) == 2
    final_stock = client.get('/api/admin/status', headers=technician).json()
    get_beans = lambda stock: next(x['quantity'] for x in stock['ingredients'] if x['name'] == 'beans')
    assert get_beans(initial_stock) - get_beans(final_stock) == 18


def test_smtp_message_contains_real_receipt_data(monkeypatch):
    """Intercept STARTTLS SMTP to verify message contents and TLS credential path without network."""
    for key, value in {
        'SMARTBREW_SMTP_HOST':'smtp.example.org','SMARTBREW_SMTP_FROM':'sales@example.org',
        'SMARTBREW_SMTP_USER':'sales@example.org','SMARTBREW_SMTP_PASSWORD':'fake-password',
        'SMARTBREW_SMTP_SECURITY':'starttls','SMARTBREW_SMTP_PORT':'587',
    }.items():
        monkeypatch.setenv(key, value)
    tracked = {}

    class FakeSMTP:
        """Simulated SMTP transport with context-manager API and captured deliveries."""
        def __init__(self, host, port, timeout):
            """Capture connection target; input host, port and timeout, return None."""
            tracked.update(host=host, port=port, timeout=timeout)
        def __enter__(self):
            """Return fake SMTP connection; no arguments, output self."""
            return self
        def __exit__(self, exc_type, exc, tb):
            """Release fake SMTP connection; input exception tuple, return None."""
            return None
        def ehlo(self):
            """Simulate ESMTP greeting; no inputs, return None."""
            return None
        def starttls(self):
            """Record STARTTLS initiation; no inputs, return None."""
            tracked['tls'] = True
        def login(self, username, password):
            """Verify passed credentials; input strings, return None."""
            tracked['authenticated'] = username == 'sales@example.org' and password == 'fake-password'
        def send_message(self, msg):
            """Record message for body assertions; input EmailMessage, return None."""
            tracked['message'] = msg

    monkeypatch.setattr(receipts.smtplib, 'SMTP', FakeSMTP)
    document = {
        'reference':'SB-000011','created_at':'2026-10-25T15:00:00+00:00',
        'drink':'Caffè Latte','amount':4.20,'payment_method':'bank_card',
        'customization':{'milk':'oat','strength':'strong','temperature':'hot','syrup':'none','size':'medium'},
    }
    receipts.send_receipt('buyer@example.org', document)
    assert tracked['tls'] and tracked['authenticated']
    msg = tracked['message']
    assert msg['To'] == 'buyer@example.org'
    plain = msg.get_body(preferencelist=('plain',)).get_content()
    assert 'SB-000011' in plain and 'Caffè Latte' in plain and 'EUR 4.20' in plain
    assert 'No actual charge' in plain


def test_email_preview_never_contacts_smtp(client, monkeypatch):
    """Preview mode stores a complete sample email but never invokes an SMTP delivery function."""
    def forbidden_send(recipient, receipt):
        """Fail if called; inputs recipient and receipt, return never."""
        raise AssertionError('Email preview must not send email')
    monkeypatch.setattr('backend.main.send_receipt', forbidden_send)
    payload = {
        'beverage_id': 2, 'receipt_method': 'email_preview',
        'receipt_email': 'student@example.org',
        'customization': {'milk': 'oat', 'strength': 'strong', 'temperature': 'iced', 'size': 'large'},
    }
    response = client.post('/api/orders', json=payload)
    assert response.status_code == 201, response.text
    order = response.json()
    receipt = order['receipt']
    assert receipt['method'] == 'email_preview'
    assert receipt['email_status'] == 'preview_only'
    assert receipt['email_to'] == 'student@example.org'
    assert receipt['email_attempts'] == 0
    assert 'no email was sent' in receipt['message'].lower()
    assert receipt['customization']['milk'] == 'oat'
    assert receipt['amount'] > 0
    track = client.get(f"/api/orders/{order['id']}?tracking_token={order['tracking_token']}")
    assert track.status_code == 200
    assert track.json()['receipt']['email_status'] == 'preview_only'
    retry = client.post(f"/api/orders/{order['id']}/email-receipt?tracking_token={order['tracking_token']}")
    assert retry.status_code == 409


def test_email_preview_requires_valid_recipient(client):
    """Preview-only email fields require valid address formatting without triggering delivery."""
    assert client.post('/api/orders', json={'beverage_id': 1, 'receipt_method': 'email_preview'}).status_code == 422
    assert client.post('/api/orders', json={'beverage_id': 1, 'receipt_method': 'email_preview', 'receipt_email': 'bad-email'}).status_code == 422
