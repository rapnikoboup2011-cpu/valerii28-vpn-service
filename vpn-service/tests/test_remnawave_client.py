import base64
from unittest.mock import AsyncMock, MagicMock

from bot.config import config
from bot.services import remnawave_client


def _mock_response(payload: dict):
    response = MagicMock()
    response.json.return_value = {"response": payload}
    response.raise_for_status = MagicMock()
    return response


async def test_create_user_assigns_configured_internal_squad(monkeypatch):
    monkeypatch.setattr(config, "remnawave_internal_squad_uuid", "squad-uuid-123")
    post = AsyncMock(return_value=_mock_response({"uuid": "u1"}))
    monkeypatch.setattr(remnawave_client._client, "post", post)

    await remnawave_client.create_user("tg123", 1)

    _, kwargs = post.call_args
    assert kwargs["json"]["activeInternalSquads"] == ["squad-uuid-123"]


async def test_get_subscription_url_uses_panel_provided_url():
    user = {
        "uuid": "u1",
        "shortUuid": "BBHBLFHbb4PpKCCY",
        "subscriptionUrl": "https://sub.valerii28.ru/BBHBLFHbb4PpKCCY",
    }

    url = await remnawave_client.get_subscription_url(user)

    assert url == "https://sub.valerii28.ru/BBHBLFHbb4PpKCCY"


async def test_get_raw_config_decodes_base64_response(monkeypatch):
    raw_text = "ss://chacha20-ietf-poly1305:pass123@62.84.99.158:1234#valerii28-main"
    response = MagicMock()
    response.text = base64.b64encode(raw_text.encode()).decode()
    response.raise_for_status = MagicMock()
    get = AsyncMock(return_value=response)
    monkeypatch.setattr(remnawave_client._client, "get", get)

    user = {"uuid": "u1", "shortUuid": "BBHBLFHbb4PpKCCY"}
    result = await remnawave_client.get_raw_config(user)

    get.assert_awaited_once_with("/api/sub/BBHBLFHbb4PpKCCY")
    assert result == raw_text
