"""Worker unit tests never connect to real services, including localhost."""

import socket

import pytest


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    attempts = []

    def guarded(method):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("Unit tests must mock network connections")
            return method(sock, address)

        return connect

    monkeypatch.setattr(socket.socket, "connect", guarded(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(socket.socket.connect_ex))
    yield
    # Catch attempts even when production error handling swallowed the exception.
    assert not attempts, "A unit test attempted a network connection"
