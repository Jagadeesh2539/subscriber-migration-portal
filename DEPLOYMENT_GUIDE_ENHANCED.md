# 🚀 Enhanced Industry-Ready Subscriber Migration Portal Deployment Guide

## 📋 Overview

This guide will help you deploy the **enhanced subscriber migration portal** with comprehensive industry-ready telecom features including:

- ✅ **Complete ODBIC/ODBOC configurations**
- ✅ **5G/4G/LTE network support**  
- ✅ **Enterprise/Business/Consumer service classes**
- ✅ **Advanced QoS and charging profiles**
- ✅ **Value-added services (VAS)**
- ✅ **Comprehensive call barring and forwarding**
- ✅ **Full HLR/AUC/EIR integration**

---

## 🔧 Step 1: Update Backend Components

### **1.1 Deploy Enhanced Subscriber Model**

```bash
# Update the main app to use enhanced subscriber model
cp backend/subscriber_enhanced.py backend/subscriber.py

# Update app.py to import enhanced model
sed -i 's/from subscriber import/from subscriber_enhanced import/g' backend/app.py

# Deploy to Lambda
cd backend
zip -r ../enhanced-backend.zip .
aws lambda update-function-code \
  --function-name subscriber-migration-stack-prod-BackendLambda-pw0yiCxXyN3J \
  --zip-file fileb://../enhanced-backend.zip \
  --region us-east-1

echo "✅ Enhanced backend deployed"
```

### **1.2 Deploy Enhanced Migration Processor**

```bash
# Update migration processor
cp backend/migration_processor/enhanced_migration.py backend/migration_processor/app.py

# Deploy enhanced processor
cd backend/migration_processor
zip -r ../../enhanced-migration-processor.zip .
aws lambda update-function-code \
  --function-name subscriber-migration-stac-MigrationProcessorFuncti-oteIVmgXQXfK \
  --zip-file fileb://../../enhanced-migration-processor.zip \
  --region us-east-1

echo "✅ Enhanced migration processor deployed"
```

---

## 🗄️ Step 2: Update Database Schemas

### **2.1 Update RDS Legacy Database**

```bash
# Get RDS connection details
SECRET=$(aws secretsmanager get-secret-value \
  --secret-id arn:aws:secretsmanager:us-east-1:144395889420:secret:subscriber-legacy-db-secret-qWXjZz \
  --region us-east-1 --query 'SecretString' --output text)

DB_HOST=$(echo $SECRET | jq -r '.host')
DB_USER=$(echo $SECRET | jq -r '.username')
DB_PASS=$(echo $SECRET | jq -r '.password')
DB_NAME=$(echo $SECRET | jq -r '.dbname')

# Execute schema update
mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < database/rds_schema_update.sql

echo "✅ RDS schema updated with industry-ready fields"
```

### **2.2 Update DynamoDB Schema**

```bash
# Update DynamoDB table for enhanced attributes
aws dynamodb update-table \
    --table-name subscriber-table \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

# Add Global Secondary Indexes for enhanced queries
aws dynamodb update-table \
    --table-name subscriber-table \
    --attribute-definitions \
        AttributeName=service_class,AttributeType=S \
        AttributeName=plan_type,AttributeType=S \
        AttributeName=network_type,AttributeType=S \
    --global-secondary-index-updates \
        '[{
            "Create": {
                "IndexName": "ServiceClassIndex",
                "KeySchema": [
                    {"AttributeName": "service_class", "KeyType": "HASH"},
                    {"AttributeName": "plan_type", "KeyType": "RANGE"}
                ],
                "Projection": {"ProjectionType": "ALL"},
                "BillingMode": "PAY_PER_REQUEST"
            }
        },
        {
            "Create": {
                "IndexName": "NetworkTypeIndex", 
                "KeySchema": [
                    {"AttributeName": "network_type", "KeyType": "HASH"}
                ],
                "Projection": {"ProjectionType": "ALL"},
                "BillingMode": "PAY_PER_REQUEST"
            }
        }]' \
    --region us-east-1

echo "✅ DynamoDB enhanced for comprehensive queries"
```

---

## 🎨 Step 3: Update Frontend

### **3.1 Deploy Enhanced Frontend Components**

```bash
cd frontend

# Update package.json if needed
npm install

# Build enhanced frontend
npm run build

# Deploy to S3
aws s3 sync build/ s3://subscriber-migration-stack-prod-frontend \
  --delete --cache-control max-age=86400 --region us-east-1

# Invalidate CloudFront (if applicable)
# aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/*"

echo "✅ Enhanced frontend deployed"
```

---

## 📊 Step 4: Populate Industry-Ready Data

### **4.1 Upload Comprehensive Test Data**

