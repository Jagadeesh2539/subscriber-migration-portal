import boto3
import os
import csv
import io
import json
from datetime import datetime
import legacy_db

# Environment variables
SUBSCRIBER_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
REPORT_BUCKET_NAME = os.environ.get('REPORT_BUCKET_NAME', os.environ.get('MIGRATION_UPLOAD_BUCKET_NAME'))
LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')

print(f"🔧 Environment check:")
print(f"SUBSCRIBER_TABLE_NAME: {SUBSCRIBER_TABLE_NAME}")
print(f"MIGRATION_JOBS_TABLE_NAME: {MIGRATION_JOBS_TABLE_NAME}")
print(f"REPORT_BUCKET_NAME: {REPORT_BUCKET_NAME}")

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
subscribers_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME)

def get_db_credentials():
    """Fetches database credentials securely from AWS Secrets Manager."""
    secrets_client = boto3.client('secretsmanager')
    try:
        print(f"🔑 Getting secret: {LEGACY_DB_SECRET_ARN}")
        response = secrets_client.get_secret_value(SecretId=LEGACY_DB_SECRET_ARN)
        secret = json.loads(response['SecretString'])

        creds = {
            'host': LEGACY_DB_HOST,
            'port': 3306,
            'user': secret['username'],
            'password': secret['password'],
            'database': 'legacydb'
        }
        print(f"✅ DB credentials retrieved for host: {creds['host']}")
        return creds
    except Exception as e:
        print(f"❌ FATAL: Could not retrieve DB credentials: {e}")
        raise

def find_identifier_key(headers):
    """Detects the main identifier from a list of CSV headers."""
    print(f"📋 CSV headers: {headers}")
    for header in headers:
        h_lower = header.lower()
        if h_lower in ['uid', 'imsi', 'msisdn', 'subscriberid', 'subscriber_id']:
            print(f"✅ Found identifier key: {header}")
            return header
    print("❌ No valid identifier key found")
    return None

