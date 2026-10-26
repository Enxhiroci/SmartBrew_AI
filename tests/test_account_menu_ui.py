"""Account navigation smoke checks for Lab 3 user experience."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_header_identity_is_interactive_and_has_menu():
    """Verify login identity is an actual button with menu choices; no parameters or return."""
    html = (ROOT / 'frontend/index.html').read_text(encoding='utf-8')
    assert '<button id="identity"' in html
    assert 'id="account-menu"' in html
    for action in ('account-open-profile', 'account-open-recipes', 'account-open-history', 'account-menu-logout'):
        assert f'id="{action}"' in html
    assert 'aria-expanded="false"' in html


def test_customer_identity_events_are_wired():
    """Ensure account menu interactions are available in the kiosk script; no parameters or return."""
    script = (ROOT / 'frontend/app.js').read_text(encoding='utf-8')
    assert "$('identity').addEventListener('click', toggleAccountMenu)" in script
    assert "openAccountSection('recipe-list')" in script
    assert "openAccountSection('order-history')" in script
    assert "if (!state.authToken) { closeAccountMenu(); showPage('profile'); return; }" in script


def test_account_sidebar_has_recognizable_profile_icon():
    """Verify account navigation displays a profile icon and not a chess piece; no parameters or return."""
    html = (ROOT / 'frontend/index.html').read_text(encoding='utf-8')
    assert 'class="nav-profile-icon"' in html
    assert '♙' not in html
    assert 'My account & recipes' in html
