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

# Get environment variables
SUBSCRIBERS_TABLE_NAME = os.environ.get('SUBSCRIBERS_TABLE_NAME')
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
REPORT_BUCKET_NAME = os.environ.get('REPORT_BUCKET_NAME')
LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Initialize DynamoDB tables
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
subscribers_table = dynamodb.Table(SUBSCRIBERS_TABLE_NAME)

# Industry-ready field mapping
FIELD_MAPPING = {
    # Core fields (existing)
    'uid': 'uid',
    'imsi': 'imsi', 
    'msisdn': 'msisdn',
    
    # Enhanced telecom fields
    'odbic': 'odbic',
    'odboc': 'odboc',
    'plan_type': 'plan_type',
    'network_type': 'network_type',
    'call_forwarding': 'call_forwarding',
    'roaming_enabled': 'roaming_enabled',
    'data_limit_mb': 'data_limit_mb',
    'voice_minutes': 'voice_minutes',
    'sms_count': 'sms_count',
    'status': 'status',
    'activation_date': 'activation_date',
    'last_recharge': 'last_recharge',
    'balance_amount': 'balance_amount',
    'service_class': 'service_class',
    'location_area_code': 'location_area_code',
    'routing_area_code': 'routing_area_code',
    'gprs_enabled': 'gprs_enabled',
    'volte_enabled': 'volte_enabled',
    'wifi_calling': 'wifi_calling',
    'premium_services': 'premium_services',
    'hlr_profile': 'hlr_profile',
    'auc_profile': 'auc_profile',
    'eir_status': 'eir_status',
    'equipment_identity': 'equipment_identity',
    'network_access_mode': 'network_access_mode',
    'qos_profile': 'qos_profile',
    'apn_profile': 'apn_profile',
    'charging_profile': 'charging_profile',
    'fraud_profile': 'fraud_profile',
    'credit_limit': 'credit_limit',
    'spending_limit': 'spending_limit',
    'international_roaming_zone': 'international_roaming_zone',
    'domestic_roaming_zone': 'domestic_roaming_zone',
    'supplementary_services': 'supplementary_services',
    'value_added_services': 'value_added_services',
    'content_filtering': 'content_filtering',
    'parental_control': 'parental_control',
    'emergency_services': 'emergency_services',
    'lte_category': 'lte_category',
    'nr_category': 'nr_category',
    'bearer_capability': 'bearer_capability',
    'teleservices': 'teleservices',
    'basic_services': 'basic_services',
    'operator_services': 'operator_services',
    'network_features': 'network_features',
    'security_features': 'security_features',
    'mobility_management': 'mobility_management',
    'session_management': 'session_management'
}

# Default values for missing fields
DEFAULT_VALUES = {
    'odbic': 'ODBIC_STD_RESTRICTIONS',
    'odboc': 'ODBOC_STD_RESTRICTIONS',
    'plan_type': 'STANDARD_PREPAID',
    'network_type': '4G_LTE',
    'call_forwarding': 'CF_NONE',
    'roaming_enabled': 'NO_ROAMING',
    'data_limit_mb': 1000,
    'voice_minutes': '100',
    'sms_count': '50',
    'status': 'ACTIVE',
    'service_class': 'CONSUMER_SILVER',
    'location_area_code': 'LAC_1000',
    'routing_area_code': 'RAC_2000',
    'gprs_enabled': True,
    'volte_enabled': False,
    'wifi_calling': False,
    'premium_services': 'VAS_BASIC',
    'hlr_profile': 'HLR_STANDARD_PROFILE',
    'auc_profile': 'AUC_BASIC_AUTH',
    'eir_status': 'EIR_VERIFIED',
    'equipment_identity': '',
    'network_access_mode': 'MODE_4G_PREFERRED',
    'qos_profile': 'QOS_CLASS_3_BEST_EFFORT',
    'apn_profile': 'APN_CONSUMER_INTERNET',
    'charging_profile': 'CHARGING_STANDARD',
    'fraud_profile': 'FRAUD_BASIC_CHECK',
    'credit_limit': 5000.00,
    'spending_limit': 500.00,
    'international_roaming_zone': 'ZONE_NONE',
    'domestic_roaming_zone': 'ZONE_HOME_ONLY',
    'supplementary_services': 'SS_CLIP:SS_CW',
    'value_added_services': 'VAS_BASIC_NEWS',
    'content_filtering': 'CF_ADULT_CONTENT',
    'parental_control': 'PC_DISABLED',
    'emergency_services': 'ES_BASIC_E911',
    'lte_category': 'LTE_CAT_6',
    'nr_category': 'N/A',
    'bearer_capability': 'BC_SPEECH:BC_DATA_64K',
    'teleservices': 'TS_SPEECH:TS_SMS',
    'basic_services': 'BS_BEARER_SPEECH:BS_PACKET_DATA',
    'operator_services': 'OS_STANDARD_SUPPORT',
    'network_features': 'NF_BASIC_LTE',
    'security_features': 'SF_BASIC_AUTH',
    'mobility_management': 'MM_BASIC',
    'session_management': 'SM_BASIC',
    'balance_amount': 0.0
}