def lambda_handler(event, context):
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']

    print(f"🚀 Processing s3://{bucket}/{key}")

    job_id = None
    job_type = 'MIGRATION'  # Default
    
    try:
        head_object = s3_client.head_object(Bucket=bucket, Key=key)
        metadata = head_object.get('Metadata', {})
        print(f"📋 S3 metadata: {metadata}")

        job_id = metadata.get('jobid')
        is_simulate_mode = metadata.get('issimulatemode', 'false').lower() == 'true'
        job_type_meta = metadata.get('jobtype', 'migration')
        
        # Determine job type from metadata or key path
        if 'deletion' in job_type_meta or key.startswith('deletions/'):
            job_type = 'BULK_DELETION'
        elif 'audit' in job_type_meta or key.startswith('audits/'):
            job_type = 'AUDIT_SYNC'
        else:
            job_type = 'MIGRATION'

        print(f"🎯 Job ID: {job_id}")
        print(f"📝 Job Type: {job_type}")
        print(f"🧪 Simulate mode: {is_simulate_mode}")

        if not job_id:
            raise Exception("Job ID not found in S3 metadata.")

    except Exception as e:
        print(f"❌ Error getting metadata: {e}")
        if job_id:
            try:
                jobs_table.update_item(
                    Key={'JobId': job_id},
                    UpdateExpression="SET #s=:s, failureReason=:fr",
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={':s': 'FAILED', ':fr': f'Metadata Read Error: {e}'}
                )
            except Exception as update_e:
                print(f"❌ Failed to update job status: {update_e}")
        return {'status': 'error', 'message': str(e)}

    counts = {'total': 0, 'migrated': 0, 'deleted': 0, 'already_present': 0, 'not_found_in_legacy': 0, 'not_found_in_cloud': 0, 'failed': 0, 'synced': 0}
    report_data = [['Identifier', 'Status', 'Details']]

    try:
        # Database connection
        db_creds = get_db_credentials()
        legacy_db.init_connection_details(**db_creds)
        print("✅ Successfully configured legacy DB connector.")

    except Exception as e:
        print(f"❌ DB Connection Error: {e}")
        try:
            jobs_table.update_item(
                Key={'JobId': job_id},
                UpdateExpression="SET #s = :s, failureReason = :fr",
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':s': 'FAILED', ':fr': f'DB Connection Error: {e}'}
            )
        except Exception as update_e:
            print(f"❌ Failed to update job status: {update_e}")
        return {'status': 'error'}

    try:
        # Process CSV
        print("📂 Reading CSV from S3...")
        csv_object = s3_client.get_object(Bucket=bucket, Key=key)
        csv_content = csv_object['Body'].read().decode('utf-8')
        print(f"📄 CSV content length: {len(csv_content)} characters")

        reader = csv.DictReader(io.StringIO(csv_content))

        identifier_key = find_identifier_key(reader.fieldnames)
        if not identifier_key:
            raise Exception("Could not find a valid identifier (uid, imsi, or msisdn) in CSV header.")

        all_rows = list(reader)
        counts['total'] = len(all_rows)
        print(f"📊 Processing {counts['total']} rows for job type: {job_type}")

        # Update job to IN_PROGRESS
        print(f"📈 Updating job {job_id} to IN_PROGRESS...")
        jobs_table.update_item(
            Key={'JobId': job_id},
            UpdateExpression="SET #s = :s, totalRecords = :t",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': 'IN_PROGRESS', ':t': counts['total']}
        )
        print("✅ Job status updated to IN_PROGRESS")

        # Process each row based on job type
        for i, row in enumerate(all_rows):
            identifier_val = row.get(identifier_key)
            print(f"\n--- Processing row {i+1}/{counts['total']}: {identifier_val} (Job: {job_type}) ---")

            if not identifier_val:
                print("⚠��� Identifier value is blank")
                counts['failed'] += 1
                report_data.append([row.get(identifier_key, 'N/A'), 'FAILED', 'Identifier value was blank in CSV row.'])
                continue

            try:
                if job_type == 'MIGRATION':
                    result = process_migration(identifier_val, is_simulate_mode)
                elif job_type == 'BULK_DELETION':
                    result = process_deletion(identifier_val, is_simulate_mode)
                elif job_type == 'AUDIT_SYNC':
                    sync_direction = metadata.get('syncdirection', 'LEGACY_TO_CLOUD')
                    result = process_audit_sync(identifier_val, sync_direction, is_simulate_mode)
                else:
                    result = {'status': 'failed', 'details': f'Unknown job type: {job_type}'}

                counts[result['status']] += 1
                status_display = result['status'].upper().replace('_', ' ')
                report_data.append([identifier_val, status_display, result['details']])

            except Exception as e:
                print(f"❌ ERROR processing {identifier_val}: {e}")
                counts['failed'] += 1
                report_data.append([identifier_val, 'FAILED', str(e)])

        # Create and upload report
        print("📊 Creating job report...")
        report_key = f"reports/{job_id}.csv"
        report_buffer = io.StringIO()
        csv.writer(report_buffer).writerows(report_data)

        report_bucket = REPORT_BUCKET_NAME or bucket
        s3_client.put_object(
            Bucket=report_bucket,
            Key=report_key,
            Body=report_buffer.getvalue()
        )
        print(f"📤 Report uploaded to s3://{report_bucket}/{report_key}")

        # Update job to COMPLETED
        print(f"✅ Updating job {job_id} to COMPLETED...")
        print(f"📈 Final counts: {counts}")

        update_expression_parts = ["#s=:s"]
        expression_values = {':s': 'COMPLETED'}
        
        # Add counts based on job type
        if job_type == 'MIGRATION':
            update_expression_parts.extend([
                "migrated=:m", "alreadyPresent=:ap", "not_found_in_legacy=:nf", "failed=:f"
            ])
            expression_values.update({
                ':m': counts['migrated'],
                ':ap': counts['already_present'],
                ':nf': counts['not_found_in_legacy'],
                ':f': counts['failed']
            })
        elif job_type == 'BULK_DELETION':
            update_expression_parts.extend([
                "deleted=:d", "not_found_in_cloud=:nfc", "failed=:f"
            ])
            expression_values.update({
                ':d': counts['deleted'],
                ':nfc': counts['not_found_in_cloud'],
                ':f': counts['failed']
            })
        elif job_type == 'AUDIT_SYNC':
            update_expression_parts.extend([
                "synced=:sy", "migrated=:m", "failed=:f"
            ])
            expression_values.update({
                ':sy': counts['synced'],
                ':m': counts['migrated'],
                ':f': counts['failed']
            })
        
        update_expression_parts.append("reportS3Key=:rk")
        expression_values[':rk'] = report_key

        jobs_table.update_item(
            Key={'JobId': job_id},
            UpdateExpression="SET " + ", ".join(update_expression_parts),
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues=expression_values
        )
        print(f"🎉 {job_type} completed successfully!")

    except Exception as e:
        print(f"💥 FATAL ERROR during processing: {e}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")

        try:
            jobs_table.update_item(
                Key={'JobId': job_id},
                UpdateExpression="SET #s = :s, failureReason = :fr",
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':s': 'FAILED', ':fr': str(e)}
            )
            print("❌ Job marked as FAILED")
        except Exception as update_e:
            print(f"❌ Failed to update job status: {update_e}")

    finally:
        # Clean up uploaded CSV
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
            print(f"🗑��� Deleted uploaded CSV: {key}")
        except Exception as e:
            print(f"⚠��� Warning: Could not delete uploaded file: {e}")

    return {'status': 'success'}

