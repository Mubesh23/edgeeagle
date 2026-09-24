from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from edgeeagle_api import local


@pytest.mark.parametrize(
    "url",
    [
        "",
        "secret",
        "sqlite:///test",
        "postgresql+psycopg://u:p@remote/db",
        "postgresql+psycopg://u:p@127.0.0.1/db?host=remote",
        "postgresql+psycopg://127.0.0.1/db",
    ],
)
def test_local_url_rejects_implicit_or_remote_configuration(url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        local.local_database_url(url)


def test_local_lifecycle_is_lazy_and_disposes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDGEEAGLE_DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1/db")
    engine = Mock()
    constructor = Mock(return_value=engine)
    monkeypatch.setattr(local, "create_engine", constructor)
    app = local.create_local_app()
    constructor.assert_not_called()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        engine.connect.assert_not_called()
        assert constructor.call_args.kwargs["max_overflow"] == 0
        assert constructor.call_args.kwargs["connect_args"]["hostaddr"] == "127.0.0.1"
    engine.dispose.assert_called_once()
    assert app.state.event_reads is None
    assert app.state.market_reads is None
