"""Executable acceptance tests of ten SmartBrew Lab 2-mapped prototype features."""
from __future__ import annotations


def test_01_menu_category_nutrition_and_prices(client):
    """Check R01 menu displays category, nutritional information, price and availability; returns None."""
    data = client.get('/api/catalog')
    assert data.status_code == 200
    drinks = data.json()
    assert len(drinks) == 6
    assert all(isinstance(d['price'], (int, float)) and 'calories' in d and 'available' in d for d in drinks)
    assert {'Coffee', 'Tea', 'Cold drinks'} <= {d['category'] for d in drinks}


def test_02_customization_validates_and_calculates_stock(client):
    """Check R02 quote reflects milk, strength, syrup and size and rejects unsupported temperature; returns None."""
    payload = {'beverage_id': 2, 'customization': {
        'milk': 'oat', 'strength': 'strong', 'temperature': 'iced', 'syrup': 'vanilla', 'size': 'large'
    }}
    quote = client.post('/api/quote', json=payload)
    assert quote.status_code == 200, quote.text
    obj = quote.json()
    assert obj['price'] == 5.20
    assert obj['ingredients']['milk_oat'] > 180
    assert obj['ingredients']['beans'] > 18
    assert obj['ingredients']['vanilla_syrup'] > 0
    invalid = client.post('/api/quote', json={'beverage_id': 1, 'customization': {'temperature': 'iced'}})
    assert invalid.status_code == 422


def test_03_order_preparation_state_and_single_deduction(client, technician):
    """Check R03 order cycles queued/brewing/ready without double charging stock; returns None."""
    before = client.get('/api/admin/status', headers=technician).json()
    beans_before = next(i['quantity'] for i in before['ingredients'] if i['name'] == 'beans')
    order = client.post('/api/orders', json={'beverage_id': 1}).json()
    assert order['status'] == 'queued'
    token = order['tracking_token']
    status_path = f"/api/orders/{order['id']}?tracking_token={token}"
    advance_path = f"/api/orders/{order['id']}/advance?tracking_token={token}"
    assert client.get(status_path).json()['status'] == 'queued'
    assert client.post(advance_path).json()['status'] == 'brewing'
    assert client.post(advance_path).json()['status'] == 'ready'
    assert client.post(advance_path).json()['status'] == 'ready'
    after = client.get('/api/admin/status', headers=technician).json()
    beans_after = next(i['quantity'] for i in after['ingredients'] if i['name'] == 'beans')
    assert beans_before - beans_after == 18
    assert after['waste']['bin_level'] - before['waste']['bin_level'] == 8
    assert client.get(f"/api/orders/{order['id']}").status_code == 403


def test_04_payment_denial_and_receipt_options(client, technician):
    """Check R04 rejected simulated payment creates no order and receipts follow choice; returns None."""
    before = client.get('/api/admin/status', headers=technician).json()
    declined = client.post('/api/orders', json={'beverage_id': 2, 'payment_approved': False})
    assert declined.status_code == 402
    after = client.get('/api/admin/status', headers=technician).json()
    assert after['ingredients'] == before['ingredients']
    assert after['waste'] == before['waste']
    assert any(e['event'] == 'PAYMENT_DECLINED' for e in client.get('/api/admin/events', headers=technician).json())
    accepted = client.post('/api/orders', json={
        'beverage_id': 2, 'payment_method': 'mobile_wallet', 'receipt_method': 'email',
        'receipt_email': 'receipt@example.org'
    })
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()['receipt']['method'] == 'email'
    assert accepted.json()['receipt']['email_status'] == 'not_configured'
    assert accepted.json()['receipt']['email_to'] == 'receipt@example.org'
    assert accepted.json()['receipt']['drink'] == 'Caffè Latte'


def test_05_registration_login_and_bad_password(client):
    """Check R06 secure password authentication and duplicate identity handling; returns None."""
    data = {'name': 'Ada', 'email': 'ada@example.com', 'password': 'password-for-test'}
    assert client.post('/api/register', json=data).status_code == 201
    assert client.post('/api/register', json=data).status_code == 409
    bad = client.post('/api/login', json={'email': data['email'], 'password': 'bad'})
    assert bad.status_code == 401
    login = client.post('/api/login', json={'email': data['email'], 'password': data['password']})
    assert login.status_code == 200
    profile = client.get('/api/me', headers={'Authorization': f"Bearer {login.json()['token']}"})
    assert profile.json()['name'] == 'Ada'
    assert client.get('/api/me').status_code == 401