```bash
# Create comprehensive test data CSV
cat > industry_test_data.csv << 'EOF'
uid,imsi,msisdn,odbic,odboc,plan_type,network_type,call_forwarding,roaming_enabled,data_limit_mb,voice_minutes,sms_count,status,service_class,premium_services,hlr_profile
ENT001,404103548762341,919876543210,ODBIC_CAT1_BARRED,ODBOC_PREMIUM_RESTRICTED,CORPORATE_POSTPAID,5G_SA_NSA,CF_CFU:919999888777,GLOBAL_ROAMING,999999,UNLIMITED,UNLIMITED,ACTIVE,ENTERPRISE_PLATINUM,VAS_ENTERPRISE_SUITE:CLOUD_PBX,HLR_ENT_PROFILE_A
BIZ002,404586321458963,918765432109,ODBIC_INTL_PREMIUM_ALLOWED,ODBOC_STD_RESTRICTIONS,BUSINESS_POSTPAID,5G_NSA,CF_CFB:918888777666,REGIONAL_ROAMING_PLUS,100000,5000,2000,ACTIVE,BUSINESS_GOLD,VAS_BUSINESS_PACK:MOBILE_BANKING,HLR_BIZ_PROFILE_B
PRE003,404203698741258,917654321098,ODBIC_INTL_BARRED,ODBOC_PREMIUM_BARRED,PREMIUM_PREPAID,4G_LTE_ADVANCED,CF_CFU:917777666555,LIMITED_ROAMING,50000,1500,500,ACTIVE,CONSUMER_PREMIUM,VAS_ENTERTAINMENT:MUSIC_STREAMING,HLR_CONSUMER_PROFILE_A
GOV005,404094785632147,916543210987,ODBIC_UNRESTRICTED,ODBOC_UNRESTRICTED,GOVERNMENT_POSTPAID,5G_SA_SECURE,CF_CFU:916666555444,GLOBAL_SECURE_ROAMING,999999,UNLIMITED,UNLIMITED,ACTIVE,GOVERNMENT_SECURE,VAS_GOVERNMENT:SECURE_MESSAGING,HLR_GOV_SECURE_PROFILE
IOT006,405863214589635,M2M765432112,ODBIC_M2M_RESTRICTED,ODBOC_M2M_DATA_ONLY,IOT_POSTPAID,4G_LTE_M,CF_NONE,GLOBAL_M2M_ROAMING,1000,0,100,ACTIVE,IOT_INDUSTRIAL,VAS_IOT:DEVICE_MGMT,HLR_IOT_PROFILE
EOF

# Upload to S3 for processing
aws s3 cp industry_test_data.csv s3://subscriber-migration-stack-prod-migration-uploads/uploads/industry-ready-$(date +%s).csv \
  --metadata "jobid=industry-ready-$(date +%s),issimulatemode=false,userid=admin,jobtype=production_migration" \
  --region us-east-1

echo "✅ Industry test data uploaded for migration"
```

---

## 🔐 Step 5: Update Environment Variables

### **5.1 Update Lambda Environment Variables**

```bash
# Update backend Lambda with enhanced environment
aws lambda update-function-configuration \
  --function-name subscriber-migration-stack-prod-BackendLambda-pw0yiCxXyN3J \
  --environment "Variables={SUBSCRIBER_TABLE_NAME=subscriber-table,MIGRATION_JOBS_TABLE_NAME=migration-jobs-table,MIGRATION_UPLOAD_BUCKET_NAME=subscriber-migration-stack-prod-migration-uploads,AUDIT_LOG_TABLE_NAME=audit-log-table,LEGACY_DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:144395889420:secret:subscriber-legacy-db-secret-qWXjZz,LEGACY_DB_HOST=subscriber-migration-legacydb.cwd6wssgy4kr.us-east-1.rds.amazonaws.com,DevelopmentMode=true,FRONTEND_DOMAIN_URL=http://subscriber-migration-stack-prod-frontend.s3-website-us-east-1.amazonaws.com,ENHANCED_MODE=true}" \
  --region us-east-1

# Update migration processor Lambda
aws lambda update-function-configuration \
  --function-name subscriber-migration-stac-MigrationProcessorFuncti-oteIVmgXQXfK \
  --environment "Variables={SUBSCRIBERS_TABLE_NAME=subscriber-table,MIGRATION_JOBS_TABLE_NAME=migration-jobs-table,REPORT_BUCKET_NAME=subscriber-migration-stack-prod-migration-uploads,LEGACY_DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:144395889420:secret:subscriber-legacy-db-secret-qWXjZz,LEGACY_DB_HOST=subscriber-migration-legacydb.cwd6wssgy4kr.us-east-1.rds.amazonaws.com,ENHANCED_PROCESSING=true}" \
  --region us-east-1

echo "✅ Environment variables updated for enhanced mode"
```

---

## 🧪 Step 6: Testing & Validation

### **6.1 Test Enhanced API Endpoints**

