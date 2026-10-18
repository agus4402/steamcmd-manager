"""Scoped tokens for the public server control page. No DB."""

from __future__ import annotations

from app.services import auth


def test_admin_token_is_not_a_server_token():
    admin = auth.create_access_token("admin")
    assert auth.decode_token(admin) == "admin"
    assert not auth.verify_server_token(admin, "srv1", "secret")


def test_server_token_cannot_reach_the_admin_api():
    token = auth.create_server_token("srv1", "secret")
    assert auth.decode_token(token) is None
    assert auth.verify_server_token(token, "srv1", "secret")


def test_server_token_is_bound_to_its_server():
    token = auth.create_server_token("srv1", "secret")
    assert not auth.verify_server_token(token, "srv2", "secret")


def test_password_change_revokes_tokens():
    token = auth.create_server_token("srv1", "secret")
    assert not auth.verify_server_token(token, "srv1", "new-secret")
    assert not auth.verify_server_token(token, "srv1", "")


def test_empty_server_password_never_matches():
    assert not auth.check_server_password("", "")
    assert not auth.check_server_password("anything", "")
    assert auth.check_server_password("secret", "secret")
    assert not auth.check_server_password("Secret", "secret")


def test_garbage_token_rejected():
    assert auth.decode_token("not-a-jwt") is None
    assert not auth.verify_server_token("not-a-jwt", "srv1", "secret")


def test_panel_default_port_from_frontend_origin(monkeypatch):
    from app.services import integration_service as svc

    def origin(value):
        monkeypatch.setattr(svc, "get_settings", lambda: type("S", (), {"frontend_origin": value})())
        return svc.panel_default_port()

    assert origin("http://192.168.1.10:3128") == 3128
    assert origin("http://panel.local") == 80
    assert origin("https://panel.example.com") == 443
