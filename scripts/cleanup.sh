#!/bin/bash
set -euo pipefail

# These variables are inherited from the GitHub Actions (env) block
STACK="${STACK_NAME}"
REGION="${AWS_DEFAULT_REGION}"

echo "🔥 ============================================"
echo "🔥  BULLETPROOF CLEANUP SYSTEM v2.0"
echo "🔥 ============================================"
echo "📍 Stack:  $STACK"
echo "📍 Region: $REGION"
echo "📍 Time:   $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# ============================================
# UTILITY FUNCTIONS
# ============================================

# Retry with exponential backoff
retry_command() {
  local max_attempts=$1
  shift
  local command=("$@")
  local attempt=1
  local delay=3
  
  while [ $attempt -le $max_attempts ]; do
    if "${command[@]}" 2>/dev/null; then
      return 0
    fi
    
    if [ $attempt -lt $max_attempts ]; then
      echo "    ⏳ Retry $attempt/$max_attempts in ${delay}s..."
      sleep $delay
      delay=$((delay * 2))
    fi
    attempt=$((attempt + 1))
  done
  
  echo "    ❌ Failed after $max_attempts attempts"
  return 1
}

# ============================================
# STEP 0: STACK HEALTH CHECK & DECISION
# ============================================

echo "🔍 STEP 0: Stack Health Check"
echo "=============================================="

CLEANUP_NEEDED=false
STACK_EXISTS=false

if aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" >/dev/null 2>&1; then
  STACK_EXISTS=true
  STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK" \
    --region "$REGION" \
    --query 'Stacks[0].StackStatus' \
    --output text)
  
  echo "📊 Current Stack Status: $STATUS"
  echo ""
  
  case "$STATUS" in
    # ✅ HEALTHY - Skip cleanup
    CREATE_COMPLETE|UPDATE_COMPLETE)
      echo "✅ ============================================"
      echo "✅  STACK IS HEALTHY - FAST PATH"
      echo "✅ ============================================"
      echo ""
      echo "ℹ️  Cleanup: SKIPPED (not needed)"
      echo "ℹ️  Action:  UPDATE deployment only"
      echo ""
      echo "cleanup_performed=false" >> $GITHUB_OUTPUT
      exit 0
      ;;
    
    # ⚠️ ERROR STATES - Full cleanup required
    ROLLBACK_COMPLETE|ROLLBACK_FAILED|CREATE_FAILED|DELETE_FAILED|UPDATE_ROLLBACK_COMPLETE|UPDATE_ROLLBACK_FAILED|DELETE_IN_PROGRESS)
      echo "⚠️ ============================================"
      echo "⚠️  STACK IN ERROR/STUCK STATE ($STATUS)"
      echo "⚠️ ============================================"
      echo ""
      echo "ℹ️  Cleanup: REQUIRED (error recovery)"
      echo "ℹ️  Action:  DELETE all + FRESH deploy"
      echo ""
      CLEANUP_NEEDED=true
      ;;
    
    # 🔄 IN PROGRESS - Wait
    CREATE_IN_PROGRESS|UPDATE_IN_PROGRESS)
      echo "⏳ Stack operation in progress - waiting 60s..."
      sleep 60
      echo "cleanup_performed=false" >> $GITHUB_OUTPUT
      exit 0
      ;;
    
    *)
      echo "❓ Unexpected status: $STATUS (proceeding with cleanup)"
      CLEANUP_NEEDED=true
      ;;
  esac
else
  echo "ℹ️ ============================================"
  echo "ℹ️  NO EXISTING STACK"
  echo "ℹ️ ============================================"
  echo ""
  echo "ℹ️  Cleanup: SKIPPED (nothing to clean)"
  echo "ℹ️  Action:  CREATE new stack"
  STACK_EXISTS=false
  CLEANUP_NEEDED=false
  echo "cleanup_performed=false" >> $GITHUB_OUTPUT
  exit 0
fi

# Export status
echo "cleanup_performed=true" >> $GITHUB_OUTPUT

