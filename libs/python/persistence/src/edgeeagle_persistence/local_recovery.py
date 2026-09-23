"""Explicit loopback-only operator recovery; never a hosted API or routine acquisition."""

import os
import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
import psycopg
from botocore.config import Config
from mypy_boto3_s3 import S3Client
from psycopg import sql
from sqlalchemy import URL, create_engine, text

from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.season_bundle import content_hash
from edgeeagle_ingestion.season_recovery import export_season, restore_season, verify_season
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.receipts import EventReceiptCodec
from edgeeagle_persistence.recovery_archive import MAX_DUMP_BYTES, load_archive, write_archive
from edgeeagle_persistence.season_storage import S3SeasonObjectStore

CODEC = EventReceiptCodec()


def _database(name: str) -> str:
    if not re.fullmatch(r"edgeeagle(?:_(?:repository_test|recovery)_[0-9a-f]{32})?", name):
        raise ValueError("only local EdgeEagle research/test databases are supported")
    return name


def _bucket(name: str) -> str:
    if not re.fullmatch(r"edgeeagle-(?:private-research|raw-test|recovery)-[a-z0-9-]{1,36}", name):
        raise ValueError("only local EdgeEagle research/test buckets are supported")
    return name


def _run(arguments: list[str], body: bytes | None = None) -> bytes:
    # Keep subprocess output off the heap until its size is checked. Never use a shell.
    environment = {k: v for k, v in os.environ.items() if not k.startswith("DOCKER_")}
    with tempfile.TemporaryFile() as output:
        subprocess.run(
            arguments, input=body, stdout=output, check=True, timeout=60, env=environment
        )
        output.seek(0)
        result = output.read(MAX_DUMP_BYTES + 1)
        if len(result) > MAX_DUMP_BYTES:
            raise ValueError("local command output exceeds recovery limit")
        return result


class LocalRecovery:
    """Connections are fixed to loopback and dummy local credentials; no host override."""

    def __init__(self, repository: Path, *, postgres_port: int = 55432, floci_port: int = 4566):
        if any(type(p) is not int or not 1 <= p <= 65535 for p in (postgres_port, floci_port)):
            raise ValueError("invalid local service port")
        self.repository = repository.resolve()
        self.postgres_port = postgres_port
        self.floci_port = floci_port
        self.docker: list[str] | None = None
        self._owned: tuple[str, str] | None = None

    def _pg(self, arguments: list[str], body: bytes | None = None) -> bytes:
        if self.docker is None:
            raise RuntimeError("local server preflight is required")
        if arguments[1:] == ["--version"]:
            return _run(self.docker + arguments)
        return _run(
            self.docker
            + [arguments[0], "-U", "edgeeagle", "-h", "/var/run/postgresql"]
            + arguments[1:],
            body,
        )

    def connect(self, database: str = "postgres") -> psycopg.Connection[Any]:
        if database != "postgres":
            _database(database)
        return psycopg.connect(
            host="127.0.0.1",
            hostaddr="127.0.0.1",
            port=self.postgres_port,
            dbname=database,
            user="edgeeagle",
            password="edgeeagle-local",
            connect_timeout=5,
            options="-c statement_timeout=30000",
            autocommit=True,
        )

    def preflight(self) -> dict[str, str]:
        context = os.environ.get("DOCKER_CONTEXT")
        host = os.environ.get("DOCKER_HOST") if not context else None
        if not host:
            command = ["docker", "context", "inspect"]
            if context:
                command.append(context)
            host = _run(command + ["--format", "{{.Endpoints.docker.Host}}"]).decode().strip()
        if not host.startswith("unix:///"):
            raise ValueError("recovery requires a local Unix-socket Docker engine")
        self.docker = [
            "docker",
            "--host",
            host,
            "compose",
            "-p",
            "edgeeagle-local",
            "-f",
            str(self.repository / "compose.yaml"),
            "exec",
            "-T",
            "postgres",
        ]
        query = "SELECT system_identifier::text FROM pg_control_system()"
        container_id = self._pg(["psql", "-d", "postgres", "-At", "-c", query]).decode().strip()
        with self.connect() as connection:
            row = connection.execute(query).fetchone()
        if row is None or row[0] != container_id:
            raise ValueError("loopback PostgreSQL does not match the Compose server")
        return {
            "postgres_system_identifier": container_id,
            "pg_dump": self._pg(["pg_dump", "--version"]).decode().strip(),
            "pg_restore": self._pg(["pg_restore", "--version"]).decode().strip(),
        }

    def client(self) -> S3Client:
        return boto3.client(
            "s3",
            endpoint_url=f"http://127.0.0.1:{self.floci_port}",
            aws_access_key_id="test",
            aws_secret_access_key="test",
            aws_session_token="test",
            region_name="us-east-1",
            config=Config(
                s3={"addressing_style": "path"},
                proxies={},
                connect_timeout=3,
                read_timeout=5,
                retries={"max_attempts": 1},
            ),
        )

    def export(self, bucket: str, root: str) -> tuple[dict[str, bytes], tuple[EventCandidate, ...]]:
        _bucket(bucket)
        client = self.client()
        try:
            files = export_season(
                root,
                CODEC,
                S3SeasonObjectStore(client, bucket, CODEC),
                S3RawPayloadStore(client, bucket),
            )
            return files, verify_season(files, root, CODEC)
        finally:
            client.close()

    def database_state(
        self, database: str, candidates: tuple[EventCandidate, ...]
    ) -> dict[str, Any]:
        engine = create_engine(
            URL.create(
                "postgresql+psycopg",
                username="edgeeagle",
                password="edgeeagle-local",
                host="127.0.0.1",
                port=self.postgres_port,
                database=_database(database),
            ),
            connect_args={
                "hostaddr": "127.0.0.1",
                "connect_timeout": 5,
                "options": "-c statement_timeout=30000",
            },
        )
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                repository = PostgresEventAcceptanceRepository(connection)
                for candidate in candidates:
                    retained = repository.get(candidate.event.event_id)
                    if retained is None or CODEC.encode(retained) != CODEC.encode(candidate):
                        raise ValueError("restored/source canonical receipt differs from replay")
                tables = ("events", "event_normalizations", "participants", "event_outbox")
                counts = {
                    table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
                    for table in tables
                }
                return {
                    "counts": counts,
                    "database_oid": connection.scalar(
                        text(
                            "SELECT oid::bigint FROM pg_database WHERE datname = current_database()"
                        )
                    ),
                    "schema": connection.scalar(text("SELECT version_num FROM alembic_version")),
                    "receipts_verified": len(candidates),
                }
        finally:
            engine.dispose()

    def object_state(self, bucket: str) -> list[dict[str, Any]]:
        _bucket(bucket)
        client = self.client()
        try:
            result = client.list_objects_v2(Bucket=bucket, MaxKeys=1000)
            if result.get("IsTruncated"):
                raise ValueError("local recovery bucket exceeds 1000-object audit limit")
            return sorted(
                (
                    {"key": r["Key"], "size": r["Size"], "etag": r["ETag"]}
                    for r in result.get("Contents", [])
                ),
                key=lambda r: str(r["key"]),
            )
        finally:
            client.close()

    def dump(self, database: str) -> bytes:
        return self._pg(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--dbname",
                _database(database),
            ]
        )

    @contextmanager
    def isolated(self, report: dict[str, Any]) -> Iterator[tuple[str, str]]:
        if self._owned is not None:
            raise RuntimeError("a recovery exercise is already active")
        suffix = uuid4().hex
        database, bucket = f"edgeeagle_recovery_{suffix}", f"edgeeagle-recovery-{suffix}"
        report.update(
            target_database=database,
            target_bucket=bucket,
            database_removed=False,
            bucket_removed=False,
        )
        client = self.client()
        database_created = bucket_created = False
        try:
            with self.connect() as admin:
                # CREATE DATABASE itself refuses collisions; never DROP an uncreated target.
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
                database_created = True
            if any(b["Name"] == bucket for b in client.list_buckets().get("Buckets", [])):
                raise FileExistsError("recovery bucket collision")
            client.create_bucket(Bucket=bucket)
            bucket_created = True
            self._owned = (database, bucket)
            yield database, bucket
        finally:
            self._owned = None
            try:
                if bucket_created:
                    for entry in self.object_state(bucket):
                        client.delete_object(Bucket=bucket, Key=entry["key"])
                    client.delete_bucket(Bucket=bucket)
                    report["bucket_removed"] = True
            finally:
                client.close()
                if database_created:
                    with self.connect() as admin:
                        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
                    report["database_removed"] = True

    def restore(
        self, database: str, bucket: str, dump: bytes, files: dict[str, bytes], root: str
    ) -> None:
        if (database, bucket) != self._owned:
            raise ValueError("restore requires isolated recovery targets")
        _database(database)
        _bucket(bucket)
        self._pg(
            [
                "pg_restore",
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-acl",
                "--dbname",
                database,
            ],
            dump,
        )
        client = self.client()
        try:
            restore_season(
                files,
                root,
                CODEC,
                S3SeasonObjectStore(client, bucket, CODEC),
                S3RawPayloadStore(client, bucket),
            )
        finally:
            client.close()


