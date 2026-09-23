"""Strict private catalog configuration and all-or-error JSON operator output."""

import json
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import Mock

import boto3
import pytest

from edgeeagle_persistence import dataset_cli


def configuration() -> dict[str, object]:
    return {"format": 1, "bucket": "edgeeagle-private-research-authored", "entries": []}


def test_decode_strict_configuration() -> None:
    bucket, catalog = dataset_cli.decode_catalog(json.dumps(configuration()).encode())
    assert bucket == "edgeeagle-private-research-authored" and catalog.entries == ()
    for body in (b"[]", b"{", b'{"format":1,"format":1}', b'{"format":NaN}', b"x" * 16385):
        with pytest.raises(ValueError):
            dataset_cli.decode_catalog(body)


@pytest.mark.parametrize(
    "field,value",
    [("format", True), ("format", 2), ("bucket", "production"), ("entries", {}), ("extra", True)],
)
def test_invalid_config_fields(field: str, value: object) -> None:
    model = configuration() | {field: value}
    with pytest.raises(ValueError):
        dataset_cli.decode_catalog(json.dumps(model).encode())


def test_config_entry_validation() -> None:
    model = configuration() | {"entries": [{"root_hash": "a" * 64, "label": "Authored"}]}
    assert dataset_cli.decode_catalog(json.dumps(model).encode())[1].entries[0].label == "Authored"
    for entries in (
        [{"root_hash": "bad", "label": "Authored"}],
        [None],
        [{"root_hash": "a" * 64, "label": "A", "extra": True}],
        [{"root_hash": "a" * 64, "label": "A"}] * 2,
    ):
        with pytest.raises((ValueError, TypeError)):
            dataset_cli.decode_catalog(json.dumps(configuration() | {"entries": entries}).encode())


def test_invalid_config_fails_before_client_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / ".data/catalog.json"
    path.parent.mkdir()
    path.write_bytes(b"bad")
    client = Mock()
    monkeypatch.setattr(dataset_cli, "local_client", client)
    assert dataset_cli.main(["--catalog", str(path), "list"]) == 1
    client.assert_not_called()
    output = capsys.readouterr()
    assert not output.out and "failed" in output.err


def test_empty_listing_closes_client_and_unknown_root_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / ".data/catalog.json"
    path.parent.mkdir()
    path.write_text(json.dumps(configuration()))
    client = Mock()
    monkeypatch.setattr(dataset_cli, "local_client", lambda: client)
    assert dataset_cli.main(["--catalog", str(path), "list"]) == 0
    assert json.loads(capsys.readouterr().out) == {"items": []}
    assert dataset_cli.main(["--catalog", str(path), "inspect", "a" * 64]) == 1
    assert not capsys.readouterr().out
    assert client.close.call_count == 2
    client.get_object.assert_not_called()


def test_inspect_outputs_fresh_evidence_and_closes_on_missing_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.unit.test_dataset_catalog import catalog

    selected, objects, raws, digest = catalog()
    monkeypatch.chdir(tmp_path)
    path = tmp_path / ".data/catalog.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            configuration()
            | {"entries": [{"root_hash": digest, "label": selected.entries[0].label}]}
        )
    )
    client = Mock()
    monkeypatch.setattr(dataset_cli, "local_client", lambda: client)
    monkeypatch.setattr(dataset_cli, "S3SeasonObjectStore", lambda *args: objects)
    monkeypatch.setattr(dataset_cli, "S3RawPayloadStore", lambda *args: raws)
    args = ["--catalog", str(path), "inspect", digest]
    assert dataset_cli.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["replay_status"] == "VERIFIED" and output["receipt_count"] == 65
    assert output["metadata"]["raw"]["capture"]["available_at"] is None
    original = objects.get.side_effect
    objects.get.side_effect = lambda key: original(key) if key == digest else None
    assert dataset_cli.main(args) == 1
    assert not capsys.readouterr().out
    assert client.close.call_count == 2
    objects.put.assert_not_called()
    raws.put.assert_not_called()


def test_path_bounds_and_regular_file_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    private = tmp_path / ".data"
    private.mkdir()
    path = private / "catalog.json"
    path.write_bytes(b"x" * 16385)
    with pytest.raises(ValueError, match="bounded"):
        dataset_cli.load_catalog(path)
    with pytest.raises(ValueError, match="inside repository"):
        dataset_cli.load_catalog(tmp_path / "outside.json")
    link = private / "linked.json"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="inside repository"):
        dataset_cli.load_catalog(link)
    fifo = private / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular"):
        dataset_cli.load_catalog(fifo)


def test_client_is_explicit_loopback_and_invalid_ports_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    monkeypatch.setattr(boto3, "client", client)
    monkeypatch.setenv("EDGEEAGLE_FLOCI_PORT", "4567")
    dataset_cli.local_client()
    assert client.call_args.kwargs["endpoint_url"] == "http://127.0.0.1:4567"
    assert client.call_args.kwargs["aws_access_key_id"] == "test"
    assert client.call_args.kwargs["config"].proxies == {}
    for invalid in ("0", "65536", "https://remote"):
        monkeypatch.setenv("EDGEEAGLE_FLOCI_PORT", invalid)
        with pytest.raises(ValueError):
            dataset_cli.local_client()
    with pytest.raises(TypeError):
        dataset_cli._json_default(object())


def test_module_help(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["datasets", "--help"])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(dataset_cli.__file__, run_name="__main__")
    assert result.value.code == 0