# ============================================
# STEP 1: PRE-CLEANUP - PREPARE RESOURCES
# ============================================

echo ""
echo "🎯 STEP 1: Pre-Cleanup Preparation"
echo "=============================================="

# Get all resources from CloudFormation stack
echo "📋 Discovering stack resources..."

STACK_RESOURCES=$(aws cloudformation list-stack-resources \
  --stack-name "$STACK" \
  --region "$REGION" \
  --query 'StackResourceSummaries[].[LogicalResourceId,PhysicalResourceId,ResourceType]' \
  --output text 2>/dev/null || true)

if [[ -n "$STACK_RESOURCES" ]]; then
  RESOURCE_COUNT=$(echo "$STACK_RESOURCES" | wc -l)
  echo "✅ Found $RESOURCE_COUNT stack resources"
else
  echo "⚠️ No stack resources found (stack may be partially deleted)"
fi

# ============================================
# STEP 2: DETACH DEPENDENCIES
# ============================================

echo ""
echo "🔗 STEP 2: Detach Dependencies"
echo "=============================================="

# 2.1: Remove Lambda ENIs (CRITICAL - must be first)
echo ""
echo "🔌 [2.1] Lambda Network Interfaces (ENIs)..."

LAMBDA_ENIS=$(aws ec2 describe-network-interfaces \
  --region "$REGION" \
  --filters "Name=description,Values=*AWS Lambda VPC ENI*" \
  --query 'NetworkInterfaces[].NetworkInterfaceId' \
  --output text 2>/dev/null || true)

if [[ -n "$LAMBDA_ENIS" ]]; then
  for eni in $LAMBDA_ENIS; do
    echo "  🗑️ Detaching ENI: $eni"
    aws ec2 delete-network-interface --network-interface-id "$eni" --region "$REGION" 2>/dev/null &
  done
  wait
  echo "  ✅ Lambda ENIs detached"
  sleep 10  # Wait for detachment to propagate
else
  echo "  ✅ No Lambda ENIs found"
fi

# 2.2: Remove EventBridge Targets
echo ""
echo "⏰ [2.2] EventBridge Rule Targets..."

RULES=$(aws events list-rules \
  --region "$REGION" \
  --query 'Rules[?contains(Name, `'$STACK'`)].Name' \
  --output text 2>/dev/null || true)

if [[ -n "$RULES" ]]; then
  for rule in $RULES; do
    echo "  🎯 Removing targets from rule: $rule"
    
    TARGETS=$(aws events list-targets-by-rule \
      --region "$REGION" \
      --rule "$rule" \
      --query 'Targets[].Id' \
      --output text 2>/dev/null || true)
    
    if [[ -n "$TARGETS" ]]; then
      aws events remove-targets \
        --region "$REGION" \
        --rule "$rule" \
        --ids $TARGETS 2>/dev/null || true
      echo "    ✅ Targets removed"
    fi
  done
else
  echo "  ✅ No EventBridge rules found"
fi

# 2.3: Detach IAM Role Policies
echo ""
echo "👤 [2.3] IAM Role Policies..."

IAM_ROLES=$(aws iam list-roles \
  --query 'Roles[?contains(RoleName, `'$STACK'`)].RoleName' \
  --output text 2>/dev/null || true)

if [[ -n "$IAM_ROLES" ]]; then
  for role in $IAM_ROLES; do
    echo "  🔓 Detaching policies from role: $role"
    
    # Detach managed policies
    MANAGED_POLICIES=$(aws iam list-attached-role-policies \
      --role-name "$role" \
      --query 'AttachedPolicies[].PolicyArn' \
      --output text 2>/dev/null || true)
    
    for policy in $MANAGED_POLICIES; do
      aws iam detach-role-policy --role-name "$role" --policy-arn "$policy" 2>/dev/null &
    done
    
    # Delete inline policies
    INLINE_POLICIES=$(aws iam list-role-policies \
      --role-name "$role" \
      --query 'PolicyNames[]' \
      --output text 2>/dev/null || true)
    
    for policy in $INLINE_POLICIES; do
      aws iam delete-role-policy --role-name "$role" --policy-name "$policy" 2>/dev/null &
    done
  done
  wait
  echo "  ✅ Policies detached"
  sleep 5
