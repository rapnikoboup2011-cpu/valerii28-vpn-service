from __future__ import annotations

import os
import tempfile

import pytest

from bot.config import config
from bot.db.db import init_db


@pytest.fixture
async def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    monkeypatch.setattr(config, "database_path", path)
    await init_db()
    yield path
    os.remove(path)
