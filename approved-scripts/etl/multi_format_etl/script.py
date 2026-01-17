"""
Here's a **short summary** of what your script does:

---

This Python script is a **config-driven ETL pipeline for GCS files**.
It:

1. Connects to a GCS bucket using an OAuth token.
2. Finds files by type and mask (CSV, XLSX, ZIP).
3. Downloads each file and archives a copy in a `processed/` folder.
4. Runs ETL:

   * **CSV** → kept as-is.
   * **XLSX** → each sheet cleaned and saved as CSV.
   * **ZIP** → extracted, then any CSV/XLSX inside are processed.
5. Uploads processed CSVs back to GCS (optionally renamed with a timestamp).
6. Cleans up local temp files.
7. Deletes the original source file from GCS.

Errors are logged, unsupported file types are skipped with warnings.

"""
import os
import fnmatch
import argparse
import logging
import json
import zipfile
from datetime import datetime
import pandas as pd
import numpy as np

from google.cloud import storage
import google.oauth2.credentials
import sys
import traceback
import logging

# ---------------- 🔍 Debug: Command-Line Arguments ----------------
def print_sys_arguments():
    """
    Prints all system arguments in a clear, pretty format.
    Useful for debugging command-line inputs.
    """
    print("\n🧾 Command-Line Arguments Summary")
    print("========================================")
    print(f"📄 Script Name : {sys.argv[0]}")

    if len(sys.argv) > 1:
        print("\n📦 Passed Arguments:")
        for i, arg in enumerate(sys.argv[1:], start=1):
            print(f"   🔹 Arg {i}: {arg}")
    else:
        print("\n⚠️  No arguments were passed.")

    print("\n🔢 Total Arguments (excluding script name):", len(sys.argv) - 1)
    print("========================================\n")


# ---------------- 🧠 Exception Logger ----------------
def log_detailed_exception(func_name, e):
    """
    Logs detailed error information including type, message, and traceback.
    
    Args:
        func_name (str): Name of the function where the exception occurred.
        e (Exception): The exception instance.
    """
    error_type = type(e).__name__
    error_message = str(e)
    tb = traceback.format_exc()
    logging.error(f"❌ Error in {func_name}: [{error_type}] {error_message}\nTraceback:\n{tb}")
    print(f"❌ Exception in {func_name} [{error_type}]: {error_message}")


# ---------------- 📣 Unified Logger/Console Printer ----------------
def log_and_print(message: str, level: str = "info"):
    """
    Logs a message and prints it to console, based on the provided log level.

    Args:
        message (str): The message to log and print.
        level (str): Log level - one of "info", "error", "warning", "debug". Defaults to "info".
    """
    level = level.lower()
    print(message)  # Always echo to console

    if level == "info":
        logging.info(message)
    elif level == "error":
        logging.error(message)
    elif level == "warning":
        logging.warning(message)
    elif level == "debug":
        logging.debug(message)
    else:
        logging.info(message)


class UnsupportedFileTypeError(Exception):
    """Raised when an unsupported file type is encountered."""

# ---------------------- ARGUMENT PARSER ----------------------

def parse_arguments():
    parser = argparse.ArgumentParser(description="ETL Processor for XLSX, CSV, and ZIP files")
    parser.add_argument("gcp_token")
    parser.add_argument("vm_logfile")
    parser.add_argument("gcp_bucket")
    parser.add_argument("gcs_folder")
    parser.add_argument("gcp_project")
    parser.add_argument("vm_config_file")
    parser.add_argument("gcs_partition")
    return vars(parser.parse_args())

# ---------------------- LOGGING SETUP ----------------------

def setup_logging(vm_logfile):
    log_dir = os.path.dirname(vm_logfile)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        filename=vm_logfile,
        level=logging.INFO,
        format='%(asctime)s - [%(levelname)s] - %(message)s'
    )

# ---------------------- GCS UTILS ----------------------

def get_gcs_client(token, project, bucket_name):
    log_and_print(f"🔐 Initializing GCS client for project: {project}, bucket: {bucket_name}")
    try:
        credentials = google.oauth2.credentials.Credentials(token)
        client = storage.Client(project=project, credentials=credentials)
        log_and_print("✅ GCS client initialized successfully")
        return client, client.bucket(bucket_name)
    except Exception as e:
        log_detailed_exception("get_gcs_client", e)
        raise

