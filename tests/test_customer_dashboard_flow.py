"""Customer journey tests: explicit saved recipe vs checkout, preference use and private purchase history."""
from __future__ import annotations


def test_saving_recipe_does_not_create_purchase_or_overwrite_preferences(client, customer):
    """Create/edit named drink without placing orders; input fixture clients, return None (R07/R09)."""
    settings = {'milk_type': 'oat', 'coffee_strength': 'strong', 'temperature': 'iced', 'syrup_preference': 'caramel'}
    assert client.put('/api/preferences', json=settings, headers=customer).status_code == 200
    created = client.post('/api/recipes', headers=customer, json={
        'name': 'My iced oat latte', 'beverage_id': 2,
        'customization': {'milk': 'oat', 'strength': 'strong', 'temperature': 'iced',
                          'syrup': 'caramel', 'size': 'large'},
    })
    assert created.status_code == 201
    assert client.get('/api/my/orders', headers=customer).json() == []
    recipe_id = created.json()['id']
    modified = client.put(f'/api/recipes/{recipe_id}', headers=customer, json={
        'name': 'Weekend oat latte', 'beverage_id': 2,
        'customization': {'milk': 'oat', 'strength': 'mild', 'temperature': 'warm',
                          'syrup': 'none', 'size': 'small'},
    })
    assert modified.status_code == 200
    recipes = client.get('/api/recipes', headers=customer).json()
    assert len(recipes) == 1 and recipes[0]['name'] == 'Weekend oat latte'
    assert recipes[0]['customization']['strength'] == 'mild'
    assert client.get('/api/me', headers=customer).json()['preferences'] == settings
    assert client.get('/api/my/orders', headers=customer).json() == []


def test_dashboard_history_updates_after_paid_order_and_reorder(client, customer):
    """Verify owned orders show their saved customizations and stay after repeat; return None (R03/R09)."""
    assert client.get('/api/my/orders').status_code == 401
    one = client.post('/api/orders', headers=customer, json={
        'beverage_id': 2, 'customization': {'milk': 'oat', 'strength': 'strong',
                                           'temperature': 'iced', 'syrup': 'vanilla', 'size': 'large'},
    })
    assert one.status_code == 201, one.text
    history = client.get('/api/my/orders', headers=customer).json()
    assert len(history) == 1
    assert history[0]['reference'] == f"SB-{one.json()['id']:06d}"
    assert history[0]['customization']['milk'] == 'oat'
    assert history[0]['customization']['size'] == 'large'
    assert history[0]['payment_status'] == 'approved_simulated'
    two = client.post('/api/orders', headers=customer, json={
        'beverage_id': history[0]['beverage_id'], 'customization': history[0]['customization'],
    })
    assert two.status_code == 201, two.text
    recent = client.get('/api/my/orders', headers=customer).json()
    assert len(recent) == 2
    assert recent[0]['id'] == two.json()['id']
    assert recent[1]['id'] == one.json()['id']
    assert recent[1]['customization'] == recent[0]['customization']


def test_guest_and_other_customer_orders_are_private(client, customer):
    """Require owner authentication; guest purchases and other accounts are not in history (R09)."""
    guest = client.post('/api/orders', json={'beverage_id': 1})
    assert guest.status_code == 201
    owned = client.post('/api/orders', headers=customer, json={'beverage_id': 1})
    assert owned.status_code == 201
    other = client.post('/api/register', json={'name': 'Other', 'email': 'other@example.org', 'password': 'SafePass1234'})
    assert other.status_code == 201
    other_auth = {'Authorization': f"Bearer {other.json()['token']}"}
    assert client.get('/api/my/orders', headers=other_auth).json() == []
    history = client.get('/api/my/orders', headers=customer).json()
    assert len(history) == 1 and history[0]['id'] == owned.json()['id']
    assert client.get(f"/api/orders/{owned.json()['id']}", headers=other_auth).status_code == 403


def test_order_history_contributes_to_recommendations_without_overwriting_defaults(client, customer):
    """Order frequency changes explanatory ranking; profile preferences remain separately controlled (R07/R10)."""
    baseline = client.post('/api/recommendations', headers=customer, json={}).json()['recommendations']
    assert client.post('/api/orders', headers=customer, json={'beverage_id': 6, 'customization': {'temperature': 'iced'}}).status_code == 201
    after = client.post('/api/recommendations', headers=customer, json={}).json()['recommendations']
    iced = next(r for r in after if r['id'] == 6)
    assert iced['score'] > next(r for r in baseline if r['id'] == 6)['score'] if any(r['id'] == 6 for r in baseline) else iced['score'] >= 12
    assert any('Picked before: 1×' in msg for msg in iced['reasons'])
    assert client.get('/api/me', headers=customer).json()['preferences']['milk_type'] == 'dairy'
