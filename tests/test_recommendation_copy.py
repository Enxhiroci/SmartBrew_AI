"""Coverage for more human-readable personalized recommendation descriptions."""


def test_recommendation_copy_has_distinct_headlines_and_prose(client):
    """Verify each ranked suggestion is readable and specific; return None."""
    resp = client.post('/api/recommendations', json={
        'weather': 'rainy', 'mood': 'tired', 'time_available_minutes': 10})
    assert resp.status_code == 200
    rows = resp.json()['recommendations']
    assert len(rows) == 3
    assert len({r['headline'] for r in rows}) == len(rows)
    for row in rows:
        assert len(row['description']) > 95
        assert row['description'].endswith('.')
        assert len(row['reasons']) >= 1
        assert 'generally suitable available drink' not in row['description']


def test_recommendation_copy_uses_weather_and_history(client, customer):
    """Check explainability changes with context and prior orders; return None."""
    before = client.post('/api/recommendations', json={
        'weather': 'sunny', 'mood': 'unspecified', 'time_available_minutes': 10})
    assert before.status_code == 200
    sunny = before.json()['recommendations']
    assert any('sunny weather you selected' in rec['description'] for rec in sunny
               if 'iced' in rec['supported_temperatures'])
    ordered = client.post('/api/orders', json={'beverage_id': 2}, headers=customer)
    assert ordered.status_code == 201, ordered.text
    after = client.post('/api/recommendations', json={}, headers=customer)
    assert after.status_code == 200
    latte = next(rec for rec in after.json()['recommendations'] if rec['name'] == 'Caffè Latte')
    assert 'ordered it before' in latte['description']


def test_hero_uses_standalone_mark_without_second_cup():
    """Check original ornamental cup is removed so brand icon leads hero; return None."""
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / 'frontend' / 'index.html').read_text(encoding='utf-8')
    assert 'class="hero-emblem"' in html
    assert 'class="hero-brewing-logo"' in html
    assert 'cup-illustration' not in html
    assert 'hero-emblem-disc' not in html