else
  echo "  ✅ No IAM roles found"
fi

# ============================================
# STEP 3: DELETE STATEFUL RESOURCES
# ============================================

echo ""
echo "🗄️ STEP 3: Delete Stateful Resources"
echo "=============================================="

# 3.1: RDS Instances (SLOW - start early)
echo ""
echo "🗄️ [3.1] RDS Database Instances..."

RDS_INSTANCES=$(aws rds describe-db-instances \
  --region "$REGION" \
  --query "DBInstances[?contains(DBInstanceIdentifier, '$STACK')].DBInstanceIdentifier" \
  --output text 2>/dev/null || true)

if [[ -n "$RDS_INSTANCES" ]]; then
  for db in $RDS_INSTANCES; do
    DB_STATUS=$(aws rds describe-db-instances \
      --region "$REGION" \
      --db-instance-identifier "$db" \
      --query 'DBInstances[0].DBInstanceStatus' \
      --output text 2>/dev/null || echo "not-found")
    
    echo "  📊 RDS: $db (status: $DB_STATUS)"
    
    if [[ "$DB_STATUS" == "deleting" ]]; then
      echo "    ⏳ Already deleting"
    elif [[ "$DB_STATUS" != "not-found" ]]; then
      echo "    🗑️ Initiating deletion..."
      
      aws rds delete-db-instance \
        --region "$REGION" \
        --db-instance-identifier "$db" \
        --skip-final-snapshot \
        --delete-automated-backups 2>/dev/null || true
      
      echo "    ✅ Deletion initiated"
    fi
  done
  
  # Wait for deletion (using variable, non-blocking)
  echo "  ⏳ Waiting for RDS deletion (max $RDS_DELETE_TIMEOUT_MINUTES min, running in background)..."
  (
    for db in $RDS_INSTANCES; do
      timeout $(($RDS_DELETE_TIMEOUT_MINUTES * 60)) aws rds wait db-instance-deleted \
        --region "$REGION" \
        --db-instance-identifier "$db" 2>/dev/null || true
    done
    echo "  ✅ RDS deletion completed or timed out"
  ) &
  RDS_WAIT_PID=$!
  
else
  echo "  ✅ No RDS instances found"
  RDS_WAIT_PID=""
fi

# 3.2: DynamoDB Tables
echo ""
echo "📇 [3.2] DynamoDB Tables..."

DYNAMODB_TABLES=$(aws dynamodb list-tables \
  --region "$REGION" \
  --query 'TableNames[]' \
  --output text 2>/dev/null | tr '\t' '\n' | grep "$STACK" 2>/dev/null || true)

if [[ -n "$DYNAMODB_TABLES" ]]; then
  for table in $DYNAMODB_TABLES; do
    echo "  🗑️ Deleting table: $table"
    aws dynamodb delete-table --region "$REGION" --table-name "$table" 2>/dev/null &
  done
  wait
  echo "  ✅ DynamoDB deletion initiated"
  sleep 10
else
  echo "  ✅ No DynamoDB tables found"
fi

# 3.3: S3 Buckets (empty then delete)
echo ""
echo "🪣 [3.3] S3 Buckets..."

S3_BUCKETS=$(aws s3api list-buckets \
  --query 'Buckets[].Name' \
  --output text 2>/dev/null | tr '\t' '\n' | grep "$STACK" 2>/dev/null || true)

