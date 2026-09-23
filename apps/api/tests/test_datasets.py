from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from botocore.exceptions import EndpointConnectionError
from fastapi.testclient import TestClient

from edgeeagle_api.datasets import CatalogAccess
from edgeeagle_api.main import create_app
from edgeeagle_domain.raw import RawPayloadIntegrityError
from tests.unit.test_dataset_catalog import catalog
from tests.unit.test_dataset_manifest import CODEC


def test_dataset_api_fresh_reads_and_eligibility() -> None:
    selected, objects, raws, digest = catalog()

    @contextmanager
    def reads() -> Iterator[CatalogAccess]:
        yield CatalogAccess(selected, objects, raws, CODEC, lambda: datetime.now(UTC))

    with TestClient(create_app(dataset_reads=reads)) as client:
        listed = client.get("/v1/datasets")
        assert listed.status_code == 200
        assert listed.headers["cache-control"] == "no-store"
        assert listed.json()["items"][0]["replay_status"] == "NOT_CHECKED"
        objects.get.assert_called_once_with(digest)
        first = client.get(f"/v1/datasets/{digest}/inspection")
        second = client.get(f"/v1/datasets/{digest}/inspection")
        assert first.status_code == second.status_code == 200
        result = first.json()
        assert result["replay_status"] == "VERIFIED"
        assert result["receipt_count"] == 65
        assert result["metadata"]["backtest_eligible"] is False
        assert result["metadata"]["raw"]["capture"]["available_at"] is None
        assert len(result["metadata"]["ineligibility_reasons"]) == 3
        assert result["rights_verified"] is False
        assert result["replay_completed_at"] != second.json()["replay_completed_at"]
        assert client.get("/v1/datasets").json()["items"][0]["replay_status"] == "NOT_CHECKED"
        objects.get.reset_mock()
        assert client.get(f"/v1/datasets/{'a' * 64}/inspection").status_code == 404
        objects.get.assert_not_called()
        objects.get.side_effect = FileNotFoundError("private bucket secret")
        failed = client.get(f"/v1/datasets/{digest}/inspection")
        assert failed.status_code == 503
        assert "secret" not in failed.text
        assert failed.headers["cache-control"] == "no-store"
    objects.put.assert_not_called()
    raws.put.assert_not_called()


@pytest.mark.parametrize("digest", ["short", "A" * 64, "g" * 64, "a" * 65])
def test_invalid_dataset_hash(digest: str) -> None:
    with TestClient(create_app()) as client:
        response = client.get(f"/v1/datasets/{digest}/inspection")
        assert response.status_code == 422
        assert response.headers["cache-control"] == "no-store"


def test_dataset_default_isolation_and_openapi() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v1/datasets").status_code == 503
        assert client.get(f"/v1/datasets/{'a' * 64}/inspection").status_code == 503
        assert client.post("/v1/datasets").status_code == 405
        spec = client.get("/openapi.json").json()
        assert spec["paths"]["/v1/datasets"]["get"]["operationId"] == "list_datasets"
        assert (
            spec["components"]["schemas"]["DatasetMetadata"]["properties"]["backtest_eligible"][
                "const"
            ]
            is False
        )


def test_dataset_programming_errors_remain_server_errors() -> None:
    @contextmanager
    def reads() -> Iterator[CatalogAccess]:
        raise RuntimeError("private programming failure")
        yield  # pragma: no cover

    with TestClient(create_app(dataset_reads=reads), raise_server_exceptions=False) as client:
        response = client.get("/v1/datasets")
        assert response.status_code == 500
        assert "private" not in response.text


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("private"),
        RawPayloadIntegrityError("private"),
        EndpointConnectionError(endpoint_url="http://private"),
    ],
)
def test_dataset_storage_failures_are_not_empty_success(failure: Exception) -> None:
    selected, objects, raws, digest = catalog()
    objects.get.side_effect = failure

    @contextmanager
    def reads() -> Iterator[CatalogAccess]:
        yield CatalogAccess(selected, objects, raws, CODEC, lambda: datetime.now(UTC))

    with TestClient(create_app(dataset_reads=reads)) as client:
        for path in ("/v1/datasets", f"/v1/datasets/{digest}/inspection"):
            response = client.get(path)
            assert response.status_code == 503
            assert "private" not in response.text
            assert "items" not in response.json()