def list_files(bucket, prefix, pattern):
    log_and_print(
        f"🔎 Listing files in bucket: {bucket.name}, prefix: '{prefix}', pattern: '{pattern}'"
    )

    try:
        blobs = list(bucket.list_blobs(prefix=prefix))
        matching_files = []

        # Case 1: wildcard pattern
        if "*" in pattern or "?" in pattern:
            matching_files = [
                blob.name
                for blob in blobs
                if fnmatch.fnmatch(os.path.basename(blob.name), pattern)
            ]

        # Case 2: exact filename (NO wildcard) → match by suffix
        else:
            matching_files = [
                blob.name
                for blob in blobs
                if blob.name.endswith(f"/{pattern}") or blob.name.endswith(pattern)
            ]

        if matching_files:
            log_and_print(
                f"📄 Found {len(matching_files)} matching file(s): {matching_files}"
            )
        else:
            log_and_print(
                f"⚠️ No files found matching pattern: {pattern}",
                level="warning",
            )

        return matching_files

    except Exception as e:
        log_detailed_exception("list_files", e)
        return []


def download_file(bucket, blob_name, local_path):
    log_and_print(f"⬇️ Downloading file: gs://{bucket.name}/{blob_name} → {local_path}")
    try:
        bucket.blob(blob_name).download_to_filename(local_path)
        log_and_print(f"✅ Downloaded {blob_name} to {local_path}")
    except Exception as e:
        log_detailed_exception("download_file", e)
        raise

def upload_file(bucket, blob_path, local_path):
    log_and_print(f"⬆️ Uploading: {local_path} to gs://{bucket.name}/{blob_path}")
    if not os.path.exists(local_path):
        log_and_print(f"❌ File not found for upload: {local_path}", level="error")
        raise FileNotFoundError(f"File not found: {local_path}")
    try:
        bucket.blob(blob_path).upload_from_filename(local_path)
        log_and_print(f"✅ Uploaded {local_path} to {blob_path}")
    except Exception as e:
        log_detailed_exception("upload_file", e)
        raise

def delete_file(bucket, blob_path):
    log_and_print(f"🧹 Attempting to delete file from GCS: gs://{bucket.name}/{blob_path}")
    try:
        bucket.blob(blob_path).delete()
        log_and_print(f"🗑️ Successfully deleted blob: gs://{bucket.name}/{blob_path}")
    except Exception as e:
        log_detailed_exception("delete_file", e)

# ---------------------- FILE PROCESSORS ----------------------

def process_xlsx_file(local_xlsx_path):
    log_and_print(f"📘 Processing XLSX file: {local_xlsx_path}")
    csv_files = []
    try:
        with pd.ExcelFile(local_xlsx_path, engine="openpyxl") as excel_file:
            for sheet_name in excel_file.sheet_names:
                log_and_print(f"🔍 Processing sheet: {sheet_name}")
                df = pd.read_excel(excel_file, sheet_name=sheet_name, dtype=str)

                # Replace empty strings with NaN
                df = df.replace("", np.nan)

                # Forward fill missing values
                df = df.ffill()

                # Drop fully empty rows
                df = df.dropna(axis=0, how="all")

                csv_file = f"{os.path.splitext(local_xlsx_path)[0]}_{sheet_name}.csv"
                df.to_csv(csv_file, index=False, sep="^", encoding="utf-8")
                csv_files.append(csv_file)
                log_and_print(f"📝 Sheet '{sheet_name}' saved to CSV: {csv_file}")

        return csv_files

    except Exception as e:
        log_detailed_exception("process_xlsx_file", e)
        raise


def process_csv_file(local_csv_path):
    log_and_print(f"🧹 Processing CSV file: {local_csv_path}")
    try:
        df = pd.read_csv(local_csv_path, dtype=str, sep=",", encoding="utf-8")

        # ❌ REMOVE ROWS CONTAINING THIS KEYWORD (any column)
        bad_keyword = "COP_VEX0002047362_FLORESTAL_BUBBA 75G_8"
        df = df[~df.apply(
            lambda row: row.astype(str).str.contains(bad_keyword, na=False).any(),
            axis=1
        )]

        df.to_csv(local_csv_path, index=False, sep=",", encoding="utf-8")
        log_and_print(f"✅ Removed rows containing keyword: {local_csv_path}")
        return [local_csv_path]

    except Exception as e:
        log_detailed_exception("process_csv_file", e)
        raise



def process_zip_file(local_zip_path):
    log_and_print(f"🗜️ Processing ZIP file: {local_zip_path}")
    extracted_files = []
    csv_files_to_upload = []
    try:
        with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
            zip_ref.extractall()
            extracted_files = zip_ref.namelist()

        log_and_print(f"📦 Extracted files from ZIP: {extracted_files}")

        for extracted_file in extracted_files:
            log_and_print(f"🔍 Evaluating file in ZIP: {extracted_file}")
            if extracted_file.endswith('.xlsx'):
                csv_files_to_upload.extend(process_xlsx_file(extracted_file))
            elif extracted_file.endswith('.csv'):
                csv_files_to_upload.extend(process_csv_file(extracted_file))
            else:
                log_and_print(f"⚠️ Skipped unsupported file in ZIP: {extracted_file}", "warning")

        return csv_files_to_upload
    except Exception as e:
        log_detailed_exception("process_zip_file", e)
        raise

