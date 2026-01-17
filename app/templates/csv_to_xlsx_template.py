import os
import fnmatch
import argparse
import sys
import json
import traceback

import pandas as pd
from google.cloud import storage
import google.oauth2.credentials


# ===================== HARDCODED CONFIG FILE PATH =====================

CONFIG_FILE_PATH = "/opt/etl/config/csvtoxlsx_config.json"

# =====================================================================


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


# ---------------- Config Loader ----------------

def load_config():
    if not os.path.exists(CONFIG_FILE_PATH):
        raise FileNotFoundError(f"Config file not found: {CONFIG_FILE_PATH}")

    with open(CONFIG_FILE_PATH) as f:
        return json.load(f)


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


# ---------------- CSV TRANSFORM ----------------

def transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Main transformation function.
    Put ALL CSV-to-XLSX business logic here.
    """
{{ function_code }}


def process_csv_file(local_csv_path):
    df = pd.read_csv(local_csv_path, dtype=str)
    df = transform(df)

    base_name = os.path.splitext(local_csv_path)[0]
    xlsx_name = f"{base_name}.xlsx"

    df.to_excel(xlsx_name, index=False, engine="openpyxl")

    return xlsx_name


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
    xlsx_file = None

    try:
        archive_and_download(bucket, file_name, local_file, args)

        xlsx_file = process_csv_file(local_file)

        final_name = (
            f"{rename_file}.xlsx"
            if rename_file
            else os.path.basename(xlsx_file)
        )

        upload_path = f"{args['gcs_folder']}{final_name}"
        upload_file(bucket, upload_path, xlsx_file)

        delete_file(bucket, file_name)

    except Exception as e:
        print_exception("handle_file", e)
        raise

    finally:
        if os.path.exists(local_file):
            os.remove(local_file)

        if xlsx_file and os.path.exists(xlsx_file):
            os.remove(xlsx_file)


# ---------------- Main ----------------

def main():
    print("CSV to XLSX ETL Script Started")
    print_sys_arguments()

    args = parse_arguments()
    config = load_config()

    _, bucket = get_gcs_client(
        args["gcp_token"],
        args["gcp_project"],
        args["gcp_bucket"]
    )

    file_mask = config["file_mask"]
    rename_file = config.get("rename_file", "")

    files = list_files(bucket, args["gcs_folder"], file_mask)

    for file_name in files:
        handle_file(file_name, bucket, args, rename_file)


if __name__ == "__main__":
    main()
