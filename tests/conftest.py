import pytest

from core.session import reset


@pytest.fixture(autouse=True)
def reset_session_state():
    reset()
    yield
