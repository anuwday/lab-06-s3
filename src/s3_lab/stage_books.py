#!/usr/bin/env python3
"""Stage Project Gutenberg books in a public S3 bucket.

Usage:
    uv run python src/s3_lab/stage_books.py book_urls.txt index.html public-khs3z
"""
import json
import logging
import os
import sys
import time

import boto3
import requests
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# One authenticated client shared by all functions
s3 = boto3.client("s3", region_name="us-east-1")


def parse_args():
    """Return (list_file, index_path, bucket) from the command line."""
    if len(sys.argv) < 4:
        log.error("Usage: stage_books.py BOOK_LIST INDEX_HTML BUCKET_NAME")
        sys.exit(1)
    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    """Download each URL in list_file into dest_dir. Return the local paths."""
    os.makedirs(dest_dir, exist_ok=True)
    paths = []
    try:
        with open(list_file) as f:
            urls = [line.strip() for line in f if line.strip()]
    except OSError as e:
        log.error(f"Cannot read {list_file}: {e}")
        return paths

    for url in urls:
        path = os.path.join(dest_dir, url.rsplit("/", 1)[-1])
        if os.path.exists(path):  # skip so reruns are fast
            log.info(f"Skipping {path} (already downloaded)")
            paths.append(path)
            continue
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # raise an error for 404 etc.
            with open(path, "wb") as out:
                out.write(response.content)
            log.info(f"Downloaded {url} -> {path}")
            paths.append(path)
        except (requests.RequestException, OSError) as e:
            log.error(f"Error downloading {url}: {e}")
        time.sleep(1)
    return paths


def create_bucket(bucket):
    """Create the bucket unless it exists. Return True if it exists afterwards."""
    try:
        s3.head_bucket(Bucket=bucket)
        log.info(f"Bucket {bucket} already exists")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchBucket"):
            log.error(f"Cannot access bucket {bucket}: {e}")
            return False
    try:
        # us-east-1: omit LocationConstraint or create_bucket fails
        s3.create_bucket(Bucket=bucket)
        log.info(f"Created bucket: {bucket}")
        return True
    except ClientError as e:
        log.error(f"Error creating bucket {bucket}: {e}")
        return False


def make_public(bucket):
    """Turn off Block Public Access, then attach a public-read policy."""
    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                }
            ],
        }
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        log.info(f"{bucket} is now publicly readable")
        return True
    except ClientError as e:
        log.error(f"Error making {bucket} public: {e}")
        return False


def upload_files(bucket, file_paths):
    """Upload each file to the bucket top level. Return the success count."""
    count = 0
    for path in file_paths:
        key = os.path.basename(path)  # pg1342.txt, not books/pg1342.txt
        try:
            with open(path, "rb") as f:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType="text/plain; charset=utf-8",  # display, not download
                )
            log.info(f"Uploaded {path} to s3://{bucket}/{key}")
            count += 1
        except FileNotFoundError:
            log.error(f"Local file not found: {path}")
        except ClientError as e:
            log.error(f"Error uploading {path}: {e}")
    return count


def upload_index(bucket, index_path):
    """Upload the index page as index.html. Return True on success."""
    try:
        with open(index_path, "rb") as f:
            s3.put_object(
                Bucket=bucket,
                Key="index.html",
                Body=f,
                ContentType="text/html",  # to let browsers render the page
            )
        log.info(f"Uploaded {index_path} to s3://{bucket}/index.html")
        return True
    except FileNotFoundError:
        log.error(f"Local file not found: {index_path}")
        return False
    except ClientError as e:
        log.error(f"Error uploading {index_path}: {e}")
        return False


def main():
    """Run all steps in order."""
    list_file, index_path, bucket = parse_args()

    paths = download_books(list_file, "books")
    if not paths:
        log.error("No books were downloaded")
        sys.exit(1)
    if not create_bucket(bucket):
        sys.exit(1)
    if not make_public(bucket):
        sys.exit(1)

    uploaded = upload_files(bucket, paths)
    log.info(f"Uploaded {uploaded} of {len(paths)} books")
    index_ok = upload_index(bucket, index_path)

    if index_ok and uploaded == len(paths):
        log.info("Success!")
    else:
        log.error("Finished with errors. Check the log above and rerun")
    log.info(f"Index page: https://{bucket}.s3.amazonaws.com/index.html")


if __name__ == "__main__":
    main()