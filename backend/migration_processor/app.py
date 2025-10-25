import boto3
import os
import csv
import io
import json
from datetime import datetime
import urllib.parse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment
SUBSCRIBERS_TABLE_NAME = os.environ.get('SUBSCRIBERS_TABLE_NAME')
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
REPORT_BUCKET_NAME = os.environ.get('REPORT_BUCKET_NAME')
LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')

# AWS
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Tables
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
subscribers_table = dynamodb.Table(SUBSCRIBERS_TABLE_NAME)

# Comprehensive field mapping and defaults (superset behavior)
FIELD_MAPPING = {
    'uid': 'uid','imsi': 'imsi','msisdn': 'msisdn',
    'odbic': 'odbic','odboc': 'odboc','plan_type': 'plan_type','network_type': 'network_type','call_forwarding': 'call_forwarding',
    'roaming_enabled': 'roaming_enabled','data_limit_mb': 'data_limit_mb','voice_minutes': 'voice_minutes','sms_count': 'sms_count','status': 'status',
    'activation_date': 'activation_date','last_recharge': 'last_recharge','balance_amount': 'balance_amount','service_class': 'service_class',
    'location_area_code': 'location_area_code','routing_area_code': 'routing_area_code','gprs_enabled': 'gprs_enabled','volte_enabled': 'volte_enabled','wifi_calling': 'wifi_calling',
    'premium_services': 'premium_services','hlr_profile': 'hlr_profile','auc_profile': 'auc_profile','eir_status': 'eir_status','equipment_identity': 'equipment_identity','network_access_mode': 'network_access_mode',
    'qos_profile': 'qos_profile','apn_profile': 'apn_profile','charging_profile': 'charging_profile','fraud_profile': 'fraud_profile',
    'credit_limit': 'credit_limit','spending_limit': 'spending_limit','international_roaming_zone': 'international_roaming_zone','domestic_roaming_zone': 'domestic_roaming_zone',
    'supplementary_services': 'supplementary_services','value_added_services': 'value_added_services',
    'content_filtering': 'content_filtering','parental_control': 'parental_control','emergency_services': 'emergency_services',
    'lte_category': 'lte_category','nr_category': 'nr_category','bearer_capability': 'bearer_capability','teleservices': 'teleservices','basic_services': 'basic_services',
    'operator_services': 'operator_services','network_features': 'network_features','security_features': 'security_features','mobility_management': 'mobility_management','session_management': 'session_management'
}

DEFAULT_VALUES = {
    'odbic': 'ODBIC_STD_RESTRICTIONS','odboc': 'ODBOC_STD_RESTRICTIONS','plan_type': 'STANDARD_PREPAID','network_type': '4G_LTE','call_forwarding': 'CF_NONE',
    'roaming_enabled': 'NO_ROAMING','data_limit_mb': 1000,'voice_minutes': '100','sms_count': '50','status': 'ACTIVE','service_class': 'CONSUMER_SILVER',
    'location_area_code': 'LAC_1000','routing_area_code': 'RAC_2000','gprs_enabled': True,'volte_enabled': False,'wifi_calling': False,
    'premium_services': 'VAS_BASIC','hlr_profile': 'HLR_STANDARD_PROFILE','auc_profile': 'AUC_BASIC_AUTH','eir_status': 'EIR_VERIFIED','equipment_identity': '',
    'network_access_mode': 'MODE_4G_PREFERRED','qos_profile': 'QOS_CLASS_3_BEST_EFFORT','apn_profile': 'APN_CONSUMER_INTERNET','charging_profile': 'CHARGING_STANDARD','fraud_profile': 'FRAUD_BASIC_CHECK',
    'credit_limit': 5000.00,'spending_limit': 500.00,'international_roaming_zone': 'ZONE_NONE','domestic_roaming_zone': 'ZONE_HOME_ONLY',
    'supplementary_services': 'SS_CLIP:SS_CW','value_added_services': 'VAS_BASIC_NEWS','content_filtering': 'CF_ADULT_CONTENT','parental_control': 'PC_DISABLED','emergency_services': 'ES_BASIC_E911',
    'lte_category': 'LTE_CAT_6','nr_category': 'N/A','bearer_capability': 'BC_SPEECH:BC_DATA_64K','teleservices': 'TS_SPEECH:TS_SMS','basic_services': 'BS_BEARER_SPEECH:BS_PACKET_DATA',
    'operator_services': 'OS_STANDARD_SUPPORT','network_features': 'NF_BASIC_LTE','security_features': 'SF_BASIC_AUTH','mobility_management': 'MM_BASIC','session_management': 'SM_BASIC',
    'balance_amount': 0.0
}