def sanitize_subscriber_data(row_data):
    """
    Sanitizes and transforms CSV row data into comprehensive subscriber object
    """
    subscriber = {}
    
    # Map CSV fields to subscriber fields
    for csv_field, db_field in FIELD_MAPPING.items():
        # Try different case variations
        value = (
            row_data.get(csv_field) or 
            row_data.get(csv_field.upper()) or 
            row_data.get(csv_field.lower()) or 
            row_data.get(csv_field.title())
        )
        
        if value is not None and value != '':
            # Type conversion based on field
            if db_field in ['data_limit_mb', 'credit_limit', 'spending_limit']:
                try:
                    if '.' in str(value):
                        subscriber[db_field] = float(value)
                    else:
                        subscriber[db_field] = int(value)
                except (ValueError, TypeError):
                    subscriber[db_field] = DEFAULT_VALUES.get(db_field, 0)
            elif db_field in ['gprs_enabled', 'volte_enabled', 'wifi_calling']:
                subscriber[db_field] = str(value).lower() in ['true', '1', 'yes', 'enabled']
            else:
                subscriber[db_field] = str(value).strip()
    
    # Apply defaults for missing fields
    for field, default_value in DEFAULT_VALUES.items():
        if field not in subscriber:
            subscriber[field] = default_value
    
    # Ensure required timestamps
    if 'activation_date' not in subscriber or not subscriber['activation_date']:
        subscriber['activation_date'] = datetime.utcnow().isoformat()
    
    if 'last_recharge' not in subscriber or not subscriber['last_recharge']:
        subscriber['last_recharge'] = datetime.utcnow().isoformat()
    
    return subscriber

def get_db_credentials():
    """Fetches database credentials from Secrets Manager"""
    try:
        response = secrets_client.get_secret_value(SecretId=LEGACY_DB_SECRET_ARN)
        secret = json.loads(response['SecretString'])
        return {
            'host': LEGACY_DB_HOST,
            'user': secret.get('username'),
            'password': secret.get('password'),
            'database': secret.get('database', 'legacy_subscribers')
        }
    except Exception as e:
        logger.error(f"Error fetching DB credentials: {e}")
        raise

def fetch_subscriber_from_legacy(identifier, db_creds):
    """Fetch comprehensive subscriber data from legacy database"""
    try:
        # For now, simulate comprehensive subscriber data
        # In production, this would query the actual MySQL database
        
        # Simulate different data based on identifier pattern
        if identifier.startswith('ENT'):
            return {
                'uid': identifier,
                'imsi': f'404103548762{identifier[-3:]}',
                'msisdn': f'91987654{identifier[-4:]}',
                'odbic': 'ODBIC_CAT1_BARRED',
                'odboc': 'ODBOC_PREMIUM_RESTRICTED',
                'plan_type': 'CORPORATE_POSTPAID',
                'network_type': '5G_SA_NSA',
                'call_forwarding': 'CF_CFU:919999888777;CF_CFB:919999888778',
                'roaming_enabled': 'GLOBAL_ROAMING',
                'data_limit_mb': 999999,
                'voice_minutes': 'UNLIMITED',
                'sms_count': 'UNLIMITED',
                'status': 'ACTIVE',
                'service_class': 'ENTERPRISE_PLATINUM',
                'premium_services': 'VAS_ENTERPRISE_SUITE:CLOUD_PBX:VIDEO_CONF'
            }
        elif identifier.startswith('BIZ'):
            return {
                'uid': identifier,
                'imsi': f'404586321458{identifier[-3:]}',
                'msisdn': f'91876543{identifier[-4:]}',
                'odbic': 'ODBIC_INTL_PREMIUM_ALLOWED',
                'odboc': 'ODBOC_STD_RESTRICTIONS',
                'plan_type': 'BUSINESS_POSTPAID',
                'network_type': '5G_NSA',
                'call_forwarding': 'CF_CFB:918888777666',
                'roaming_enabled': 'REGIONAL_ROAMING_PLUS',
                'data_limit_mb': 100000,
                'voice_minutes': '5000',
                'sms_count': '2000',
                'status': 'ACTIVE',
                'service_class': 'BUSINESS_GOLD',
                'premium_services': 'VAS_BUSINESS_PACK:MOBILE_BANKING'
            }
        else:
            return {
                'uid': identifier,
                'imsi': f'404203698741{identifier[-3:]}',
                'msisdn': f'91765432{identifier[-4:]}',
                'odbic': 'ODBIC_STD_RESTRICTIONS',
                'odboc': 'ODBOC_BASIC_BARRING',
                'plan_type': 'STANDARD_PREPAID',
                'network_type': '4G_LTE',
                'call_forwarding': 'CF_CFNRY:917777666555',
                'roaming_enabled': 'NO_ROAMING',
                'data_limit_mb': 15000,
                'voice_minutes': '300',
                'sms_count': '100',
                'status': 'ACTIVE',
                'service_class': 'CONSUMER_SILVER',
                'premium_services': 'VAS_BASIC:NEWS_ALERTS'
            }
    except Exception as e:
        logger.error(f"Error fetching subscriber {identifier}: {e}")
        return None