def process_migration(identifier_val, is_simulate_mode):
    """Process migration from legacy to cloud"""
    try:
        # Query legacy database
        print(f"🔍 Querying legacy DB for {identifier_val}...")
        legacy_data = legacy_db.get_subscriber_by_any_id(identifier_val)
        print(f"📊 Legacy data found: {legacy_data is not None}")

        # Query cloud database with correct key (subscriberId)
        print(f"☁��� Querying cloud DB for subscriberId={identifier_val}...")
        cloud_response = subscribers_table.get_item(Key={'subscriberId': identifier_val})
        cloud_data = cloud_response.get('Item')
        print(f"📊 Cloud data found: {cloud_data is not None}")

        if legacy_data and not cloud_data:
            print(f"🚀 Migrating {identifier_val}...")
            if not is_simulate_mode:
                legacy_data['subscriberId'] = legacy_data['uid']
                subscribers_table.put_item(Item=legacy_data)
                print(f"✅ Successfully migrated {identifier_val}")
                return {'status': 'migrated', 'details': 'Migrated successfully'}
            else:
                print(f"🧪 SIMULATED migration for {identifier_val}")
                return {'status': 'migrated', 'details': 'SIMULATED: Would have been migrated'}

        elif cloud_data:
            print(f"⚠��� Skipping {identifier_val} - already present in cloud")
            return {'status': 'already_present', 'details': 'Already present in cloud'}

        elif not legacy_data:
            print(f"⚠��� Skipping {identifier_val} - not found in legacy")
            return {'status': 'not_found_in_legacy', 'details': 'Not found in legacy DB'}

    except Exception as e:
        print(f"❌ ERROR processing migration {identifier_val}: {e}")
        return {'status': 'failed', 'details': str(e)}

def process_deletion(identifier_val, is_simulate_mode):
    """Process deletion from cloud only"""
    try:
        print(f"🗑��� Querying cloud DB for deletion: subscriberId={identifier_val}...")
        cloud_response = subscribers_table.get_item(Key={'subscriberId': identifier_val})
        cloud_data = cloud_response.get('Item')
        print(f"📊 Cloud data found: {cloud_data is not None}")

        if cloud_data:
            print(f"🗑��� Deleting {identifier_val} from cloud...")
            if not is_simulate_mode:
                subscribers_table.delete_item(Key={'subscriberId': identifier_val})
                print(f"✅ Successfully deleted {identifier_val}")
                return {'status': 'deleted', 'details': 'Deleted from cloud successfully'}
            else:
                print(f"🧪 SIMULATED deletion for {identifier_val}")
                return {'status': 'deleted', 'details': 'SIMULATED: Would have been deleted'}
        else:
            print(f"⚠��� Skipping {identifier_val} - not found in cloud")
            return {'status': 'not_found_in_cloud', 'details': 'Not found in cloud DB'}

    except Exception as e:
        print(f"❌ ERROR processing deletion {identifier_val}: {e}")
        return {'status': 'failed', 'details': str(e)}

def process_audit_sync(identifier_val, sync_direction, is_simulate_mode):
    """Process audit and sync between legacy and cloud"""
    try:
        # Query both databases
        print(f"🔍 Auditing {identifier_val} with direction: {sync_direction}...")
        legacy_data = legacy_db.get_subscriber_by_any_id(identifier_val)
        cloud_response = subscribers_table.get_item(Key={'subscriberId': identifier_val})
        cloud_data = cloud_response.get('Item')

        print(f"📊 Legacy data: {legacy_data is not None}, Cloud data: {cloud_data is not None}")

        if legacy_data and cloud_data:
            # Both exist - check for differences
            differences = []
            if legacy_data.get('imsi') != cloud_data.get('imsi'):
                differences.append('IMSI')
            if legacy_data.get('msisdn') != cloud_data.get('msisdn'):
                differences.append('MSISDN')
            if legacy_data.get('plan') != cloud_data.get('plan'):
                differences.append('Plan')

            if differences:
                if sync_direction in ['LEGACY_TO_CLOUD', 'BOTH_WAYS'] and not is_simulate_mode:
                    legacy_data['subscriberId'] = legacy_data['uid']
                    subscribers_table.put_item(Item=legacy_data)
                    return {'status': 'synced', 'details': f'Synced differences: {", ".join(differences)}'}
                else:
                    return {'status': 'synced', 'details': f'SIMULATED: Would sync differences: {", ".join(differences)}'}
            else:
                return {'status': 'synced', 'details': 'No differences found - data in sync'}

        elif legacy_data and not cloud_data:
            if sync_direction in ['LEGACY_TO_CLOUD', 'BOTH_WAYS']:
                if not is_simulate_mode:
                    legacy_data['subscriberId'] = legacy_data['uid']
                    subscribers_table.put_item(Item=legacy_data)
                    return {'status': 'migrated', 'details': 'Migrated from legacy to cloud'}
                else:
                    return {'status': 'migrated', 'details': 'SIMULATED: Would migrate from legacy to cloud'}
            else:
                return {'status': 'not_found_in_cloud', 'details': 'Exists in legacy only, sync direction prevents migration'}

        elif cloud_data and not legacy_data:
            return {'status': 'not_found_in_legacy', 'details': 'Exists in cloud only'}

        else:
            return {'status': 'failed', 'details': 'Not found in either database'}

    except Exception as e:
        print(f"❌ ERROR processing audit {identifier_val}: {e}")
        return {'status': 'failed', 'details': str(e)}