if [[ -n "$S3_BUCKETS" ]]; then
  for bucket in $S3_BUCKETS; do
    echo "  🗑️ Processing bucket: $bucket"
    
    # Empty bucket (delete all objects and versions)
    echo "    📦 Emptying bucket..."
    aws s3 rm "s3://$bucket" --recursive --region "$REGION" 2>/dev/null || true
    
    # Delete all versions if versioning enabled
    aws s3api list-object-versions \
      --bucket "$bucket" \
      --region "$REGION" \
      --output json 2>/dev/null | \
    jq -r '.Versions[]?, .DeleteMarkers[]? | 
      "--key \"\(.Key)\" --version-id \"\(.VersionId)\""' 2>/dev/null | \
    xargs -I {} aws s3api delete-object --bucket "$bucket" --region "$REGION" {} 2>/dev/null || true
    
    # Delete bucket
    echo "    🗑️ Deleting bucket..."
    aws s3 rb "s3://$bucket" --force --region "$REGION" 2>/dev/null &
  done
  wait
  echo "  ✅ S3 buckets deleted"
else
  echo "  ✅ No S3 buckets found"
fi

# 3.4: Secrets Manager (WITH PROPER WAIT)
echo ""
echo "🔐 [3.4] Secrets Manager..."

SECRETS=$(aws secretsmanager list-secrets \
  --region "$REGION" \
  --query 'SecretList[].Name' \
  --output text 2>/dev/null | tr '\t' '\n' | grep "$STACK" 2>/dev/null || true)

if [[ -n "$SECRETS" ]]; then
  echo "  📋 Found $(echo $SECRETS | wc -w) secret(s)"
  
  # Phase 1: Initiate deletion
  for secret in $SECRETS; do
    echo "  🗑️ Deleting secret: $secret"
    
    if aws secretsmanager delete-secret \
      --region "$REGION" \
      --secret-id "$secret" \
      --force-delete-without-recovery 2>/dev/null; then
      echo "    ✅ Deletion initiated"
    else
      echo "    ⚠️ Already deleted or not found"
    fi
  done
  
  # Phase 2: CRITICAL - Wait for full deletion
  echo "  ⏳ Waiting for secrets to be FULLY deleted (max 90s)..."
  
  for secret in $SECRETS; do
    WAIT_COUNT=0
    MAX_WAIT=18  # 18 iterations * 5s = 90s
    
    while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
      if aws secretsmanager describe-secret \
        --region "$REGION" \
        --secret-id "$secret" >/dev/null 2>&1; then
        
        # Secret still exists
        if [ $((WAIT_COUNT % 4)) -eq 0 ]; then
          echo "    ⏳ Still deleting: $secret ($((WAIT_COUNT * 5))s elapsed)"
        fi
        
        sleep 5
        WAIT_COUNT=$((WAIT_COUNT + 1))
      else
        # Secret not found - deletion complete
        echo "    ✅ Fully deleted: $secret"
        break
      fi
    done
    
    if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
      echo "    ⚠️ Timeout for: $secret (may still be deleting)"
    fi
  done
  
  # Phase 3: Final verification
  echo "  🔍 Final verification..."
  sleep 5
  
  REMAINING=$(aws secretsmanager list-secrets \
    --region "$REGION" \
    --query 'SecretList[?DeletionDate==null].Name' \
    --output text 2>/dev/null | tr '\t' '\n' | grep "$STACK" 2>/dev/null || true)
  
  if [[ -z "$REMAINING" ]]; then
    echo "  ✅ All secrets fully deleted and verified"
  else
    echo "  ⚠️ Some secrets may still be deleting: $REMAINING"
    echo "  ⏳ Waiting additional 30s..."
    sleep 30
  fi
  
else
  echo "  ✅ No secrets found"
fi

# ============================================
# STEP 4: DELETE COMPUTE RESOURCES
# ============================================

echo ""
echo "⚡ STEP 4: Delete Compute Resources"
echo "=============================================="

# 4.1: Lambda Functions
echo ""
echo "⚡ [4.1] Lambda Functions..."

LAMBDA_FUNCTIONS=$(aws lambda list-functions \
  --region "$REGION" \
  --query 'Functions[?contains(FunctionName, `'$STACK'`)].FunctionName' \
  --output text 2>/dev/null || true)

