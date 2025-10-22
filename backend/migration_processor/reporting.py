import os
import io
import csv
import json
import time
import uuid
from datetime import datetime, timezone
from audit import log_audit

import boto3
from botocore.exceptions import ClientError, BotoCoreError

# Environment variables expected (configured by your workflow)
REPORT_BUCKET_NAME = os.getenv("REPORT_BUCKET_NAME") or os.getenv("MIGRATION_UPLOAD_BUCKET_NAME")
STACK_NAME = os.getenv("STACK_NAME", "subscriber-migration-stack")
AUDIT_LOG_TABLE_NAME = os.getenv("AUDIT_LOG_TABLE_NAME", "audit-log-table")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
audit_table = dynamodb.Table(AUDIT_LOG_TABLE_NAME)


class ReportingError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_dumps(payload: dict) -> str:
    try:
        return json.dumps(payload, default=str)
    except Exception:
        return json.dumps({"error": "unserializable payload"})


def _s3_put_bytes(bucket: str, key: str, data: bytes, content_type: str = "text/csv") -> str:
    """
    Upload bytes to S3 and return the s3:// URL.
    """
    if not bucket:
        raise ReportingError("REPORT_BUCKET_NAME/MIGRATION_UPLOAD_BUCKET_NAME is not configured")
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="no-store",
        )
        return f"s3://{bucket}/{key}"
    except (ClientError, BotoCoreError) as e:
        raise ReportingError(f"Failed to upload report to S3: {e}")


