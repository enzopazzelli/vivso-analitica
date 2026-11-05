"""Reglas para todas las pruebas: ninguna usa la red y ninguna depende de las variables ANALITICA_* de quien las corre."""
import os
import socket

import pytest


@pytest.fixture(autouse=True)
def sin_red_ni_variables(monkeypatch):
    def bloquear(*args, **kwargs):
        raise RuntimeError("Las pruebas no usan la red")

    monkeypatch.setattr(socket.socket, "connect", bloquear)
    monkeypatch.setattr(socket, "getaddrinfo", bloquear)
    for nombre in list(os.environ):
        if nombre.startswith("ANALITICA_"):
            monkeypatch.delenv(nombre)