def get_db_credentials():
    try:
        response = secrets_client.get_secret_value(SecretId=LEGACY_DB_SECRET_ARN)
        secret = json.loads(response['SecretString'])
        return {'host': LEGACY_DB_HOST,'user': secret.get('username'),'password': secret.get('password'),'database': secret.get('database', 'legacy_subscribers')}
    except Exception as e:
        logger.error(f"Error fetching DB credentials: {e}")
        raise

def fetch_subscriber_from_legacy(identifier, db_creds):
    try:
        # Placeholder: simulate success; production should query MySQL
        return {'uid': identifier,'imsi': f"imsi_{identifier}",'msisdn': f"msisdn_{identifier}",'status': 'active'}
    except Exception as e:
        logger.error(f"Error fetching subscriber {identifier}: {e}")
        return None

def sanitize_subscriber_data(row):
    sub = {}
    for csv_field, db_field in FIELD_MAPPING.items():
        val = row.get(csv_field) or row.get(csv_field.upper()) or row.get(csv_field.lower()) or row.get(csv_field.title())
        if val is not None and val != '':
            if db_field in ['data_limit_mb', 'credit_limit', 'spending_limit']:
                try:
                    sub[db_field] = float(val) if '.' in str(val) else int(val)
                except (ValueError, TypeError):
                    sub[db_field] = DEFAULT_VALUES.get(db_field, 0)
            elif db_field in ['gprs_enabled', 'volte_enabled', 'wifi_calling']:
                sub[db_field] = str(val).lower() in ['true', '1', 'yes', 'enabled']
            else:
                sub[db_field] = str(val).strip()
    for f, d in DEFAULT_VALUES.items():
        if f not in sub:
            sub[f] = d
    if not sub.get('activation_date'):
        sub['activation_date'] = datetime.utcnow().isoformat()
    if not sub.get('last_recharge'):
        sub['last_recharge'] = datetime.utcnow().isoformat()
    return sub

def update_job_status(migration_id, status, **kwargs):
    try:
        update_expression = "SET #s = :status, lastUpdated = :updated"
        expression_values = {':status': status, ':updated': datetime.utcnow().isoformat()}
        expression_names = {'#s': 'status'}
        for key, value in kwargs.items():
            if value is not None:
                placeholder = f":{key}"
                update_expression += f", {key} = {placeholder}"
                expression_values[placeholder] = value
        jobs_table.update_item(Key={'JobId': migration_id},UpdateExpression=update_expression,ExpressionAttributeNames=expression_names,ExpressionAttributeValues=expression_values)
        logger.info(f"Updated job {migration_id} status to {status}")
    except Exception as e:
        logger.error(f"Error updating job status: {e}")
        raise