# ---------------------- FILE HANDLER ----------------------

def move_to_archive_and_download(bucket, file_name, local_file, args):
    """
    Move file to archive (processed path), delete original,
    then download from archive for ETL.
    """
    processed_path = (
        f"processed/{args['gcs_folder']}"
        f"partition_key={args['gcs_partition']}/{local_file}"
    )

    log_and_print(f"📦 Moving file to archive: {processed_path}")

    try:
        source_blob = bucket.blob(file_name)

        # Copy to archive
        bucket.copy_blob(source_blob, bucket, processed_path)

        # Delete original immediately
        source_blob.delete()
        log_and_print(f"🗑️ Deleted original source: {file_name}")

        # Download from archive
        download_file(bucket, processed_path, local_file)

        return processed_path

    except Exception as e:
        log_detailed_exception("move_to_archive_and_download", e)
        raise





def run_etl(file_type, local_file):
    """Run ETL depending on file type and return list of processed files."""
    if file_type == "xlsx":
        return process_xlsx_file(local_file)
    elif file_type == "csv":
        return process_csv_file(local_file)
    elif file_type == "zip":
        extracted = process_zip_file(local_file)
        processed = []
        for name in extracted:
            if name.endswith(".xlsx"):
                processed.extend(process_xlsx_file(name))
            elif name.endswith(".csv"):
                processed.extend(process_csv_file(name))
        return processed
    else:
        raise UnsupportedFileTypeError(f"Unsupported file type: {file_type}")


def upload_processed_files(bucket, files_to_upload, args, rename_file):
    """Upload processed files with optional renaming."""
    
    for f in files_to_upload:
        base_name = os.path.basename(f)
        final_name = f"{rename_file}.csv" if rename_file else base_name
        upload_path = f"{args['gcs_folder']}{final_name}"
        upload_file(bucket, upload_path, f)


def cleanup_local(files):
    """Remove local temp files safely."""
    for f in files:
        if os.path.exists(f):
            log_and_print(f"🧹 Cleaning up local file: {f}")
            os.remove(f)

def handle_file(file_name, file_type, bucket, args, rename_file):
    log_and_print(f"\n📂 Handling file: {file_name} (type: {file_type})")
    local_file = os.path.basename(file_name)
    files_to_upload = []

    try:
        # Step 1: Move to archive and download from archive
        move_to_archive_and_download(bucket, file_name, local_file, args)

        # Step 2: ETL (always from archived copy)
        files_to_upload = run_etl(file_type, local_file)

        # Step 3: Upload processed files
        upload_processed_files(bucket, files_to_upload, args, rename_file)

    except Exception as e:
        log_detailed_exception("handle_file", e)
        raise

    finally:
        # Step 4: Cleanup local temp files only
        cleanup_local([local_file] + files_to_upload)



# ---------------------- MAIN ----------------------

def main():
    log_and_print("🚀 Script Started")
    print_sys_arguments()

    log_and_print("🛠️ Parsing arguments...")
    args = parse_arguments()

    log_and_print("🗂️ Setting up logging...")
    setup_logging(args['vm_logfile'])

    log_and_print("🔐 Connecting to GCS...")
    _, bucket = get_gcs_client(args['gcp_token'], args['gcp_project'], args['gcp_bucket'])

    log_and_print(f"📖 Loading config file: {args['vm_config_file']}")
    try:
        with open(args['vm_config_file']) as f:
            config = json.load(f)
    except Exception as e:
        log_detailed_exception("main > load_config", e)
        raise

    log_and_print(f"🔍 Starting processing for file types: {list(config.keys())}")
    for file_type, details in config.items():
        pattern = details['file_mask']
        rename_file = details.get('rename_file', '')

        log_and_print(f"\n📁 Searching for {file_type} files matching: {pattern}")
        matching_files = list_files(bucket, args['gcs_folder'], pattern)

        if not matching_files:
            log_and_print(f"⚠️ No {file_type} files found matching: {pattern}", "warning")
            continue

        for file_name in matching_files:
            try:
                handle_file(file_name, file_type, bucket, args, rename_file)
            except Exception as e:
                log_detailed_exception("main > handle_file", e)
                raise

if __name__ == "__main__":
    main()
