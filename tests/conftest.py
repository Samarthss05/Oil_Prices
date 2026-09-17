"""The suite is offline even if a future test accidentally invokes a connector."""
import socket

import pytest


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must use recorded fixtures or mocks, never the live network")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