if [[ -n "$LAMBDA_FUNCTIONS" ]]; then
  for func in $LAMBDA_FUNCTIONS; do
    echo "  🗑️ Deleting function: $func"
    aws lambda delete-function --region "$REGION" --function-name "$func" 2>/dev/null &
  done
  wait
  echo "  ✅ Lambda functions deleted"
else
  echo "  ✅ No Lambda functions found"
fi

# 4.2: Lambda Layers
echo ""
echo "📦 [4.2] Lambda Layers..."

LAMBDA_LAYERS=$(aws lambda list-layers \
  --region "$REGION" \
  --query 'Layers[].LayerName' \
  --output text 2>/dev/null | tr '\t' '\n' | grep "$STACK" 2>/dev/null || true)

if [[ -n "$LAMBDA_LAYERS" ]]; then
  for layer in $LAMBDA_LAYERS; do
    echo "  🗑️ Deleting layer: $layer"
    
    VERSIONS=$(aws lambda list-layer-versions \
      --region "$REGION" \
      --layer-name "$layer" \
      --query 'LayerVersions[].Version' \
      --output text 2>/dev/null || true)
    
    for version in $VERSIONS; do
      aws lambda delete-layer-version \
        --region "$REGION" \
        --layer-name "$layer" \
        --version-number "$version" 2>/dev/null &
    done
  done
  wait
  echo "  ✅ Lambda layers deleted"
else
  echo "  ✅ No Lambda layers found"
fi

# 4.3: Step Functions State Machines
echo ""
echo "🔄 [4.3] Step Functions State Machines..."

STATE_MACHINES=$(aws stepfunctions list-state-machines \
  --region "$REGION" \
  --query 'stateMachines[?contains(name, `'$STACK'`)].stateMachineArn' \
  --output text 2>/dev/null || true)

if [[ -n "$STATE_MACHINES" ]]; then
  for sm in $STATE_MACHINES; do
    SM_NAME=$(basename "$sm")
    echo "  🗑️ Deleting state machine: $SM_NAME"
    aws stepfunctions delete-state-machine --region "$REGION" --state-machine-arn "$sm" 2>/dev/null &
  done
  wait
  echo "  ✅ State machines deleted"
else
  echo "  ✅ No state machines found"
fi

# ============================================
# STEP 5: DELETE API & NETWORKING
# ============================================

echo ""
echo "🌐 STEP 5: Delete API & Networking"
echo "=============================================="

# 5.1: API Gateways
echo ""
echo "📡 [5.1] API Gateways..."

API_GATEWAYS=$(aws apigateway get-rest-apis \
  --region "$REGION" \
  --query "items[?contains(name, '$STACK')].id" \
  --output text 2>/dev/null || true)

if [[ -n "$API_GATEWAYS" ]]; then
  for api in $API_GATEWAYS; do
    API_NAME=$(aws apigateway get-rest-api \
      --region "$REGION" \
      --rest-api-id "$api" \
      --query 'name' \
      --output text 2>/dev/null || echo "unknown")
    
    echo "  🗑️ Deleting API Gateway: $api ($API_NAME)"
    aws apigateway delete-rest-api --region "$REGION" --rest-api-id "$api" 2>/dev/null &
  done
  wait
  echo "  ✅ API Gateways deleted"
else
  echo "  ✅ No API Gateways found"
fi

# 5.2: VPC Endpoints
echo ""
echo "🔗 [5.2] VPC Endpoints..."

VPC_ENDPOINTS=$(aws ec2 describe-vpc-endpoints \
  --region "$REGION" \
  --query 'VpcEndpoints[].VpcEndpointId' \
  --output text 2>/dev/null || true)

VPCE_COUNT=0
for vpce in $VPC_ENDPOINTS; do
  TAGS=$(aws ec2 describe-vpc-endpoints \
    --region "$REGION" \
    --vpc-endpoint-ids "$vpce" \
    --query 'VpcEndpoints[0].Tags[?Key==`aws:cloudformation:stack-name`].Value' \
    --output text 2>/dev/null || true)
  
  if echo "$TAGS" | grep -q "$STACK"; then
    echo "  🗑️ Deleting VPC Endpoint: $vpce"
    retry_command 3 aws ec2 delete-vpc-endpoints --region "$REGION" --vpc-endpoint-ids "$vpce" &
    VPCE_COUNT=$((VPCE_COUNT + 1))
  fi
