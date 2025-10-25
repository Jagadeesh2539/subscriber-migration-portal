# 🚀 Enhanced Subscriber Migration Portal

[![Deploy Enhanced Portal](https://github.com/Jagadeesh2539/subscriber-migration-portal/actions/workflows/main-deploy.yml/badge.svg)](https://github.com/Jagadeesh2539/subscriber-migration-portal/actions/workflows/main-deploy.yml)
[![AWS Status](https://img.shields.io/badge/AWS-Live-success)](http://subscriber-migration-stack-prod-frontend.s3-website-us-east-1.amazonaws.com/)
[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/Jagadeesh2539/subscriber-migration-portal/releases)

> **Enterprise-grade subscriber migration portal with dual database support, professional UI, and complete legacy integration.**

## 🌐 **Live Portal Access**

**🎆 Portal URL**: http://subscriber-migration-stack-prod-frontend.s3-website-us-east-1.amazonaws.com/

**🔐 Login Credentials**:
- **Admin**: `admin` / `Admin@123` (Full system access)
- **Operator**: `operator` / `Operator@123` (Operations access)  
- **Guest**: `guest` / `Guest@123` (Read-only access)

## 🌟 Features

### 🎯 **Dual Database Architecture**
- **☁️ Cloud Mode**: DynamoDB for modern, scalable operations
- **🏛️ Legacy Mode**: MySQL RDS for existing data compatibility  
- **🔄 Dual Provisioning**: Atomic operations across both systems
- **📊 Smart Dashboard**: Real-time statistics from both systems

### 🔧 **Enhanced Features** 
- **📅 Job Management**: Migration jobs with timestamps, cancel/pause functionality
- **📋 Copy Job ID**: One-click copying for tracking
- **📊 Analytics**: Professional charts and comprehensive reporting
- **🔍 Bulk Operations**: Mass deletion, audit comparison, data export
- **🎨 Material-UI**: Professional responsive interface

### 🚀 **CI/CD Pipeline**
- **Auto-deploy**: Every push to main triggers deployment
- **Manual Control**: Run workflow button for on-demand deployments
- **Component Deploy**: Frontend-only or backend-only options
- **Comprehensive Testing**: API health, auth, frontend, legacy DB checks

## 🚀 Quick Deployment

### **1. One-Click Deploy**

[![Deploy Now](https://img.shields.io/badge/Deploy-Now-success?style=for-the-badge&logo=github)](https://github.com/Jagadeesh2539/subscriber-migration-portal/actions/workflows/main-deploy.yml)

1. Click the deploy badge above
2. Click "Run workflow" → "Run workflow"
3. Wait 10-15 minutes
4. Your enhanced portal is live!

### **2. Auto-Deploy on Push**
```bash
# Any push to main triggers automatic deployment
git push origin main
```

## 📋 System Requirements

### **☁️ AWS Resources** (Already Configured)
- **Frontend**: S3 bucket `subscriber-migration-stack-prod-frontend`
- **Backend**: Lambda `subscriber-migration-stack-prod-BackendLambda-pw0yiCxXyN3J`
- **API**: Gateway `hsebznxeu6` 
- **Cloud DB**: DynamoDB tables (subscriber, audit, jobs)
- **Legacy DB**: MySQL RDS `subscriber-migration-legacydb`
- **Security**: Secrets Manager for credentials

### **🔐 GitHub Secrets** (Required)
```bash
AWS_ACCESS_KEY_ID=<your-aws-access-key>
AWS_SECRET_ACCESS_KEY=<your-aws-secret-key>
```

## 📋 Usage Guide

### **🏠 Dashboard**
- Combined stats from both legacy MySQL and cloud DynamoDB
- Real-time system health monitoring  
- Migration job progress tracking
- Professional charts and analytics

### **👥 Provisioning Modes**

| Mode | Description | Data Storage |
|------|-------------|-------------|
| ☁️ **Cloud** | Modern operations | DynamoDB only |
| 🏛️ **Legacy** | Existing data compatibility | MySQL RDS only |
| 🔄 **Dual** | Best of both worlds | Both systems |

### **🔄 Migration Operations**
1. **Upload CSV**: Legacy subscriber data
2. **Configure**: Source (legacy) → Destination (cloud)
3. **Monitor**: Real-time job progress
4. **Control**: Cancel, pause, resume with timestamps
5. **Copy Job ID**: One-click tracking reference

### **🔍 Bulk Operations**
- **Mass Delete**: Remove subscribers from legacy/cloud/both
- **Audit Compare**: Verify data consistency between systems
- **Export Data**: Download from specific or both systems
- **Statistics**: Real-time counts and health metrics

## 🎯 Architecture

```
🌐 Enhanced React Frontend (Material-UI)
         │
         ↓
🔗 API Gateway (hsebznxeu6)
         │
         ↓  
⚡ Production Flask Backend (Serverless)
     │                    │
     ↓                    ↓
☁️ DynamoDB           🏛️ MySQL RDS
(Cloud Data)        (Legacy Data)
```

## 🧪 Testing

### **API Health Check**
```bash
curl https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod/api/health
```

### **Authentication Test**
```bash
curl -X POST https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123"}'
```

### **Legacy Database Test**  
```bash
curl https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod/api/legacy/test
```

## 🛠️ Configuration

### **Available Deployment Options**
- **Full Deploy**: Frontend + Backend + API Gateway
- **Frontend Only**: Updates UI components only
- **Backend Only**: Updates Lambda function only

### **Environment Variables** (Auto-configured)
```bash
# Backend Lambda
SUBSCRIBER_TABLE_NAME=subscriber-table
LEGACY_DB_HOST=subscriber-migration-legacydb.cwd6wssgy4kr.us-east-1.rds.amazonaws.com
PROVISIONING_MODES=legacy,cloud,dual_prov
VERSION=2.0.0-production

# Frontend React
REACT_APP_API_BASE_URL=https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod
REACT_APP_LEGACY_ENABLED=true
```

## 📊 Monitoring

### **Real-time Metrics**
- 📈 **Subscriber Growth**: Track registrations over time
- 🔄 **Migration Progress**: Legacy → cloud data transfer
- 🏥 **System Health**: API response times, database connectivity
- 🔍 **Audit Trails**: Complete operation logging

### **Job Management**  
- 📅 **Timestamps**: Created, updated, completed times
- 📋 **Copy Job ID**: One-click reference copying
- ⏸️ **Controls**: Cancel, pause, resume operations
- 📊 **Progress**: Real-time status updates

## 💡 What's New in v2.0

✅ **Job Management Enhanced**: Timestamps, cancel functionality, copy Job ID  
✅ **Legacy MySQL Integration**: Complete dual-database support  
✅ **Professional UI**: Material-UI with responsive design  
✅ **Dual Provisioning**: Atomic operations across both systems  
✅ **Bulk Operations**: Mass deletion and audit comparison  
✅ **Analytics Dashboard**: Real-time statistics and charts  
✅ **CI/CD Pipeline**: Automated GitHub Actions deployment  
✅ **Comprehensive Testing**: API, auth, frontend, legacy DB validation  

## 🚨 Troubleshooting

### **Common Issues**

🔴 **Legacy DB Connection Failed**
- Check Lambda VPC configuration
- Verify security group allows MySQL (port 3306)
- Ensure Secrets Manager permissions

🔴 **Frontend Build Issues**  
- Workflow automatically clears npm cache
- Uses `npm install` instead of `npm ci`
- No manual intervention required

🔴 **API Gateway Errors**
- Check Lambda logs via CloudWatch
- Verify environment variables
- Test individual API endpoints

## 🚀 Next Steps

After successful deployment:

1. **🌐 Access Portal**: Visit the live URL above
2. **🔐 Login**: Use admin credentials to explore
3. **👥 Test Provisioning**: Create subscribers in different modes
4. **🔄 Try Migration**: Upload CSV for bulk data transfer
5. **📈 Monitor**: View real-time analytics and system health

---

<div align="center">

**🚀 [Launch Portal](http://subscriber-migration-stack-prod-frontend.s3-website-us-east-1.amazonaws.com/) | 📖 [Deploy Now](https://github.com/Jagadeesh2539/subscriber-migration-portal/actions) | 🔧 [GitHub Actions](https://github.com/Jagadeesh2539/subscriber-migration-portal/actions/workflows/main-deploy.yml)**

*Enterprise-grade subscriber migration portal - Ready for production use*

</div>