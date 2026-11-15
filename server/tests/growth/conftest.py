from datetime import datetime, timezone

import pytest


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
