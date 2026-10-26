"""Scannable, fully offline demo receipt QR: no customer data, tokens or payment credentials."""
from __future__ import annotations
from io import BytesIO
from typing import Any
import qrcode


def qr_receipt_text(receipt: dict[str, Any]) -> str:
    """Convert trusted receipt fields to readable QR text; input receipt dictionary, output text."""
    # Short payload deliberately optimizes phone scanning of compact on-paper PDFs.
    # Payment metadata, contact details, card suffixes and access tokens are excluded.
    date = receipt['created_at'][:16].replace('T', ' ')
    return '\n'.join([
        'SmartBrew AI - DEMO receipt',
        f"Order {receipt['reference']}",
        f"UTC {date}",
        f"{receipt['drink']} | EUR {float(receipt['amount']):.2f}",
        'SIMULATED - NOT A TAX INVOICE',
    ])


def generate_qr_png(receipt: dict[str, Any]) -> bytes:
    """Encode an order's non-sensitive receipt summary into a PNG; return PNG bytes."""
    qr = qrcode.QRCode(version=None, box_size=8, border=3, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_receipt_text(receipt))
    qr.make(fit=True)
    graphic = qr.make_image(fill_color='#234A32', back_color='white')
    out = BytesIO()
    graphic.save(out, format='PNG')
    return out.getvalue()
