"""Approved, disposable Floci-only topology; no production policy or resources."""

import json
import os
from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass

import boto3
import pytest
from botocore.config import Config
from mypy_boto3_events import EventBridgeClient
from mypy_boto3_sqs import SQSClient

from edgeeagle_persistence.sqs import SqsNotificationQueue
from tests.integration.test_eventbridge_publisher import event_bus as event_bus


@dataclass
class Routing:
    events: EventBridgeClient
    sqs: SQSClient
    bus: str
    rule: str
    queue_url: str
    queue_arn: str
    consumer_dlq_url: str
    delivery_dlq_url: str
    delivery_dlq_arn: str

    def queue(self, url: str) -> SqsNotificationQueue:
        return SqsNotificationQueue(self.sqs, url, visibility_timeout=1)


@pytest.fixture
def routing(event_bus: tuple[EventBridgeClient, str]) -> Iterator[Routing]:
    events, bus = event_bus
    name = bus.rsplit("/", 1)[1]
    client = boto3.client(
        "sqs",
        endpoint_url=f"http://127.0.0.1:{int(os.environ.get('EDGEEAGLE_FLOCI_PORT', '4566'))}",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_session_token="test",
        config=Config(
            connect_timeout=2,
            read_timeout=3,
            proxies={},
            retries={"mode": "standard", "total_max_attempts": 1},
        ),
    )
    with ExitStack() as cleanup:
        cleanup.callback(client.close)

        def create(suffix: str, retention: int) -> tuple[str, str]:
            url = client.create_queue(
                QueueName=f"{name}-{suffix}",
                Attributes={
                    "MessageRetentionPeriod": str(retention),
                    "VisibilityTimeout": "1",
                },
            )["QueueUrl"]
            cleanup.callback(client.delete_queue, QueueUrl=url)
            arn = client.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])[
                "Attributes"
            ]["QueueArn"]
            return url, arn

        dead, dead_arn = create("consumer-dlq", 1209600)
        broker_dead, broker_dead_arn = create("delivery-dlq", 1209600)
        url, arn = create("consumer", 86400)
        client.set_queue_attributes(
            QueueUrl=url,
            Attributes={
                "RedrivePolicy": json.dumps(
                    {
                        "deadLetterTargetArn": dead_arn,
                        "maxReceiveCount": 2,
                    }
                )
            },
        )
        client.set_queue_attributes(
            QueueUrl=dead,
            Attributes={
                "RedriveAllowPolicy": json.dumps(
                    {
                        "redrivePermission": "byQueue",
                        "sourceQueueArns": [arn],
                    }
                )
            },
        )
        rule = "verify-acceptance"
        rule_arn = events.put_rule(
            Name=rule,
            EventBusName=bus,
            EventPattern=json.dumps(
                {
                    "source": ["edgeeagle.ingestion"],
                    "detail-type": ["EventAccepted"],
                }
            ),
        )["RuleArn"]
        cleanup.callback(events.delete_rule, Name=rule, EventBusName=bus)
        for target_url, target_arn in ((url, arn), (broker_dead, broker_dead_arn)):
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "events.amazonaws.com"},
                        "Action": "sqs:SendMessage",
                        "Resource": target_arn,
                        "Condition": {"ArnEquals": {"aws:SourceArn": rule_arn}},
                    }
                ],
            }
            client.set_queue_attributes(
                QueueUrl=target_url, Attributes={"Policy": json.dumps(policy)}
            )
            saved = client.get_queue_attributes(QueueUrl=target_url, AttributeNames=["Policy"])
            assert json.loads(saved["Attributes"]["Policy"]) == policy
        cleanup.callback(events.remove_targets, Rule=rule, EventBusName=bus, Ids=["consumer"])
        result = events.put_targets(
            Rule=rule,
            EventBusName=bus,
            Targets=[
                {
                    "Id": "consumer",
                    "Arn": arn,
                    "DeadLetterConfig": {"Arn": broker_dead_arn},
                    "RetryPolicy": {"MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 60},
                }
            ],
        )
        assert result["FailedEntryCount"] == 0
        yield Routing(events, client, bus, rule, url, arn, dead, broker_dead, broker_dead_arn)