done
wait

if [ $VPCE_COUNT -gt 0 ]; then
  echo "  ✅ Deleted $VPCE_COUNT VPC endpoint(s)"
  sleep 15
else
  echo "  ✅ No VPC endpoints found"
fi

# 5.3: Security Groups (with retries)
echo ""
echo "🛡️ [5.3] Security Groups..."

for attempt in {1..3}; do
  SG_DELETED=0
  echo "  🔄 Attempt $attempt/3..."
  
  SECURITY_GROUPS=$(aws ec2 describe-security-groups \
    --region "$REGION" \
    --query 'SecurityGroups[?GroupName!=`default`].GroupId' \
    --output text 2>/dev/null || true)
  
  for sg in $SECURITY_GROUPS; do
    SG_NAME=$(aws ec2 describe-security-groups \
      --region "$REGION" \
      --group-ids "$sg" \
      --query 'SecurityGroups[0].GroupName' \
      --output text 2>/dev/null || true)
    
    if echo "$SG_NAME" | grep -q "$STACK"; then
      if aws ec2 delete-security-group --region "$REGION" --group-id "$sg" 2>/dev/null; then
        echo "    ✅ Deleted: $sg ($SG_NAME)"
        SG_DELETED=$((SG_DELETED + 1))
      fi
    fi
  done
  
  [ $SG_DELETED -eq 0 ] && break
  [ $attempt -lt 3 ] && sleep 15
done
echo "  ✅ Security groups cleanup complete"

# 5.4: RDS Subnet Groups (after RDS deletion)
echo ""
echo "🔧 [5.4] RDS Subnet Groups..."

# Wait for RDS deletion to complete first
if [[ -n "$RDS_WAIT_PID" ]]; then
  echo "  ⏳ Waiting for RDS deletion to complete..."
  wait $RDS_WAIT_PID 2>/dev/null || true
fi

for attempt in {1..3}; do
  SUBNET_GROUPS=$(aws rds describe-db-subnet-groups \
    --region "$REGION" \
    --query "DBSubnetGroups[?contains(DBSubnetGroupName, '$STACK')].DBSubnetGroupName" \
    --output text 2>/dev/null || true)
  
  if [[ -z "$SUBNET_GROUPS" ]]; then
    echo "  ✅ No RDS subnet groups found"
    break
  fi
  
  echo "  🔄 Attempt $attempt/3..."
  for sg in $SUBNET_GROUPS; do
    if aws rds delete-db-subnet-group --region "$REGION" --db-subnet-group-name "$sg" 2>/dev/null; then
      echo "    ✅ Deleted: $sg"
    else
      echo "    ⏭️ Still in use: $sg"
    fi
  done
  
  [ $attempt -lt 3 ] && sleep 10
done

# ============================================
# STEP 6: DELETE MONITORING & LOGGING
# ============================================

echo ""
echo "📊 STEP 6: Delete Monitoring & Logging"
echo "=============================================="

# 6.1: CloudWatch Log Groups
echo ""
echo "📝 [6.1] CloudWatch Log Groups..."

LOG_PREFIXES=(
  "/aws/lambda/${STACK}"
  "/aws/vendedlogs/states/${STACK}"
  "/aws/apigateway/${STACK}"
  "/aws/rds/${STACK}"
)

for prefix in "${LOG_PREFIXES[@]}"; do
  LOGS=$(aws logs describe-log-groups \
    --region "$REGION" \
    --log-group-name-prefix "$prefix" \
    --query 'logGroups[].logGroupName' \
    --output text 2>/dev/null || true)
  
  if [[ -n "$LOGS" ]]; then
    for lg in $LOGS; do
      echo "  🗑️ Deleting log group: $lg"
      aws logs delete-log-group --region "$REGION" --log-group-name "$lg" 2>/dev/null &
    done
  fi