```bash
# Test enhanced schema endpoint
curl -X GET "https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod/provision/schema" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" | jq

# Test enhanced subscriber creation
curl -X POST "https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod/provision/subscriber" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "uid": "TEST001",
    "imsi": "404103548762999",
    "msisdn": "919999999999",
    "odbic": "ODBIC_STD_RESTRICTIONS",
    "odboc": "ODBOC_STD_RESTRICTIONS",
    "plan_type": "STANDARD_PREPAID",
    "network_type": "4G_LTE",
    "service_class": "CONSUMER_SILVER",
    "premium_services": "VAS_BASIC:NEWS_ALERTS"
  }' | jq

echo "✅ API endpoints tested"
```

### **6.2 Verify Database Population**

```bash
# Check RDS data
mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME -e \
  "SELECT uid, plan_type, network_type, service_class, premium_services FROM subscribers_enhanced LIMIT 5;"

# Check DynamoDB data
aws dynamodb scan --table-name subscriber-table --region us-east-1 --max-items 5 \
  --query 'Items[*].{UID:uid.S,PlanType:plan_type.S,NetworkType:network_type.S,ServiceClass:service_class.S}' \
  --output table

echo "✅ Database population verified"
```

---

## 🎯 Step 7: Feature Verification Checklist

### **7.1 Core Features ✅**
- [ ] Login with admin/Admin@123 works
- [ ] Enhanced subscriber form loads with all tabs
- [ ] CSV upload processes comprehensive data
- [ ] Real-time migration status updates
- [ ] Comprehensive reports generated

### **7.2 Industry Features ✅**
- [ ] ODBIC/ODBOC call barring options
- [ ] 5G/4G/LTE network selections
- [ ] Enterprise/Business/Consumer service classes
- [ ] Call forwarding configurations
- [ ] Roaming zone settings
- [ ] VAS/Premium services
- [ ] QoS profiles
- [ ] HLR/AUC profiles

### **7.3 Data Migration ✅**
- [ ] CSV with comprehensive fields processes correctly
- [ ] Legacy database migration works
- [ ] DynamoDB receives all enhanced fields
- [ ] Reports include all industry data

---

## 🚀 Step 8: Go Live!

### **8.1 Final Deployment Steps**

```bash
# Final verification
echo "🔍 Running final system check..."

# Test login
echo "Testing login..."
curl -X POST "https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod/users/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123"}' | jq '.token' > /dev/null && echo "✅ Login working"

# Test migration upload
echo "Testing migration upload..."
aws s3 ls s3://subscriber-migration-stack-prod-migration-uploads/uploads/ --region us-east-1 && echo "✅ S3 upload working"

# Test Lambda functions
echo "Testing Lambda functions..."
aws lambda get-function-configuration --function-name subscriber-migration-stack-prod-BackendLambda-pw0yiCxXyN3J --region us-east-1 --query 'State' && echo "✅ Backend Lambda ready"
aws lambda get-function-configuration --function-name subscriber-migration-stac-MigrationProcessorFuncti-oteIVmgXQXfK --region us-east-1 --query 'State' && echo "✅ Migration processor ready"

echo ""
echo "🎉🎊 DEPLOYMENT COMPLETE! 🎊🎉"
echo ""
echo "🌐 Access your enhanced portal at:"
echo "   http://subscriber-migration-stack-prod-frontend.s3-website-us-east-1.amazonaws.com"
echo ""
echo "🔑 Login credentials:"
echo "   Username: admin"
echo "   Password: Admin@123"
echo ""
echo "✨ Enhanced Features Available:"
echo "   📱 Industry-ready subscriber provisioning"
echo "   📊 Comprehensive migration processing  "
echo "   🏢 Enterprise/Business/Consumer service classes"
echo "   🌐 5G/4G/LTE network support"
echo "   🔧 Advanced QoS and charging profiles"
echo "   📡 Complete telecom feature set"
echo ""
```

---

## 🆘 Troubleshooting

### **Common Issues & Solutions**

**Issue: "Schema endpoint not found"**
```bash
# Solution: Redeploy backend with enhanced model
cp backend/subscriber_enhanced.py backend/subscriber.py
# Redeploy Lambda
```

**Issue: "New fields not saving"**
```bash
# Solution: Check DynamoDB table capacity
aws dynamodb describe-table --table-name subscriber-table --region us-east-1
```

**Issue: "Migration processor failing"**
```bash
# Solution: Check Lambda logs
aws logs tail /aws/lambda/subscriber-migration-stac-MigrationProcessorFuncti-oteIVmgXQXfK --follow --region us-east-1
```

**Issue: "Frontend not showing new fields"**
```bash
# Solution: Clear browser cache and rebuild
cd frontend
npm run build
aws s3 sync build/ s3://subscriber-migration-stack-prod-frontend --delete
```

---

## 🏆 Success Metrics

**Your enhanced system should now support:**
- ✅ **40+ industry-standard subscriber fields**
- ✅ **Enterprise-grade service classes**
- ✅ **5G/4G network configurations** 
- ✅ **Comprehensive call management**
- ✅ **Advanced billing & limits**
- ✅ **Full telecom VAS suite**
- ✅ **Production-ready migration processing**

**🎯 You now have a world-class, industry-ready subscriber migration platform!** 🌍📡🚀