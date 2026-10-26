"""Payment-method details and actual scannable QR for simulated receipts (R04)."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader
from PIL import Image
import pytest
from backend.qr_receipts import qr_receipt_text


def test_card_details_on_receipt_and_pdf(client):
    """Record only a masked demo card reference on order, PDF and tracking views."""
    order = client.post('/api/orders', json={
        'beverage_id': 1, 'payment_method': 'bank_card',
        'payment_details': {'brand': 'Mastercard', 'last4': '9876'},
        'receipt_method': 'qr',
    })
    assert order.status_code == 201, order.text
    result = order.json()
    assert result['receipt']['payment_description'] == 'Mastercard demo card •••• 9876'
    pdf = PdfReader(BytesIO(client.get(
        f"/api/orders/{result['id']}/receipt.pdf?tracking_token={result['tracking_token']}"
    ).content))
    assert len(pdf.pages) == 1
    assert len(pdf.pages[0].images) >= 2  # brewing logo AND real QR
    text = pdf.pages[0].extract_text()
    assert 'Payment details' in text
    assert '9876' in text
    assert 'SCAN YOUR QR RECEIPT' in text


def test_wallet_and_employee_details(client):
    """Validate wallet approval and demo employee PIN; do not expose or save secret PIN."""
    wallet_rejected = client.post('/api/orders', json={
        'beverage_id': 1, 'payment_method': 'mobile_wallet',
        'payment_details': {'wallet': 'Google Pay', 'confirmed': 'no'},
    })
    assert wallet_rejected.status_code == 422
    wallet = client.post('/api/orders', json={
        'beverage_id': 1, 'payment_method': 'mobile_wallet',
        'payment_details': {'wallet': 'Google Pay', 'confirmed': 'yes'},
    })
    assert wallet.status_code == 201, wallet.text
    assert 'Google Pay' in wallet.json()['receipt']['payment_description']
    emp_bad = client.post('/api/orders', json={
        'beverage_id': 1, 'payment_method': 'employee_card',
        'payment_details': {'badge': 'EMP-1001', 'demo_pin': '0000'},
    })
    assert emp_bad.status_code == 402
    employee = client.post('/api/orders', json={
        'beverage_id': 1, 'payment_method': 'employee_card',
        'payment_details': {'badge': 'EMP-1001', 'demo_pin': '1357'},
    })
    assert employee.status_code == 201, employee.text
    assert employee.json()['receipt']['payment_description'] == 'Employee demo card EMP-1001'
    assert '1357' not in str(employee.json())


def test_qr_png_protected_and_contains_real_receipt_data(client):
    """QR PNG is readable and scoped to a tracked QR order; never contains tokens."""
    res = client.post('/api/orders', json={'beverage_id': 2, 'receipt_method': 'qr'})
    assert res.status_code == 201
    order = res.json()
    path = f"/api/orders/{order['id']}/receipt-qr.png"
    assert client.get(path).status_code == 403
    assert client.get(path + '?tracking_token=incorrect').status_code == 403
    img_resp = client.get(path + '?tracking_token=' + order['tracking_token'])
    assert img_resp.status_code == 200
    assert img_resp.headers['content-type'] == 'image/png'
    assert img_resp.content.startswith(b'\x89PNG\r\n\x1a\n')
    img = Image.open(BytesIO(img_resp.content))
    assert img.width >= 250 and img.height >= 250
    payload = qr_receipt_text(order['receipt'])
    assert order['receipt']['reference'] in payload
    assert 'EUR' in payload and 'Latte' in payload
    assert order['tracking_token'] not in payload
    assert 'NOT A TAX INVOICE' in payload


def test_no_qr_for_email_receipt(client):
    """Ensure QR route only exists when customer actually selects QR receipt."""
    order = client.post('/api/orders', json={
        'beverage_id': 1, 'receipt_method': 'email_preview', 'receipt_email': 'student@example.org'
    }).json()
    result = client.get(f"/api/orders/{order['id']}/receipt-qr.png?tracking_token={order['tracking_token']}")
    assert result.status_code == 404


def test_frontend_has_method_specific_and_qr_sections():
    """HTML and controller expose all payment choices and actual QR image."""
    root = Path(__file__).resolve().parents[1]
    html = (root / 'frontend/index.html').read_text(encoding='utf-8')
    js = (root / 'frontend/app.js').read_text(encoding='utf-8')
    for item in ('bank-card-fields', 'wallet-fields', 'employee-fields', 'qr-choice-note', 'download-qr'):
        assert f'id="{item}"' in html
    for item in ('updatePaymentChoice', 'paymentDetails', 'receipt-qr.png', 'qrMarkup'):
        assert item in js


def test_payment_description_in_private_customer_history(client, customer):
    """Authenticated owner sees masked method in history, never credentials or PIN."""
    result = client.post('/api/orders', headers=customer, json={
        'beverage_id': 1, 'payment_method': 'employee_card',
        'payment_details': {'badge': 'EMP-5555', 'demo_pin': '1357'},
        'receipt_method': 'qr',
    })
    assert result.status_code == 201
    history = client.get('/api/my/orders', headers=customer)
    assert history.status_code == 200
    assert history.json()[0]['payment_description'] == 'Employee demo card EMP-5555'
    assert '1357' not in str(history.json())
