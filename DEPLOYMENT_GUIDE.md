# 🚀 AWS Deployment Guide for Enhanced Portal

## 🎯 **Quick Fix for "GitHub not updating AWS website"**

### **Problem:** Your enhanced code isn't showing on your live AWS website
### **Solution:** Deploy enhanced components to your existing AWS infrastructure

---

## 📋 **Your AWS Resources (Already Deployed)**

```
✅ Frontend URL: http://subscriber-migration-stack-prod-frontend.s3-website-us-east-1.amazonaws.com/
✅ API Gateway: https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod
✅ Backend Lambda: subscriber-migration-stack-prod-BackendLambda-pw0yiCxXyN3J
✅ DynamoDB Tables: subscriber-table, audit-log-table, migration-jobs-table
✅ S3 Buckets: subscriber-migration-stack-prod-frontend, subscriber-migration-stack-prod-migration-uploads
```

---

## 🚀 **Deploy Enhanced Features (3 Options)**

### **Option 1: Automatic GitHub Actions (Recommended)**

1. **Go to your repository**: https://github.com/Jagadeesh2539/subscriber-migration-portal
2. **Click "Actions" tab**
3. **Click "Deploy Enhanced Subscriber Migration Portal"**
4. **Click "Run workflow"** → **"Run workflow"**
5. **Wait 5-10 minutes** for deployment to complete

### **Option 2: Manual AWS CLI Deployment**

```bash
# 1. Deploy Enhanced Frontend
cd frontend
npm install recharts
npm run build
aws s3 sync build/ s3://subscriber-migration-stack-prod-frontend/ --delete

# 2. Deploy Enhanced Backend
cd ../backend
zip -r enhanced-backend.zip app_enhanced.py requirements.txt *.py
aws lambda update-function-code \
  --function-name subscriber-migration-stack-prod-BackendLambda-pw0yiCxXyN3J \
  --zip-file fileb://enhanced-backend.zip

# 3. Update API Gateway
aws apigateway create-deployment \
  --rest-api-id hsebznxeu6 \
  --stage-name prod \
  --description "Enhanced Portal $(date)"
```

### **Option 3: One-Click Force Deploy**

1. **Push any change to main branch** (like adding a comment)
2. **GitHub Actions will auto-deploy** enhanced features

---

## 🔧 **What Gets Deployed:**

### **Enhanced Frontend Components:**
- ✅ **ProvisioningModule.js** → Multi-mode provisioning (Legacy/Cloud/Dual)
- ✅ **MigrationModule.js** → Job management with cancel, copy, timestamps
- ✅ **BulkOperationsModule.js** → Bulk delete and audit operations
- ✅ **DataQueryModule.js** → Advanced data export and querying
- ✅ **MonitoringDashboard.js** → Real-time system monitoring
- ✅ **AnalyticsModule.js** → Comprehensive analytics and reports
- ✅ **Professional UI** → Modern Material-UI with dark/light theme

### **Enhanced Backend Features:**
- ✅ **30+ API Endpoints** → Complete REST API with all operations
- ✅ **Job Cancel Function** → Stop/pause/resume migration jobs
- ✅ **Timestamp Support** → All jobs include created_timestamp
- ✅ **AWS Integration** → DynamoDB, S3, Secrets Manager
- ✅ **Error Handling** → Comprehensive error management

---

## ⚡ **Quick Test After Deployment:**

1. **Visit:** http://subscriber-migration-stack-prod-frontend.s3-website-us-east-1.amazonaws.com/
2. **Login:** admin/Admin@123 (or operator/Operator@123)
3. **Check Features:**
   - ✅ **Dashboard** with real-time stats
   - ✅ **Provisioning** with Legacy/Cloud/Dual modes
   - ✅ **Migration** with job cancel, copy ID, timestamps
   - ✅ **Bulk Operations** for deletion and audit
   - ✅ **Data Query** for advanced exports
   - ✅ **Monitoring** with system health
   - ✅ **Analytics** with comprehensive reports