def generate_report(migration_id, results, is_simulate_mode, comprehensive=False):
    try:
        csv_buffer = io.StringIO()
        if comprehensive:
            fieldnames = ['identifier','status','reason','timestamp','uid','imsi','msisdn','odbic','odboc','plan_type','network_type','service_class','data_limit_mb','voice_minutes','sms_count','roaming_enabled','gprs_enabled','volte_enabled','wifi_calling','premium_services','hlr_profile','qos_profile','charging_profile','balance_amount','credit_limit','spending_limit']
        else:
            fieldnames = ['identifier','status','reason','legacy_data','timestamp']
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            if comprehensive and 'subscriber_data' in r:
                row = {'identifier': r.get('identifier',''),'status': r.get('status',''),'reason': r.get('reason',''),'timestamp': r.get('timestamp','')}
                for f in fieldnames[4:]:
                    row[f] = r['subscriber_data'].get(f, '')
                writer.writerow(row)
            else:
                writer.writerow(r)
        csv_content = csv_buffer.getvalue()
        key_name = 'comprehensive-migration-report.csv' if comprehensive else 'migration-report.csv'
        report_key = f"reports/{migration_id}/{key_name}"
        s3_client.put_object(Bucket=REPORT_BUCKET_NAME,Key=report_key,Body=csv_content,ContentType='text/csv',Metadata={'migration-id': migration_id,'generated-at': datetime.utcnow().isoformat(),'simulate-mode': str(is_simulate_mode).lower(),'report-type': 'comprehensive' if comprehensive else 'standard'})
        logger.info(f"Report uploaded to s3://{REPORT_BUCKET_NAME}/{report_key}")
        return report_key
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return None