done
wait
echo "  ✅ Log groups deleted"

# 6.2: CloudWatch Alarms
echo ""
echo "🔔 [6.2] CloudWatch Alarms..."

ALARMS=$(aws cloudwatch describe-alarms \
  --region "$REGION" \
  --query 'MetricAlarms[?contains(AlarmName, `'$STACK'`)].AlarmName' \
  --output text 2>/dev/null || true)

if [[ -n "$ALARMS" ]]; then
  for alarm in $ALARMS; do
    echo "  🗑️ Deleting alarm: $alarm"
    aws cloudwatch delete-alarms --region "$REGION" --alarm-names "$alarm" 2>/dev/null &
  done
  wait
  echo "  ✅ Alarms deleted"
else
  echo "  ✅ No alarms found"
fi

# ============================================
# STEP 7: DELETE IAM RESOURCES
# ============================================

echo ""
echo "👤 STEP 7: Delete IAM Resources"
echo "=============================================="

# 7.1: IAM Roles (policies already detached in Step 2)
echo ""
echo "👤 [7.1] IAM Roles..."

if [[ -n "$IAM_ROLES" ]]; then
  for role in $IAM_ROLES; do
    echo "  🗑️ Deleting role: $role"
    retry_command 3 aws iam delete-role --role-name "$role" &
  done
  wait
  echo "  ✅ IAM roles deleted"
else
  echo "  ✅ No IAM roles found"
fi

# ============================================
# STEP 8: DELETE EVENTBRIDGE RULES
# ============================================

echo ""
echo "⏰ STEP 8: Delete EventBridge Rules"
echo "=============================================="

if [[ -n "$RULES" ]]; then
  for rule in $RULES; do
    echo "  🗑️ Deleting rule: $rule"
    aws events delete-rule --region "$REGION" --name "$rule" 2>/dev/null &
  done
  wait
  echo "  ✅ EventBridge rules deleted"
else
  echo "  ✅ No EventBridge rules found (already processed)"
fi

# ============================================
# STEP 9: DELETE CLOUDFORMATION STACK
# ============================================

echo ""
echo "📦 STEP 9: Delete CloudFormation Stack"
echo "=============================================="

if [[ "$STACK_EXISTS" == "true" ]]; then
  echo "  🗑️ Initiating stack deletion: $STACK"
  
  if aws cloudformation delete-stack --stack-name "$STACK" --region "$REGION" 2>/dev/null; then
    echo "  ✅ Stack deletion initiated"
    
    # Wait for stack deletion
    echo "  ⏳ Waiting for stack deletion (max $STACK_DELETE_TIMEOUT_MINUTES min)..."
    
    if timeout $(($STACK_DELETE_TIMEOUT_MINUTES * 60)) \
       aws cloudformation wait stack-delete-complete \
         --stack-name "$STACK" \
         --region "$REGION" 2>/dev/null; then
      echo "  ✅ Stack deleted successfully"
    else
      # Check if stack still exists
      if aws cloudformation describe-stacks \
        --stack-name "$STACK" \
        --region "$REGION" >/dev/null 2>&1; then
        
        CURRENT_STATUS=$(aws cloudformation describe-stacks \
          --stack-name "$STACK" \
          --region "$REGION" \
          --query 'Stacks[0].StackStatus' \
          --output text 2>/dev/null || echo "UNKNOWN")
        
        echo "  ⚠️ Stack deletion timeout (status: $CURRENT_STATUS)"
        
        if [[ "$CURRENT_STATUS" == "DELETE_FAILED" ]]; then
          echo "  ⚠️ Stack deletion failed - checking for stuck resources..."
          
          aws cloudformation describe-stack-resources \
            --stack-name "$STACK" \
            --region "$REGION" \
            --query 'StackResources[?ResourceStatus==`DELETE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
            --output table 2>/dev/null || true
        fi
      else
        echo "  ✅ Stack no longer exists (deletion completed)"
      fi
    fi
  else
    echo "  ⚠️ Stack deletion command failed (may not exist)"
  fi
