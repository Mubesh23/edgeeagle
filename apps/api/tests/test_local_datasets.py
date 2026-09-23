import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from edgeeagle_api import local_datasets
from tests.unit.test_dataset_catalog import catalog


def test_local_dataset_factory_pins_config_and_closes_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected, objects, raws, digest = catalog()
    monkeypatch.chdir(tmp_path)
    config = tmp_path / ".data/catalog.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "format": 1,
                "bucket": "edgeeagle-raw-test-catalog",
                "entries": [{"root_hash": digest, "label": "Authored"}],
            }
        )
    )
    monkeypatch.setenv("EDGEEAGLE_DATASET_CATALOG", str(config))
    client = Mock()
    factory = Mock(return_value=client)
    monkeypatch.setattr(local_datasets, "local_client", factory)
    monkeypatch.setattr(local_datasets, "S3SeasonObjectStore", Mock(return_value=objects))
    monkeypatch.setattr(local_datasets, "S3RawPayloadStore", Mock(return_value=raws))
    app = local_datasets.create_local_dataset_app()
    factory.assert_not_called()
    config.write_text("{}")  # Configuration changes require an explicit restart.
    with TestClient(app) as http:
        assert http.get("/health").status_code == 200
        assert http.get("/v1/events").status_code == 503
        assert http.get("/v1/datasets/bad/inspection").status_code == 422
        factory.assert_not_called()
        assert http.get("/v1/datasets").status_code == 200
        assert client.close.call_count == 1
        assert http.get(f"/v1/datasets/{digest}/inspection").status_code == 200
        assert client.close.call_count == 2
        objects.get.side_effect = ValueError("private corrupt root")
        assert http.get("/v1/datasets").status_code == 503
        assert client.close.call_count == 3
        objects.get.side_effect = RuntimeError("programming error")
        with pytest.raises(RuntimeError):
            http.get("/v1/datasets")
        assert client.close.call_count == 4


def test_local_dataset_factory_rejects_missing_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EDGEEAGLE_DATASET_CATALOG", raising=False)
    with pytest.raises(ValueError, match="EDGEEAGLE_DATASET_CATALOG"):
        local_datasets.create_local_dataset_app()
