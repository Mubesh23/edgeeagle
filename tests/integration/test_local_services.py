"""Local-only service smoke checks; never contact provider or AWS endpoints."""

import os
from uuid import uuid4

import boto3
import psycopg
from botocore.config import Config


def test_postgres_connection_and_transaction() -> None:
    port = int(os.environ.get("EDGEEAGLE_POSTGRES_PORT", "55432"))
    with psycopg.connect(
        host="127.0.0.1",
        port=port,
        user="edgeeagle",
        password="edgeeagle-local",
        dbname="edgeeagle",
        connect_timeout=5,
    ) as connection:
        connection.execute("CREATE TEMPORARY TABLE foundation_probe (value integer)")
        connection.execute("INSERT INTO foundation_probe VALUES (42)")
        assert connection.execute("SELECT value FROM foundation_probe").fetchone() == (42,)


def test_floci_s3_round_trip() -> None:
    port = int(os.environ.get("EDGEEAGLE_FLOCI_PORT", "4566"))
    s3 = boto3.client(
        "s3",
        endpoint_url=f"http://127.0.0.1:{port}",
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
    bucket = f"edgeeagle-test-{uuid4().hex}"
    s3.create_bucket(Bucket=bucket)
    try:
        s3.put_object(Bucket=bucket, Key="probe.json", Body=b'{"synthetic":true}')
        response = s3.get_object(Bucket=bucket, Key="probe.json")
        with response["Body"] as body:
            assert body.read() == b'{"synthetic":true}'
    finally:
        s3.delete_object(Bucket=bucket, Key="probe.json")
        s3.delete_bucket(Bucket=bucket)
        s3.close()
