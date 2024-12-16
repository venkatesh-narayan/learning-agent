import gzip
import json
from typing import Dict

from google.cloud import storage


def read_gcs_file(bucket_name: str, file_path: str) -> Dict:
    """Read and decompress a gzipped JSON file from GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(file_path)
    content = blob.download_as_bytes()
    decompressed = gzip.decompress(content)
    return json.loads(decompressed)


def write_gcs_file(bucket_name: str, file_path: str, content: Dict) -> None:
    """Write and compress content to a JSON file in GCS."""
    client = storage.Client()

    # Handle bucket/path separation.
    if "/" in bucket_name:
        # If bucket_name includes a path (e.g. "bucket/test_processing")
        tokens = bucket_name.split("/")
        bucket_name, remaining = tokens[0], tokens[1:]
        file_path = "/".join([*remaining, file_path])

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(file_path)

    # Convert to JSON and compress
    json_content = json.dumps(content)
    compressed = gzip.compress(json_content.encode())

    # Upload to GCS
    blob.upload_from_string(compressed)


def file_exists_in_gcs(bucket_name: str, file_path: str) -> bool:
    """Check if a file exists in GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(file_path)
    return blob.exists()


def list_gcs_files(bucket_name: str, prefix: str = "") -> list[str]:
    """List all files in a GCS bucket with given prefix."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)
    return [blob.name for blob in blobs]
