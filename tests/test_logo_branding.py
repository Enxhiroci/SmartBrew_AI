"""Brand consistency checks for the kiosk and generated simulated PDF receipts."""
from pathlib import Path
from pypdf import PdfReader
from backend.receipt_pdf import build_receipt_pdf
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]

def test_logo_replaces_all_old_marks():
    """Verify the sidebar, banner, receipt preview and favicon share an asset."""
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert html.count("smartbrew-logo.png") == 3
    assert 'class="hero-brewing-logo"' in html
    assert 'cup-illustration' not in html
    assert 'cup-body' not in html
    assert 'class="receipt-mark"' in js and "smartbrew-logo.png" in js
    assert "✺" not in html and "✺" not in js
    assert (ROOT / "frontend" / "smartbrew-logo.png").exists()

def test_pdf_contains_brand_image():
    """Verify the downloadable receipt embeds the branding artwork."""
    receipt = {"reference":"SB-000007", "created_at":"2026-10-25T12:00:00Z",
        "drink":"Latte", "customization":{}, "payment_method":"bank_card",
        "method":"email_preview", "email_to":"customer@example.com", "amount":3.50}
    pdf = PdfReader(BytesIO(build_receipt_pdf(receipt)))
    assert len(pdf.pages) == 1
    assert pdf.pages[0].images
    assert 'SB-000007' in pdf.pages[0].extract_text()


def test_symbol_only_is_transparent_and_used_in_main_hero():
    """Require a real RGBA symbol-only asset used directly in hero markup; return None."""
    import struct
    asset = ROOT / 'frontend' / 'smartbrew-logo.png'
    content = asset.read_bytes()
    assert content.startswith(b'\x89PNG\r\n\x1a\n')
    width, height, bit_depth, color_type = struct.unpack('>IIBB', content[16:26])
    assert color_type == 6  # PNG RGBA supports a genuinely transparent background.
    assert bit_depth == 8
    assert 0 < width < 1000 and 0 < height < 1000
    html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
    assert 'class="hero-brewing-logo"' in html
    assert 'cup-illustration' not in html