def backup(
    local: LocalRecovery, path: Path, database: str, bucket: str, root: str
) -> dict[str, Any]:
    if path.exists() or path.is_symlink():
        raise FileExistsError("backup path already exists")
    versions = local.preflight()
    files, candidates = local.export(bucket, root)
    before = local.database_state(database, candidates)
    objects = local.object_state(bucket)
    dump = local.dump(database)
    # Check read-only source stability before publishing any completion marker.
    if before != local.database_state(database, candidates) or objects != local.object_state(
        bucket
    ):
        raise ValueError("source changed during backup")
    inventory = write_archive(path, files, dump, root, CODEC)
    return {
        "archive": str(path),
        "inventory_sha256": inventory,
        "root": root,
        "source_database": database,
        "source_bucket": bucket,
        "versions": versions,
        "source_state": before,
        "source_objects": objects,
        "usage": "REPLAY_ONLY",
    }


def verify_restore(
    local: LocalRecovery, path: Path, inventory: str, report: dict[str, Any] | None = None
) -> dict[str, Any]:
    files, dump, root = load_archive(path, inventory, CODEC)
    result = report if report is not None else {}
    result.update(inventory_sha256=inventory, root=root, verified=False)
    result["versions"] = local.preflight()
    with local.isolated(result) as (database, bucket):
        local.restore(database, bucket, dump, files, root)
        # Verification reads only the restored stores and restored PostgreSQL receipts.
        restored, candidates = local.export(bucket, root)
        if restored != files:
            raise ValueError("restored artifact bytes differ from backup")
        result["restored_state"] = local.database_state(database, candidates)
        result["objects"] = len(local.object_state(bucket))
        result["raw_sha256"] = content_hash(restored["raw.bin"])
        result["usage"] = "REPLAY_ONLY"
        available = candidates[0].raw.capture.available_at
        result["historical_available_at"] = available.isoformat() if available is not None else None
    result["verified"] = True
    return result
