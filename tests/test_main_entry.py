import sys

import main as entrypoint


def test_main_defaults_to_web_server(monkeypatch):
    called = []
    monkeypatch.setattr(entrypoint, "run_web", lambda: called.append("web"))
    monkeypatch.setattr(sys, "argv", ["main.py"])

    entrypoint.main()

    assert called == ["web"]


def test_main_keeps_cli_mode(monkeypatch):
    called = []
    monkeypatch.setattr(entrypoint, "run_cli", lambda: called.append("cli"))
    monkeypatch.setattr(sys, "argv", ["main.py", "--cli"])

    entrypoint.main()

    assert called == ["cli"]
