"""Reusable isolated SQLite application fixtures for the SmartBrew test suite."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from backend.main import create_app


@pytest.fixture
def client(tmp_path):
    """Create a fresh test database; input pytest tmp_path, output isolated HTTP test client."""
    with TestClient(create_app(str(tmp_path / 'test.db'))) as test_client:
        yield test_client


@pytest.fixture
def customer(client):
    """Create an authenticated customer; input test client, output HTTP authorization headers."""
    result = client.post('/api/register', json={
        'name': 'SmartBrew Student', 'email': 'student@example.com', 'password': 'TestPassword123!'
    })
    assert result.status_code == 201, result.text
    return {'Authorization': f"Bearer {result.json()['token']}"}


@pytest.fixture
def technician(client):
    """Sign in as demo technician; input test client, output technician authorization headers."""
    result = client.post('/api/admin/login', json={'pin': '2468'})
    assert result.status_code == 200, result.text
    return {'Authorization': f"Bearer {result.json()['token']}"}