def update_job_status(migration_id, status, **kwargs):
    """Update job status in DynamoDB"""
    try:
        update_expression = "SET #s = :status, lastUpdated = :updated"
        expression_values = {
            ':status': status,
            ':updated': datetime.utcnow().isoformat()
        }
        expression_names = {'#s': 'status'}
        
        # Add optional fields
        for key, value in kwargs.items():
            if value is not None:
                placeholder = f":{key}"
                update_expression += f", {key} = {placeholder}"
                expression_values[placeholder] = value
        
        jobs_table.update_item(
            Key={'JobId': migration_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )
        logger.info(f"Updated job {migration_id} status to {status}")
        
    except Exception as e:
        logger.error(f"Error updating job status: {e}")
        raise

def generate_comprehensive_report(migration_id, results, is_simulate_mode):
    """Generate comprehensive CSV report with all subscriber fields"""
    try:
        # Create CSV content with all fields
        csv_buffer = io.StringIO()
        fieldnames = [
            'identifier', 'status', 'reason', 'timestamp',
            # Core fields
            'uid', 'imsi', 'msisdn',
            # Service config
            'odbic', 'odboc', 'plan_type', 'network_type', 'service_class',
            # Limits and features
            'data_limit_mb', 'voice_minutes', 'sms_count', 'roaming_enabled',
            'gprs_enabled', 'volte_enabled', 'wifi_calling',
            # Advanced features
            'premium_services', 'hlr_profile', 'qos_profile', 'charging_profile',
            # Financial
            'balance_amount', 'credit_limit', 'spending_limit'
        ]
        
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        
        for result in results:
            # Flatten subscriber data for CSV
            row = {
                'identifier': result.get('identifier', ''),
                'status': result.get('status', ''),
                'reason': result.get('reason', ''),
                'timestamp': result.get('timestamp', '')
            }
            
            # Add subscriber data if present
            if 'subscriber_data' in result:
                subscriber_data = result['subscriber_data']
                for field in fieldnames[4:]:  # Skip first 4 meta fields
                    row[field] = subscriber_data.get(field, '')
            
            writer.writerow(row)
        
        csv_content = csv_buffer.getvalue()
        
        # Upload to S3
        report_key = f"reports/{migration_id}/comprehensive-migration-report.csv"
        s3_client.put_object(
            Bucket=REPORT_BUCKET_NAME,
            Key=report_key,
            Body=csv_content,
            ContentType='text/csv',
            Metadata={
                'migration-id': migration_id,
                'generated-at': datetime.utcnow().isoformat(),
                'simulate-mode': str(is_simulate_mode).lower(),
                'report-type': 'comprehensive'
            }
        )
        
        logger.info(f"Comprehensive report uploaded to s3://{REPORT_BUCKET_NAME}/{report_key}")
        return report_key
        
    except Exception as e:
        logger.error(f"Error generating comprehensive report: {e}")
        return None

def lambda_handler(event, context):
    """Enhanced Lambda handler for processing comprehensive migration files"""
    logger.info(f"Enhanced migration processor invoked with event: {json.dumps(event)}")
    
    try:
        # Parse S3 event
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            
            logger.info(f"Processing comprehensive file: s3://{bucket}/{key}")
            
            # Extract migration details
            migration_id = None
            is_simulate_mode = False
            job_type = 'migration'
            
            try:
                # Get object metadata
                metadata_response = s3_client.head_object(Bucket=bucket, Key=key)
                metadata = metadata_response.get('Metadata', {})
                
                migration_id = (
                    metadata.get('jobid') or 
                    metadata.get('migrationid') or
                    metadata.get('migration-id')
                )
                is_simulate_mode = metadata.get('issimulatemode', 'false').lower() == 'true'
                job_type = metadata.get('jobtype', 'migration')
                
                if not migration_id:
                    migration_id = key.split('/')[-1].replace('.csv', '')
                    
                logger.info(f"Processing: ID={migration_id}, Simulate={is_simulate_mode}, Type={job_type}")
                
            except Exception as metadata_error:
                logger.error(f"Metadata extraction failed: {metadata_error}")
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'status': 'error',
                        'message': f'Could not determine migration ID: {str(metadata_error)}'
                    })
                }
            
            # Update job status to IN_PROGRESS
            update_job_status(migration_id, 'IN_PROGRESS', 
                            statusMessage='Processing comprehensive CSV file...')
            
            # Download and process CSV file
            try:
                csv_object = s3_client.get_object(Bucket=bucket, Key=key)
                csv_content = csv_object['Body'].read().decode('utf-8')
                csv_reader = csv.DictReader(io.StringIO(csv_content))
                
                # Validate CSV has identifier columns
                identifiers = ['uid', 'imsi', 'msisdn', 'subscriberid']
                headers_lower = [h.lower() for h in csv_reader.fieldnames] if csv_reader.fieldnames else []
                
                if not any(identifier in headers_lower for identifier in identifiers):
                    raise Exception(f"CSV must contain at least one identifier column: {', '.join(identifiers)}")
                
                logger.info(f"CSV validated with {len(headers_lower)} headers including comprehensive fields")
                
                # Process all rows
                all_rows = list(csv_reader)
                counts = {
                    'total': len(all_rows),
                    'migrated': 0,
                    'alreadyPresent': 0,
                    'not_found_in_legacy': 0,
                    'failed': 0,
                    'deleted': 0
                }
                
                results = []  # For comprehensive report generation
                
                logger.info(f"Processing {counts['total']} comprehensive rows (Simulate: {is_simulate_mode})")
                
                # Update job with total count
                update_job_status(migration_id, 'IN_PROGRESS', 
                                totalRecords=counts['total'],
                                statusMessage=f'Processing {counts["total"]} comprehensive records...')
                
                # Process each row with comprehensive data
                for idx, row in enumerate(all_rows, 1):
                    # Get identifier from row
                    identifier = (
                        row.get('uid') or row.get('UID') or
                        row.get('imsi') or row.get('IMSI') or  
                        row.get('msisdn') or row.get('MSISDN') or
                        row.get('subscriberid') or row.get('subscriberId')
                    )
                    
                    if not identifier:
                        counts['failed'] += 1
                        results.append({
                            'identifier': 'N/A',
                            'status': 'failed',
                            'reason': 'No identifier found in row',
                            'timestamp': datetime.utcnow().isoformat()
                        })
                        continue
                    
                    try:
                        if job_type == 'deletion':
                            # Handle deletion (existing logic)
                            existing_item = subscribers_table.get_item(Key={'SubscriberId': identifier})
                            
                            if 'Item' not in existing_item:
                                counts['not_found_in_legacy'] += 1
                                results.append({
                                    'identifier': identifier,
                                    'status': 'not_found',
                                    'reason': 'Subscriber not found in cloud database',
                                    'timestamp': datetime.utcnow().isoformat()
                                })
                                continue
                            
                            if not is_simulate_mode:
                                subscribers_table.delete_item(Key={'SubscriberId': identifier})
                                
                            counts['deleted'] += 1
                            results.append({
                                'identifier': identifier,
                                'status': 'deleted' if not is_simulate_mode else 'would_delete',
                                'reason': 'Successfully deleted from cloud',
                                'subscriber_data': existing_item['Item'],
                                'timestamp': datetime.utcnow().isoformat()
                            })
                            
                        else:
                            # Handle comprehensive migration
                            existing_item = subscribers_table.get_item(Key={'SubscriberId': identifier})
                            
                            if 'Item' in existing_item:
                                counts['alreadyPresent'] += 1
                                results.append({
                                    'identifier': identifier,
                                    'status': 'already_present',
                                    'reason': 'Subscriber already exists in cloud',
                                    'subscriber_data': existing_item['Item'],
                                    'timestamp': datetime.utcnow().isoformat()
                                })
                                continue
                            
                            # Process comprehensive data from CSV or legacy
                            if len(row.keys()) > 3:  # CSV has comprehensive data
                                subscriber_data = sanitize_subscriber_data(row)
                                logger.info(f"Using comprehensive CSV data for {identifier}")
                            else:
                                # Fetch from legacy system
                                db_creds = get_db_credentials()
                                legacy_data = fetch_subscriber_from_legacy(identifier, db_creds)
                                
                                if not legacy_data:
                                    counts['not_found_in_legacy'] += 1
                                    results.append({
                                        'identifier': identifier,
                                        'status': 'not_found_in_legacy',
                                        'reason': 'Subscriber not found in legacy database',
                                        'timestamp': datetime.utcnow().isoformat()
                                    })
                                    continue
                                
                                subscriber_data = sanitize_subscriber_data(legacy_data)
                                logger.info(f"Using legacy data for {identifier}")
                            
                            # Migrate comprehensive data to cloud
                            if not is_simulate_mode:
                                # Prepare DynamoDB item
                                dynamodb_item = {
                                    'SubscriberId': identifier,
                                    'migrationId': migration_id,
                                    'migratedAt': datetime.utcnow().isoformat()
                                }
                                dynamodb_item.update(subscriber_data)
                                
                                subscribers_table.put_item(Item=dynamodb_item)
                            
                            counts['migrated'] += 1
                            results.append({
                                'identifier': identifier,
                                'status': 'migrated' if not is_simulate_mode else 'would_migrate',
                                'reason': 'Successfully migrated comprehensive data to cloud',
                                'subscriber_data': subscriber_data,
                                'timestamp': datetime.utcnow().isoformat()
                            })
                        
                        # Update progress every 50 records
                        if idx % 50 == 0:
                            progress_msg = f'Processed {idx}/{counts["total"]} comprehensive records...'
                            update_job_status(migration_id, 'IN_PROGRESS',
                                            statusMessage=progress_msg,
                                            **{k: v for k, v in counts.items() if k != 'total'})
                            logger.info(f"Progress update: {progress_msg}")
                        
                    except Exception as row_error:
                        logger.error(f"Error processing comprehensive row {idx} (identifier: {identifier}): {row_error}")
                        counts['failed'] += 1
                        results.append({
                            'identifier': identifier,
                            'status': 'failed',
                            'reason': f'Processing error: {str(row_error)}',
                            'timestamp': datetime.utcnow().isoformat()
                        })
                
                # Generate comprehensive report
                report_key = generate_comprehensive_report(migration_id, results, is_simulate_mode)
                
                # Update job to completed status
                final_status = 'COMPLETED'
                status_message = f"Successfully processed {counts['total']} comprehensive records"
                
                if is_simulate_mode:
                    status_message += " (SIMULATION MODE)"
                
                update_job_status(
                    migration_id, 
                    final_status,
                    statusMessage=status_message,
                    reportS3Key=report_key,
                    **{k: v for k, v in counts.items() if k != 'total'}
                )
                
                logger.info(f"Comprehensive job {migration_id} completed successfully: {counts}")
                
            except Exception as processing_error:
                logger.error(f"Processing error for comprehensive job {migration_id}: {processing_error}")
                
                # Update job to failed status
                update_job_status(
                    migration_id,
                    'FAILED',
                    statusMessage=f'Comprehensive processing failed: {str(processing_error)}',
                    failureReason=str(processing_error)
                )
                
                raise processing_error
                
    except Exception as handler_error:
        logger.error(f"Enhanced Lambda handler error: {handler_error}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'message': str(handler_error)
            })
        }
    
    finally:
        # Clean up processed file
        try:
            if 'bucket' in locals() and 'key' in locals():
                s3_client.delete_object(Bucket=bucket, Key=key)
                logger.info(f"Cleaned up comprehensive file: s3://{bucket}/{key}")
        except Exception as cleanup_error:
            logger.warning(f"File cleanup failed (non-critical): {cleanup_error}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'status': 'success',
            'message': 'Enhanced comprehensive migration processing completed'
        })
    }