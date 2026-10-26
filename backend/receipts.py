"""Optional SMTP delivery for SmartBrew's simulated-payment transactional receipts.

Only receipts are real emails: the payments and drink preparation remain simulated.
SMTP credentials are loaded from environment/.env and never returned to clients.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from html import escape


def smtp_is_configured() -> bool:
    """Check required environment settings; no parameters, return True if SMTP is configured."""
    return all(os.getenv(key, '').strip() for key in (
        'SMARTBREW_SMTP_HOST', 'SMARTBREW_SMTP_FROM',
        'SMARTBREW_SMTP_USER', 'SMARTBREW_SMTP_PASSWORD',
    ))


def send_receipt(recipient: str, receipt: dict) -> None:
    """Send a plaintext/HTML receipt using TLS SMTP; input address and receipt object, return None or raise SMTP error."""
    if not smtp_is_configured():
        raise RuntimeError('SMTP is not configured')
    host = os.environ['SMARTBREW_SMTP_HOST'].strip()
    security = os.getenv('SMARTBREW_SMTP_SECURITY', 'starttls').strip().lower()
    if security not in {'ssl', 'starttls'}:
        raise ValueError('SMTP security must be ssl or starttls')
    port = int(os.getenv('SMARTBREW_SMTP_PORT', '465' if security == 'ssl' else '587'))
    sender = os.environ['SMARTBREW_SMTP_FROM'].strip()
    username = os.environ['SMARTBREW_SMTP_USER'].strip()
    password = os.environ['SMARTBREW_SMTP_PASSWORD']

    message = EmailMessage()
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = f"SmartBrew receipt {receipt['reference']} — simulated payment"
    lines = [
        'SMARTBREW AI — ORDER RECEIPT',
        f"Order: {receipt['reference']}",
        f"Date (UTC): {receipt['created_at']}",
        f"Beverage: {receipt['drink']}",
        f"Milk: {receipt['customization']['milk']}",
        f"Strength: {receipt['customization']['strength']}",
        f"Temperature: {receipt['customization']['temperature']}",
        f"Syrup: {receipt['customization']['syrup']}",
        f"Size: {receipt['customization']['size']}",
        f"Payment method: {receipt['payment_method'].replace('_', ' ')}",
        f"Payment details: {receipt.get('payment_description', 'Demo transaction')}",
        f"Total: EUR {receipt['amount']:.2f}",
        '',
        'EDUCATIONAL SIMULATION: No actual charge or beverage preparation occurred.',
        'This is not a tax invoice; VAT is not calculated.',
    ]
    message.set_content('\n'.join(lines))
    rows = ''.join(f'<tr><th style="text-align:left;padding:7px">{escape(k)}</th>'
                   f'<td style="padding:7px">{escape(str(v))}</td></tr>' for k, v in [
        ('Order number', receipt['reference']), ('Date (UTC)', receipt['created_at']),
        ('Beverage', receipt['drink']),
        *[(k.title(), v) for k, v in receipt['customization'].items()],
        ('Payment method', receipt['payment_method'].replace('_', ' ')),
        ('Payment details', receipt.get('payment_description', 'Demo transaction')),
        ('Total', f"EUR {receipt['amount']:.2f}"),
    ])
    message.add_alternative(f'''<html><body style="font:15px Arial,sans-serif;color:#203d2a;max-width:560px">
      <h1>SmartBrew AI</h1><p>Thank you for trying our demo kiosk.</p>
      <table style="border-collapse:collapse;width:100%">{rows}</table>
      <p style="background:#f1f6ec;padding:14px"><strong>Educational simulation:</strong>
      No real payment or beverage preparation. Not a tax invoice; VAT is not calculated.</p>
      </body></html>''', subtype='html')
    if security == 'ssl':
        with smtplib.SMTP_SSL(host, port, timeout=8) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=8) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(username, password)
            server.send_message(message)
