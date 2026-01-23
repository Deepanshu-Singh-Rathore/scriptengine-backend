import os
import fnmatch
import argparse
import json
import sys
import traceback

import pandas as pd
from google.cloud import storage
import google.oauth2.credentials


# ---------------- Debug ----------------

def print_sys_arguments():
    print("\nCommand-Line Arguments")
    print("=" * 40)
    print(f"Script: {sys.argv[0]}")
    for i, arg in enumerate(sys.argv[1:], start=1):
        print(f"Arg {i}: {arg}")
    print("=" * 40 + "\n")


def print_exception(func, e):
    print(f"ERROR in {func}: {type(e).__name__}: {e}")
    print(traceback.format_exc())


# ---------------- Arguments ----------------

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("gcp_token")
    parser.add_argument("vm_logfile")  # kept for compatibility, not used
    parser.add_argument("gcp_bucket")
    parser.add_argument("gcs_folder")
    parser.add_argument("gcp_project")
    parser.add_argument("gcs_partition")
    return vars(parser.parse_args())


# ---------------- GCS ----------------

def get_gcs_client(token, project, bucket_name):
    creds = google.oauth2.credentials.Credentials(token)
    client = storage.Client(project=project, credentials=creds)
    return client, client.bucket(bucket_name)


def list_files(bucket, prefix, pattern):
    blobs = list(bucket.list_blobs(prefix=prefix))
    return [
        blob.name
        for blob in blobs
        if fnmatch.fnmatch(os.path.basename(blob.name), pattern)
    ]


def download_file(bucket, blob_name, local_path):
    print(f"Downloading {blob_name}")
    bucket.blob(blob_name).download_to_filename(local_path)


def upload_file(bucket, blob_path, local_path):
    print(f"Uploading {local_path} -> {blob_path}")
    bucket.blob(blob_path).upload_from_filename(local_path)


def delete_file(bucket, blob_path):
    print(f"Deleting source file {blob_path}")
    bucket.blob(blob_path).delete()


# ---------------- CSV CONVERSION ----------------

def convert(df: pd.DataFrame) -> pd.DataFrame:
    """
    Main conversion function.
    Put ALL CSV transformation logic here.
    """
    if 'Error' in df.columns:
        df = df.rename(columns={'Error': 'updatedError'})
    return df


def process_csv_file(local_csv_path):
    df = pd.read_csv(local_csv_path, dtype=str)
    df = convert(df)
    df.to_csv(local_csv_path, index=False)
    return local_csv_path


# ---------------- Archive (SAFE) ----------------

def archive_and_download(bucket, file_name, local_file, args):
    archive_path = (
        f"processed/{args['gcs_folder']}"
        f"partition_key={args['gcs_partition']}/{local_file}"
    )

    print(f"Archiving {file_name} -> {archive_path}")
    source_blob = bucket.blob(file_name)
    bucket.copy_blob(source_blob, bucket, archive_path)
    download_file(bucket, archive_path, local_file)

    return archive_path


# ---------------- Handler ----------------

def handle_file(file_name, bucket, args, rename_file):
    local_file = os.path.basename(file_name)

    try:
        archive_and_download(bucket, file_name, local_file, args)

        process_csv_file(local_file)

        final_name = f"{rename_file}.csv" if rename_file else local_file
        upload_path = f"{args['gcs_folder']}{final_name}"
        upload_file(bucket, upload_path, local_file)

        delete_file(bucket, file_name)

    except Exception as e:
        print_exception("handle_file", e)
        raise

    finally:
        if os.path.exists(local_file):
            os.remove(local_file)


# ---------------- Main ----------------

def main():
    print("CSV ETL Script Started")
    print_sys_arguments()

    args = parse_arguments()
    _, bucket = get_gcs_client(
        args["gcp_token"], args["gcp_project"], args["gcp_bucket"]
    )

    # Hardcoded config file path (template-specific)
    config_path = "/mnt/scratch/scripts/csv_etl_template_config.json"
    
    with open(config_path) as f:
        config = json.load(f)

    pattern = config["file_mask"]
    # rename_file is optional - only used if specified in config
    rename_file = config.get("rename_file", "")

    files = list_files(bucket, args["gcs_folder"], pattern)

    for file_name in files:
        handle_file(file_name, bucket, args, rename_file)


if __name__ == "__main__":
    main()