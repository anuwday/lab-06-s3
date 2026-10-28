#!/bin/bash
# Download one Gutenberg book, upload it to a private bucket, print a presigned URL. Usage: ./share_book.sh BOOK_URL BUCKET EXPIRES_SECONDS
set -euo pipefail

# Check
if [ "$#" -lt 3 ]; then
    echo "Usage: $0 BOOK_URL BUCKET EXPIRES_SECONDS" >&2
    exit 1
fi

URL="$1"
BUCKET="$2"
EXPIRES="$3"
FILE="$(basename "$URL")"

# Download the book into books/ to keep the file name from the URL
mkdir -p books
curl -fsSL "$URL" -o "books/$FILE"

# Create the bucket unless it already exists (stays private)
if aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    echo "Bucket $BUCKET already exists"
else
    aws s3 mb "s3://$BUCKET" --region us-east-1
fi

# Upload a content type so it displays in the browser
aws s3 cp "books/$FILE" "s3://$BUCKET/$FILE" --content-type "text/plain; charset=utf-8"

# Print a presigned URL that expires after EXPIRES seconds
aws s3 presign "s3://$BUCKET/$FILE" --expires-in "$EXPIRES"