def _build_csv(rows: list[dict], headers: list[str]) -> bytes:
    """
    Build a CSV in-memory from a list of dicts.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def generate_migration_report(
    job_id: str,
    actor: str,
    summary: dict,
    successes: list[dict],
    failures: list[dict],
    extra_metadata: dict | None = None,
) -> dict:
    """
    Generate CSV reports for a migration job and store them in S3.

    Parameters:
      - job_id: Migration job identifier.
      - actor: User or system triggering the report.
      - summary: Dict like {"total": N, "success": X, "failed": Y, "duration_ms": Z}
      - successes: List of dicts with fields for successful records.
      - failures: List of dicts with fields for failed records (include "error" message).
      - extra_metadata: Optional additional context (region, stack, input file name, etc.)

    Returns:
      {
        "job_id": "...",
        "summary_key": "reports/{job_id}/summary.json",
        "success_csv_key": "... or None",
        "failure_csv_key": "... or None",
        "s3_urls": {
           "summary": "s3://...",
           "success_csv": "s3://... or None",
           "failure_csv": "s3://... or None"
        }
      }
    """
    start = time.time()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_prefix = f"reports/{job_id}/{timestamp}"

    # Compose headers based on observed keys for consistency
    success_headers = set()
    for r in successes:
        success_headers.update(r.keys())
    failure_headers = set()
    for r in failures:
        failure_headers.update(r.keys())
    # Ensure common identifiers first, then others
    canonical_first = ["SubscriberId", "IMSI", "MSISDN"]
    success_headers = canonical_first + sorted([h for h in success_headers if h not in canonical_first])
    failure_headers = canonical_first + sorted([h for h in failure_headers if h not in canonical_first])

    # Build CSVs
    success_key = None
    failure_key = None
    success_url = None
    failure_url = None

    try:
        if successes:
            success_csv = _build_csv(successes, headers=success_headers)
            success_key = f"{base_prefix}/migration_success.csv"
            success_url = _s3_put_bytes(REPORT_BUCKET_NAME, success_key, success_csv, content_type="text/csv")

        if failures:
            # Ensure there's an error column
            for f in failures:
                f.setdefault("error", f.get("reason") or f.get("message") or "unknown_error")
            if "error" not in failure_headers:
                failure_headers.append("error")

            failure_csv = _build_csv(failures, headers=failure_headers)
            failure_key = f"{base_prefix}/migration_failure.csv"
            failure_url = _s3_put_bytes(REPORT_BUCKET_NAME, failure_key, failure_csv, content_type="text/csv")

        # Build summary JSON
        summary_doc = {
            "job_id": job_id,
            "stack": STACK_NAME,
            "timestamp": _now_iso(),
            "summary": summary,
            "counts": {
                "successes": len(successes),
                "failures": len(failures),
            },
            "artifacts": {
                "success_csv": success_key,
                "failure_csv": failure_key,
            },
            "metadata": extra_metadata or {},
        }
        summary_bytes = json.dumps(summary_doc, ensure_ascii=False, indent=2).encode("utf-8")
        summary_key = f"{base_prefix}/summary.json"
        summary_url = _s3_put_bytes(REPORT_BUCKET_NAME, summary_key, summary_bytes, content_type="application/json")

        duration_ms = int((time.time() - start) * 1000)
        result = {
            "job_id": job_id,
            "summary_key": summary_key,
            "success_csv_key": success_key,
            "failure_csv_key": failure_key,
            "s3_urls": {
                "summary": summary_url,
                "success_csv": success_url,
                "failure_csv": failure_url,
            },
            "duration_ms": duration_ms,
        }

        # Audit success using existing log_audit function
        log_audit(
            actor=actor,
            action="GENERATE_MIGRATION_REPORT",
            details={
                "job_id": job_id,
                "summary_key": summary_key,
                "success_key": success_key,
                "failure_key": failure_key,
                "duration_ms": duration_ms,
            },
            status="SUCCESS"
        )
        return result

    except ReportingError as e:
        log_audit(
            actor=actor,
            action="GENERATE_MIGRATION_REPORT",
            details={"job_id": job_id, "error": str(e)},
            status="ERROR"
        )
        raise
    except Exception as e:
        log_audit(
            actor=actor,
            action="GENERATE_MIGRATION_REPORT", 
            details={"job_id": job_id, "error": str(e)},
            status="ERROR"
        )
        raise


def presign_report_url(s3_key: str, expires_in: int = 3600) -> str:
    """
    Generate a pre-signed HTTPS URL for a report object.
    """
    if not REPORT_BUCKET_NAME:
        raise ReportingError("REPORT_BUCKET_NAME/MIGRATION_UPLOAD_BUCKET_NAME is not configured")
    try:
        return s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": REPORT_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=expires_in,
        )
    except (ClientError, BotoCoreError) as e:
        raise ReportingError(f"Failed to presign URL: {e}")


def list_job_reports(job_id: str) -> list[dict]:
    """
    List all report artifacts for a given job_id.
    """
    if not REPORT_BUCKET_NAME:
        raise ReportingError("REPORT_BUCKET_NAME/MIGRATION_UPLOAD_BUCKET_NAME is not configured")

    prefix = f"reports/{job_id}/"
    out = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=REPORT_BUCKET_NAME, Prefix=prefix):
            for obj in page.get("Contents", []):
                out.append(
                    {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat() if hasattr(obj["LastModified"], 'isoformat') else str(obj["LastModified"]),
                        "url": f"s3://{REPORT_BUCKET_NAME}/{obj['Key']}",
                    }
                )
        return out
    except (ClientError, BotoCoreError) as e:
        raise ReportingError(f"Failed to list job reports: {e}")


def get_migration_summary(job_id: str) -> dict:
    """
    Get the summary report for a specific migration job.
    """
    reports = list_job_reports(job_id)
    summary_reports = [r for r in reports if r["key"].endswith("summary.json")]
    
    if not summary_reports:
        raise ReportingError(f"No summary report found for job {job_id}")
    
    # Get the most recent summary (in case there are multiple)
    latest_summary = max(summary_reports, key=lambda x: x["last_modified"])
    
    try:
        # Download and parse the summary JSON
        response = s3.get_object(Bucket=REPORT_BUCKET_NAME, Key=latest_summary["key"])
        summary_data = json.loads(response["Body"].read().decode("utf-8"))
        return summary_data
    except (ClientError, BotoCoreError) as e:
        raise ReportingError(f"Failed to fetch summary report: {e}")


def cleanup_old_reports(days_to_keep: int = 30) -> dict:
    """
    Clean up old migration reports to save storage costs.
    
    Parameters:
      - days_to_keep: Number of days to retain reports (default: 30)
      
    Returns:
      {"deleted_count": N, "saved_bytes": X}
    """
    if not REPORT_BUCKET_NAME:
        raise ReportingError("REPORT_BUCKET_NAME/MIGRATION_UPLOAD_BUCKET_NAME is not configured")
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    deleted_count = 0
    saved_bytes = 0
    
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=REPORT_BUCKET_NAME, Prefix="reports/"):
            objects_to_delete = []
            
            for obj in page.get("Contents", []):
                if obj["LastModified"] < cutoff_date:
                    objects_to_delete.append({"Key": obj["Key"]})
                    saved_bytes += obj["Size"]
            
            # Delete in batches of 1000 (S3 limit)
            if objects_to_delete:
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i:i+1000]
                    s3.delete_objects(
                        Bucket=REPORT_BUCKET_NAME,
                        Delete={"Objects": batch}
                    )
                    deleted_count += len(batch)
        
        # Log the cleanup activity
        log_audit(
            actor="system",
            action="CLEANUP_OLD_REPORTS",
            details={
                "days_to_keep": days_to_keep,
                "deleted_count": deleted_count,
                "saved_bytes": saved_bytes
            },
            status="SUCCESS"
        )
        
        return {"deleted_count": deleted_count, "saved_bytes": saved_bytes}
        
    except (ClientError, BotoCoreError) as e:
        log_audit(
            actor="system",
            action="CLEANUP_OLD_REPORTS",
            details={"error": str(e)},
            status="ERROR"
        )
        raise ReportingError(f"Failed to cleanup old reports: {e}")


# Example usage function
def example_usage():
    """
    Example of how to use the reporting functions.
    """
    # Generate a sample report
    sample_successes = [
        {"SubscriberId": "S001", "IMSI": "123456789012345", "MSISDN": "1234567890"},
        {"SubscriberId": "S002", "IMSI": "123456789012346", "MSISDN": "1234567891"}
    ]
    
    sample_failures = [
        {"SubscriberId": "S003", "IMSI": "123456789012347", "MSISDN": "1234567892", "error": "Duplicate IMSI"},
        {"SubscriberId": "S004", "IMSI": "", "MSISDN": "1234567893", "error": "Missing IMSI"}
    ]
    
    result = generate_migration_report(
        job_id="job-20251022-001",
        actor="admin",
        summary={
            "total": 4,
            "success": 2,
            "failed": 2,
            "duration_ms": 5000
        },
        successes=sample_successes,
        failures=sample_failures,
        extra_metadata={
            "source_file": "uploads/batch-1.csv",
            "region": "us-east-1"
        }
    )
    
    print(f"Report generated: {result['s3_urls']['summary']}")
    
    # Get pre-signed URL for downloading
    download_url = presign_report_url(result["summary_key"], expires_in=3600)
    print(f"Download URL: {download_url}")
    
    return result


if __name__ == "__main__":
    # For testing purposes
    example_usage()
