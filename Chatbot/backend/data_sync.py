"""
Fetch the ab_data Parquet files from object storage at boot.

ab_data/ is not in git, so a GitHub-triggered deploy ships without it. When
DATA_BUCKET is set, every top-level <table>.parquet in that bucket is
downloaded into DATA_DIR before the in-memory adapter loads, skipping files
already present at the same size. Credentials come from the DATA_BUCKET_*
variables (S3-compatible; a Railway bucket's `railway bucket credentials`).
Local dev leaves DATA_BUCKET unset and reads ab_data/ from disk.
"""
from __future__ import annotations

import os
from pathlib import Path


def sync_from_bucket(data_dir: Path) -> int:
    """Download missing/changed Parquet files; return how many were fetched."""
    bucket = os.environ.get("DATA_BUCKET")
    if not bucket:
        return 0

    import boto3
    from botocore.config import Config

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["DATA_BUCKET_ENDPOINT"],
        region_name=os.environ.get("DATA_BUCKET_REGION") or "auto",
        aws_access_key_id=os.environ["DATA_BUCKET_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["DATA_BUCKET_SECRET_ACCESS_KEY"],
        config=Config(s3={"addressing_style": os.environ.get("DATA_BUCKET_URL_STYLE", "virtual")}),
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if "/" in key or not key.endswith(".parquet"):
                continue  # originals/ and anything else stay in the bucket
            dest = data_dir / key
            if dest.exists() and dest.stat().st_size == obj["Size"]:
                continue
            part = dest.with_name(dest.name + ".part")
            s3.download_file(bucket, key, str(part))
            part.replace(dest)
            fetched += 1
    return fetched