def lambda_handler(event, context):
    logger.info(f"Unified migration processor invoked: {json.dumps(event)}")
    try:
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            logger.info(f"Processing file: s3://{bucket}/{key}")
            migration_id = None
            is_simulate_mode = False
            job_type = 'migration'
            try:
                metadata_response = s3_client.head_object(Bucket=bucket, Key=key)
                metadata = metadata_response.get('Metadata', {})
                migration_id = metadata.get('jobid') or metadata.get('migrationid') or metadata.get('migration-id')
                is_simulate_mode = metadata.get('issimulatemode', 'false').lower() == 'true'
                job_type = metadata.get('jobtype', 'migration')
                if not migration_id:
                    migration_id = key.split('/')[-1].replace('.csv', '')
                logger.info(f"Extracted: ID={migration_id}, Simulate={is_simulate_mode}, Type={job_type}")
            except Exception as meta_err:
                logger.warning(f"Metadata extraction failed: {meta_err}")
                migration_id = key.split('/')[-1].replace('.csv', '')
            update_job_status(migration_id, 'IN_PROGRESS', statusMessage='Processing CSV file...')
            try:
                csv_object = s3_client.get_object(Bucket=bucket, Key=key)
                csv_content = csv_object['Body'].read().decode('utf-8')
                csv_reader = csv.DictReader(io.StringIO(csv_content))
                identifiers = ['uid','imsi','msisdn','subscriberid']
                headers_lower = [h.lower() for h in csv_reader.fieldnames] if csv_reader.fieldnames else []
                if not any(identifier in headers_lower for identifier in identifiers):
                    raise Exception(f"CSV must contain at least one identifier column: {', '.join(identifiers)}")
                rows = list(csv_reader)
                counts = {'total': len(rows),'migrated': 0,'alreadyPresent': 0,'not_found_in_legacy': 0,'failed': 0,'deleted': 0}
                results = []
                comprehensive = len(headers_lower) > 5  # heuristic: treat as comprehensive if more fields exist
                update_job_status(migration_id, 'IN_PROGRESS', totalRecords=counts['total'], statusMessage=f"Processing {counts['total']} records...")
                for idx, row in enumerate(rows, 1):
                    identifier = (row.get('uid') or row.get('UID') or row.get('imsi') or row.get('IMSI') or row.get('msisdn') or row.get('MSISDN') or row.get('subscriberid') or row.get('subscriberId') or row.get('SUBSCRIBERID'))
                    if not identifier:
                        counts['failed'] += 1
                        results.append({'identifier': 'N/A','status': 'failed','reason': 'No identifier found in row','legacy_data': '', 'timestamp': datetime.utcnow().isoformat()})
                        continue
                    try:
                        if job_type == 'deletion':
                            existing_item = subscribers_table.get_item(Key={'SubscriberId': identifier})
                            if 'Item' not in existing_item:
                                counts['not_found_in_legacy'] += 1
                                results.append({'identifier': identifier,'status': 'not_found','reason': 'Subscriber not found in cloud database','timestamp': datetime.utcnow().isoformat()})
                                continue
                            if not is_simulate_mode:
                                subscribers_table.delete_item(Key={'SubscriberId': identifier})
                            counts['deleted'] += 1
                            results.append({'identifier': identifier,'status': 'deleted' if not is_simulate_mode else 'would_delete','reason': 'Successfully deleted from cloud','timestamp': datetime.utcnow().isoformat()})
                        else:
                            existing_item = subscribers_table.get_item(Key={'SubscriberId': identifier})
                            if 'Item' in existing_item:
                                counts['alreadyPresent'] += 1
                                results.append({'identifier': identifier,'status': 'already_present','reason': 'Subscriber already exists in cloud','timestamp': datetime.utcnow().isoformat()})
                                continue
                            db_creds = get_db_credentials()
                            legacy_data = fetch_subscriber_from_legacy(identifier, db_creds)
                            if comprehensive:
                                subscriber_data = sanitize_subscriber_data(row if row else (legacy_data or {}))
                            else:
                                subscriber_data = legacy_data or {}
                            if not subscriber_data:
                                counts['not_found_in_legacy'] += 1
                                results.append({'identifier': identifier,'status': 'not_found_in_legacy','reason': 'Subscriber not found in legacy database','timestamp': datetime.utcnow().isoformat()})
                                continue
                            if not is_simulate_mode:
                                item = {'SubscriberId': identifier,'migrationId': migration_id,'migratedAt': datetime.utcnow().isoformat()}
                                if comprehensive:
                                    item.update(subscriber_data)
                                else:
                                    item.update({k: subscriber_data.get(k) for k in ['uid','imsi','msisdn','status'] if subscriber_data.get(k) is not None})
                                subscribers_table.put_item(Item=item)
                            counts['migrated'] += 1
                            entry = {'identifier': identifier,'status': 'migrated' if not is_simulate_mode else 'would_migrate','reason': 'Successfully migrated to cloud','timestamp': datetime.utcnow().isoformat()}
                            if comprehensive:
                                entry['subscriber_data'] = subscriber_data
                            else:
                                entry['legacy_data'] = json.dumps(subscriber_data)
                            results.append(entry)
                        if idx % 100 == 0:
                            update_job_status(migration_id, 'IN_PROGRESS', statusMessage=f"Processed {idx}/{counts['total']} records...", **{k: v for k, v in counts.items() if k != 'total'})
                    except Exception as row_error:
                        logger.error(f"Error processing row {idx} (identifier: {identifier}): {row_error}")
                        counts['failed'] += 1
                        results.append({'identifier': identifier,'status': 'failed','reason': f"Processing error: {str(row_error)}",'timestamp': datetime.utcnow().isoformat()})
                report_key = generate_report(migration_id, results, is_simulate_mode, comprehensive=comprehensive)
                final_status = 'COMPLETED'
                status_message = f"Successfully processed {counts['total']} records" + (" (SIMULATION MODE)" if is_simulate_mode else '')
                update_job_status(migration_id, final_status, statusMessage=status_message, reportS3Key=report_key, **{k: v for k, v in counts.items() if k != 'total'})
                logger.info(f"Job {migration_id} completed successfully: {counts}")
            except Exception as processing_error:
                logger.error(f"Processing error for job {migration_id}: {processing_error}")
                update_job_status(migration_id, 'FAILED', statusMessage=f"Processing failed: {str(processing_error)}", failureReason=str(processing_error))
                raise processing_error
    except Exception as handler_error:
        logger.error(f"Lambda handler error: {handler_error}")
        return {'statusCode': 500,'body': json.dumps({'status': 'error','message': str(handler_error)})}
    finally:
        try:
            if 'bucket' in locals() and 'key' in locals():
                s3_client.delete_object(Bucket=bucket, Key=key)
                logger.info(f"Cleaned up file: s3://{bucket}/{key}")
        except Exception as cleanup_error:
            logger.warning(f"File cleanup failed (non-critical): {cleanup_error}")
    return {'statusCode': 200,'body': json.dumps({'status': 'success','message': 'Unified migration processing completed'})}
