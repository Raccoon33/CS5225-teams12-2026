"""Scheduled/manual Lambda entry point for raw HDB rental ingestion."""

import os
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.config import Config

from flatsplit_api.rental_ingestion import (
    DataGovClient,
    S3SnapshotWriter,
    run_ingestion,
)

logger = Logger()


@logger.inject_lambda_context(clear_state=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Ingest one export; exceptions intentionally mark the invocation failed."""
    del event, context
    bucket = os.environ.get("RENT_RAW_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("RENT_RAW_BUCKET is not configured.")
    s3 = boto3.client(
        "s3",
        config=Config(
            connect_timeout=2,
            read_timeout=30,
            retries={"total_max_attempts": 3, "mode": "standard"},
        ),
    )
    try:
        pointer = run_ingestion(DataGovClient(), S3SnapshotWriter(s3, bucket))
    except Exception:
        logger.exception("HDB rental ingestion failed")
        raise
    logger.info(
        "HDB rental ingestion completed",
        extra={
            "snapshot_id": pointer["snapshotId"],
            "source_month_to": pointer["sourceMonthTo"],
        },
    )
    return dict(pointer)
