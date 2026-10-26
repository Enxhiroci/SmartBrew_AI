"""Receipt PDF access, content and repeat-purchase backend regressions."""
from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader


def test_receipt_pdf_is_downloadable_and_itemized(client):
    """Order once; protected download contains correct complete receipt and attachment headers."""
    order = client.post('/api/orders', json={
        'beverage_id': 2, 'receipt_method': 'email_preview',
        'receipt_email': 'student@example.org',
        'customization': {'milk': 'oat', 'strength': 'strong', 'temperature': 'iced',
                          'syrup': 'vanilla', 'size': 'large'},
    }).json()
    url = f"/api/orders/{order['id']}/receipt.pdf?tracking_token={order['tracking_token']}"
    assert client.get(url.split('?')[0]).status_code in (401, 403)
    assert client.get(f"/api/orders/{order['id']}/receipt.pdf?tracking_token=wrong").status_code == 403
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/pdf'
    assert 'attachment;' in response.headers['content-disposition']
    assert response.headers['cache-control'] == 'no-store'
    assert response.content.startswith(b'%PDF-')
    parsed = PdfReader(BytesIO(response.content))
    assert len(parsed.pages) == 1
    text = parsed.pages[0].extract_text()
    for expected in (order['receipt']['reference'], 'Latte', 'oat', 'strong', 'iced',
                     'vanilla', 'large', 'student@example.org', 'PREVIEW', 'NOT SENT', f"EUR {order['receipt']['amount']:.2f}"):
        assert expected in text, (expected, text)
    inline = client.get(url + '&inline=true')
    assert inline.status_code == 200
    assert 'inline;' in inline.headers['content-disposition']
    assert inline.content.startswith(b'%PDF-')


def test_customer_can_order_again_after_first_is_ready(client):
    """Create two different consecutive purchases; each tracks independently and counts stock exactly twice."""
    first = client.post('/api/orders', json={'beverage_id': 1, 'receipt_method': 'qr'})
    assert first.status_code == 201
    first_order = first.json()
    second = client.post('/api/orders', json={'beverage_id': 2, 'receipt_method': 'qr'})
    assert second.status_code == 201, second.text
    second_order = second.json()
    assert first_order['id'] != second_order['id']
    for order in (first_order, second_order):
        url = f"/api/orders/{order['id']}?tracking_token={order['tracking_token']}"
        assert client.get(url).status_code == 200
        pdf = client.get(f"/api/orders/{order['id']}/receipt.pdf?tracking_token={order['tracking_token']}")
        assert pdf.status_code == 200
        assert order['receipt']['reference'] in PdfReader(BytesIO(pdf.content)).pages[0].extract_text()
    assert client.get('/api/catalog').status_code == 200