---

## 🛠 **Manual Deployment Commands (If GitHub Actions Fails):**

### **Frontend Only:**
```bash
# Install and build
cd frontend
npm install
npm run build

# Deploy to S3
aws s3 sync build/ s3://subscriber-migration-stack-prod-frontend/ \
  --delete \
  --region us-east-1

echo "✅ Frontend deployed - check: http://subscriber-migration-stack-prod-frontend.s3-website-us-east-1.amazonaws.com/"
```

### **Backend Only:**
```bash
# Package backend
cd backend
pip install -r requirements.txt -t .
cp app_enhanced.py lambda_function.py
zip -r lambda-package.zip . -x "*.pyc" "__pycache__/*"

# Deploy to Lambda
aws lambda update-function-code \
  --function-name subscriber-migration-stack-prod-BackendLambda-pw0yiCxXyN3J \
  --zip-file fileb://lambda-package.zip \
  --region us-east-1

# Update API Gateway
DEPLOY_ID=$(aws apigateway create-deployment \
  --rest-api-id hsebznxeu6 \
  --description "Manual Enhanced Deploy" \
  --query 'id' --output text)

aws apigateway update-stage \
  --rest-api-id hsebznxeu6 \
  --stage-name prod \
  --patch-operations op=replace,path=/deploymentId,value=$DEPLOY_ID

echo "✅ Backend deployed - API: https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod"
```

---

## 🔍 **Troubleshooting:**

### **If GitHub Actions Fails:**
1. **Check Secrets**: Repository Settings → Secrets → Actions
   - `AWS_ACCESS_KEY_ID` ✅
   - `AWS_SECRET_ACCESS_KEY` ✅
   - `AWS_ACCOUNT_ID` (add: 144395889420)

2. **Check Permissions**: Your AWS user needs:
   - Lambda: UpdateFunctionCode, UpdateFunctionConfiguration
   - S3: PutObject, DeleteObject, ListBucket
   - API Gateway: CreateDeployment, UpdateStage

### **If Website Still Shows Old Version:**
1. **Clear browser cache** (Ctrl+F5 or Cmd+Shift+R)
2. **Check S3 bucket contents**:
   ```bash
   aws s3 ls s3://subscriber-migration-stack-prod-frontend/
   ```
3. **Verify Lambda function was updated**:
   ```bash
   aws lambda get-function --function-name subscriber-migration-stack-prod-BackendLambda-pw0yiCxXyN3J
   ```

---

## 🎉 **Expected Results After Deployment:**

### **Live Website Will Show:**
- ✅ **Modern Professional UI** with sidebar navigation
- ✅ **Provisioning Section** with Legacy/Cloud/Dual modes
- ✅ **Migration Management** with job cancel, timestamps, copy ID
- ✅ **Bulk Operations** for deletion and audit
- ✅ **Data Query & Export** with advanced filtering
- ✅ **Real-time Monitoring** dashboard
- ✅ **Comprehensive Analytics** with charts
- ✅ **Dark/Light Theme** toggle
- ✅ **Role-based Access** (Admin/Operator/Guest)

### **API Endpoints Will Include:**
- ✅ **30+ Enhanced Endpoints** for all new features
- ✅ **Job Control**: `/api/migration/jobs/{id}/stop` for cancel
- ✅ **Bulk Operations**: `/api/bulk/*` endpoints
- ✅ **Analytics**: `/api/analytics/*` endpoints
- ✅ **Monitoring**: `/api/monitoring/*` endpoints

---

## 🆘 **Need Help?**

If deployment fails:
1. **Check GitHub Actions logs** in repository
2. **Run manual commands** from sections above
3. **Verify AWS permissions** for your access keys
4. **Clear browser cache** after deployment

**Your enhanced portal is ready to go live!** 🚀