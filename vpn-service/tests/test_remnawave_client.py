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
