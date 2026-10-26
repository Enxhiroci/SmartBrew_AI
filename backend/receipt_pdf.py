"""Create a one-page downloadable receipt from trusted server-side order data.

The resulting PDF is a proof of a *simulated* transaction, not a tax invoice.
No browser-print dependency or external PDF service is required.
"""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image
from backend.qr_receipts import generate_qr_png


# ReportLab bundles this portable TTF, so the PDF works on Windows without OS fonts.
_FONT_FILE = Path(reportlab.__file__).resolve().parent / 'fonts' / 'Vera.ttf'
if _FONT_FILE.is_file():
    pdfmetrics.registerFont(TTFont('SmartBrewVera', str(_FONT_FILE)))
    _FONT = 'SmartBrewVera'
else:
    _FONT = 'Helvetica'


def build_receipt_pdf(receipt: dict) -> bytes:
    """Render receipt data to a PDF document; input server receipt dict, output PDF bytes."""
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, topMargin=24 * mm, bottomMargin=23 * mm,
                            leftMargin=25 * mm, rightMargin=25 * mm,
                            title=f"SmartBrew receipt {receipt['reference']}",
                            author='SmartBrew AI educational prototype')
    primary = colors.HexColor('#234A32')
    subtle = colors.HexColor('#677A6D')
    pale = colors.HexColor('#F1F7EF')
    header = ParagraphStyle('Header', fontName=_FONT, fontSize=22, leading=29, textColor=primary)
    sub = ParagraphStyle('Sub', fontName=_FONT, fontSize=10, leading=15, textColor=subtle)
    caption = ParagraphStyle('Caption', fontName=_FONT, fontSize=9.5, leading=15, textColor=primary)
    value = ParagraphStyle('Value', fontName=_FONT, fontSize=10, leading=15, textColor=colors.HexColor('#22362A'))
    tiny = ParagraphStyle('Note', fontName=_FONT, fontSize=8.7, leading=15, textColor=subtle)
    field_labels = {
        'milk': 'Milk', 'strength': 'Strength', 'temperature': 'Temperature',
        'syrup': 'Syrup', 'size': 'Size',
    }

    def paragraph(text: object, style: ParagraphStyle) -> Paragraph:
        """Escape printable field value; input value and style, output safe Paragraph."""
        return Paragraph(escape(str(text if text is not None else '—')), style)

    rows = [
        ('Receipt number', receipt['reference']),
        ('Date (UTC)', receipt['created_at']),
        ('Beverage', receipt['drink']),
    ]
    options = receipt.get('customization') or {}
    rows.extend((label, options.get(key, '—')) for key, label in field_labels.items())
    rows.append(('Payment method', str(receipt.get('payment_method', '')).replace('_', ' ').title()))
    rows.append(('Payment details', receipt.get('payment_description') or 'Demo transaction'))
    rows.append(('Payment status', 'Approved (simulation)'))
    if receipt.get('email_to') and receipt.get('method') in {'email', 'email_preview'}:
        rows.append(('Email recipient', receipt['email_to']))
        rows.append(('Email status', 'Preview only — NOT SENT' if receipt['method'] == 'email_preview' else
                     str(receipt.get('email_status', 'not sent')).replace('_', ' ').title()))
    qr_selected = receipt.get('method') == 'qr'
    total = f"EUR {float(receipt['amount']):.2f}"
    table_rows = [[paragraph(k, caption), paragraph(v, value)] for k, v in rows]
    table_rows.append([paragraph('TOTAL PAID (SIMULATED)', caption), paragraph(total, value)])
    table = Table(table_rows, colWidths=[60 * mm, 97 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5 if qr_selected else 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5 if qr_selected else 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 0), (-1, -2), .35, colors.HexColor('#D9E5D7')),
        ('BACKGROUND', (0, -1), (-1, -1), pale),
        ('TOPPADDING', (0, -1), (-1, -1), 10 if qr_selected else 14),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 10 if qr_selected else 14),
    ]))
    notice = ('EMAIL PREVIEW ONLY — THIS EMAIL WAS NOT SENT.' if receipt.get('method') == 'email_preview'
              else 'SIMULATED RECEIPT — NOT A TAX INVOICE.')
    logo_path = Path(__file__).resolve().parent.parent / 'frontend' / 'smartbrew-logo.png'
    brand_header = Table([[Image(str(logo_path), width=18 * mm, height=17 * mm),
                           Paragraph('SMARTBREW AI', header)]],
                         colWidths=[23 * mm, 133 * mm], hAlign='LEFT')
    brand_header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                      ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                      ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                      ('TOPPADDING', (0, 0), (-1, -1), 0),
                                      ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    story = [
        brand_header,
        Spacer(1, 3 * mm),
        paragraph('Order receipt · Software Engineering Lab 3', sub),
        Spacer(1, (7 if qr_selected else 10) * mm),
        table,
        Spacer(1, (7 if qr_selected else 11) * mm),
        paragraph(notice, caption),
        Spacer(1, 2 * mm),
        paragraph('Educational demonstration only: no real charge or beverage preparation occurred. '
                  'VAT is not calculated. This document does not establish a commercial sale.', tiny),
    ]
    if receipt.get('method') == 'qr':
        # A genuinely scannable QR embeds a non-sensitive offline receipt summary.
        qr_image = Image(BytesIO(generate_qr_png(receipt)), width=39 * mm, height=39 * mm)
        qr_image.hAlign = 'CENTER'
        story.extend([Spacer(1, 7 * mm), paragraph('SCAN YOUR QR RECEIPT', caption),
                      Spacer(1, 3 * mm), qr_image,
                      Spacer(1, 2 * mm), paragraph('Works without internet. Contains order summary only, never card details or access tokens.', tiny)])
    doc.build(story)
    return output.getvalue()