def test_06_persistent_preferences_and_named_recipes(client, customer):
    """Check R07 preferences/recipes persist and users cannot browse them anonymously; returns None."""
    values = {'coffee_strength': 'strong', 'milk_type': 'oat', 'temperature': 'iced', 'syrup_preference': 'vanilla'}
    assert client.put('/api/preferences', json=values, headers=customer).status_code == 200
    assert client.get('/api/me', headers=customer).json()['preferences'] == values
    assert client.get('/api/recipes').status_code == 401
    created = client.post('/api/recipes', json={'name': 'Afternoon oat', 'beverage_id': 2,
       'customization': {'milk': 'oat', 'temperature': 'iced'}}, headers=customer)
    assert created.status_code == 201, created.text
    rows = client.get('/api/recipes', headers=customer).json()
    assert len(rows) == 1 and rows[0]['name'] == 'Afternoon oat'
    edited = client.put(f"/api/recipes/{created.json()['id']}", json={'name': 'Evening oat', 'beverage_id': 2,
       'customization': {'milk': 'oat', 'temperature': 'warm'}}, headers=customer)
    assert edited.status_code == 200
    assert client.get('/api/recipes', headers=customer).json()[0]['name'] == 'Evening oat'


def test_07_context_changes_recommendation_ranking(client, customer):
    """Check R10 weather, mood, time, and saved profile can influence top suggestions; returns None."""
    rushed = client.post('/api/recommendations', json={'weather': 'mild', 'mood': 'unspecified', 'time_available_minutes': 2})
    assert rushed.status_code == 200
    assert rushed.json()['recommendations'][0]['name'] == 'Espresso'
    calm = client.post('/api/recommendations', json={'weather': 'mild', 'mood': 'calm', 'time_available_minutes': 20})
    assert calm.json()['recommendations'][0]['name'] == 'Matcha Latte'
    assert all('reasons' in rec for rec in calm.json()['recommendations'])
    profile_recs = client.post('/api/recommendations', json={'weather': 'sunny', 'mood': 'energetic', 'time_available_minutes': 10}, headers=customer)
    assert len(profile_recs.json()['recommendations']) == 3


def test_08_admin_pin_and_role_protection(client, customer, technician):
    """Check R13 admin boundary, failed PIN logging, and customer forbidden status; returns None."""
    assert client.get('/api/admin/status').status_code == 401
    assert client.get('/api/admin/status', headers=customer).status_code == 403
    assert client.post('/api/admin/login', json={'pin': 'wrong'}).status_code == 401
    audit = client.get('/api/admin/events', headers=technician).json()
    assert any(row['event'] == 'ADMIN_DENIED' for row in audit)
    assert client.get('/api/admin/status', headers=technician).status_code == 200


def test_09_monitoring_stock_waste_and_fault_blocks_sales(client, technician):
    """Check R14 low stock, waste threshold and active fault suppress ordering; returns None."""
    assert client.post('/api/admin/bin/fill', json={'amount': 100}, headers=technician).status_code == 200
    quote = client.post('/api/quote', json={'beverage_id': 1}).json()
    assert not quote['available']
    assert 'Waste bin requires emptying' in quote['blocking_reasons']
    assert client.post('/api/orders', json={'beverage_id': 1}).status_code == 409
    assert client.post('/api/admin/bin/empty', headers=technician).status_code == 200
    result = client.post('/api/admin/faults', json={'message': 'Test heater fault'}, headers=technician)
    assert result.status_code == 201
    assert all(not d['available'] for d in client.get('/api/catalog').json())
    assert client.post(f"/api/admin/faults/{result.json()['id']}/resolve", headers=technician).status_code == 200
    assert any(d['available'] for d in client.get('/api/catalog').json())


def test_10_technician_refill_bin_reset_permissions(client, customer, technician):
    """Check R15 refill and empty counters require technician role and update quantities; returns None."""
    before = client.get('/api/admin/status', headers=technician).json()
    old_qty = next(i['quantity'] for i in before['ingredients'] if i['name'] == 'beans')
    assert client.post('/api/admin/ingredients/beans/refill', json={'amount': 100}, headers=customer).status_code == 403
    response = client.post('/api/admin/ingredients/beans/refill', json={'amount': 100}, headers=technician)
    assert response.status_code == 200 and response.json()['quantity'] == old_qty + 100
    assert client.post('/api/admin/ingredients/nope/refill', json={'amount': 1}, headers=technician).status_code == 404
    assert client.post('/api/admin/bin/fill', json={'amount': 25}, headers=technician).status_code == 200
    assert client.post('/api/admin/bin/empty', headers=technician).json()['bin_level'] == 0
