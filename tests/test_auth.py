import hashlib
import hmac
import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from server import config
from server.auth import check_init_data
from server.main import app

TOKEN = "test-token"
NOW = 1_790_000_000
USER = {"id": 42, "first_name": "Аня", "last_name": "С+", "username": "anya"}
CHAT = {"id": -100, "type": "CHAT"}


def make_init_data(params: dict, token: str = TOKEN) -> str:
    """Собирает initData так, как это делает МАКС: пары key=value + подпись hash."""
    launch_params = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()
    return "&".join(f"{key}={quote(value, safe='')}" for key, value in {**params, "hash": signature}.items())


def valid_params(**overrides) -> dict:
    params = {
        "auth_date": str(NOW),
        "query_id": "q1",
        "user": json.dumps(USER, ensure_ascii=False),
        "chat": json.dumps(CHAT),
        "start_param": "chat-100",
    }
    return {**params, **overrides}


def test_valid_signature_returns_user_and_chat():
    data = check_init_data(make_init_data(valid_params()), TOKEN, now=NOW + 60)
    assert data["user"] == USER  # плюс в фамилии не превратился в пробел
    assert data["chat"] == CHAT
    assert data["start_param"] == "chat-100"


def test_tampered_data_is_rejected():
    init_data = make_init_data(valid_params()).replace("anya", "hacker")
    with pytest.raises(ValueError, match="подпись не совпала"):
        check_init_data(init_data, TOKEN, now=NOW)


def test_other_bot_token_is_rejected():
    with pytest.raises(ValueError, match="подпись не совпала"):
        check_init_data(make_init_data(valid_params(), token="other-token"), TOKEN, now=NOW)


def test_missing_hash_is_rejected():
    with pytest.raises(ValueError, match="нет подписи"):
        check_init_data("auth_date=1&user=%7B%7D", TOKEN, now=NOW)


def test_old_signature_is_rejected():
    with pytest.raises(ValueError, match="устарела"):
        check_init_data(make_init_data(valid_params()), TOKEN, now=NOW + 2 * 24 * 3600)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(config, "DEV_AUTH", False)
    monkeypatch.setattr(config, "DEV_CHAT_ID", None)
    return TestClient(app)


def test_me_without_signature_is_401(client):
    assert client.get("/api/me").status_code == 401


def test_me_with_bad_signature_is_401(client):
    assert client.get("/api/me", headers={"X-Max-Init-Data": "auth_date=1&hash=abc"}).status_code == 401


def test_me_with_valid_signature(client, monkeypatch):
    monkeypatch.setattr("server.auth.time.time", lambda: NOW + 60)
    response = client.get("/api/me", headers={"X-Max-Init-Data": make_init_data(valid_params())})
    assert response.status_code == 200
    assert response.json() == {"user": USER, "chat": CHAT, "start_param": "chat-100"}


def test_me_in_dev_mode(client, monkeypatch):
    monkeypatch.setattr(config, "DEV_AUTH", True)
    monkeypatch.setattr(config, "DEV_CHAT_ID", -555)
    body = client.get("/api/me").json()
    assert body["user"]["first_name"] == "Тест"
    assert body["chat"] == {"id": -555, "type": "CHAT"}