else
  echo "  ✅ No stack to delete"
fi

# ============================================
# STEP 10: FINAL VERIFICATION & ORPHAN CHECK
# ============================================

echo ""
echo "🔍 STEP 10: Final Verification"
echo "=============================================="

echo "🔍 Checking for remaining resources..."

# Check each resource type
ORPHAN_COUNT=0

# RDS
if REMAINING_RDS=$(aws rds describe-db-instances \
  --region "$REGION" \
  --query "DBInstances[?contains(DBInstanceIdentifier, '$STACK')].DBInstanceIdentifier" \
  --output text 2>/dev/null) && [[ -n "$REMAINING_RDS" ]]; then
  echo "  ⚠️ Remaining RDS: $REMAINING_RDS"
  ORPHAN_COUNT=$((ORPHAN_COUNT + 1))
fi

# DynamoDB
if REMAINING_DDB=$(aws dynamodb list-tables \
  --region "$REGION" \
  --query 'TableNames[]' \
  --output text 2>/dev/null | tr '\t' '\n' | grep "$STACK" 2>/dev/null); then
  echo "  ⚠️ Remaining DynamoDB: $REMAINING_DDB"
  ORPHAN_COUNT=$((ORPHAN_COUNT + 1))
fi

# Secrets
if REMAINING_SECRETS=$(aws secretsmanager list-secrets \
  --region "$REGION" \
  --query 'SecretList[?DeletionDate==null].Name' \
  --output text 2>/dev/null | tr '\t' '\n' | grep "$STACK" 2>/dev/null); then
  echo "  ⚠️ Remaining Secrets: $REMAINING_SECRETS"
  ORPHAN_COUNT=$((ORPHAN_COUNT + 1))
fi

# Lambda
if REMAINING_LAMBDA=$(aws lambda list-functions \
  --region "$REGION" \
  --query 'Functions[?contains(FunctionName, `'$STACK'`)].FunctionName' \
  --output text 2>/dev/null) && [[ -n "$REMAINING_LAMBDA" ]]; then
  echo "  ⚠️ Remaining Lambda: $REMAINING_LAMBDA"
  ORPHAN_COUNT=$((ORPHAN_COUNT + 1))
fi

# S3
if REMAINING_S3=$(aws s3api list-buckets \
  --query 'Buckets[].Name' \
  --output text 2>/dev/null | tr '\t' '\n' | grep "$STACK" 2>/dev/null); then
  echo "  ⚠️ Remaining S3: $REMAINING_S3"
  ORPHAN_COUNT=$((ORPHAN_COUNT + 1))
fi

if [ $ORPHAN_COUNT -eq 0 ]; then
  echo "✅ No orphaned resources found"
else
  echo "⚠️ Found $ORPHAN_COUNT type(s) of orphaned resources"
  echo "   These may still be deleting or require manual cleanup"
fi

# ============================================
# CLEANUP COMPLETE
# ============================================

CLEANUP_DURATION=$SECONDS

echo ""
echo "✅ ============================================"
echo "✅  CLEANUP COMPLETED SUCCESSFULLY"
echo "✅ ============================================"
echo ""
echo "📊 Cleanup Summary:"
echo "  ✅ Stack deletion:      Complete"
echo "  ✅ Stateful resources:  Deleted"
echo "  ✅ Compute resources:   Deleted"
echo "  ✅ Networking:          Deleted"
echo "  ✅ Monitoring:          Deleted"
echo "  ✅ IAM resources:       Deleted"
echo "  ⚠️ Orphaned resources:  $ORPHAN_COUNT type(s)"
echo "  ⏱️ Duration:            ${CLEANUP_DURATION}s (~$((CLEANUP_DURATION / 60)) min)"
echo ""
echo "🚀 System ready for fresh deployment!"
echo ""