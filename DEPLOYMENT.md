# 🚀 Deployment Guide - Subscriber Migration Portal

## 🎯 Quick Start (One-Click Deployment)

**Your application is ready to deploy with complete automation!**

### Option 1: One-Click Script (Recommended)

```powershell
# Run the automated deployment script
.\scripts\deploy-now.ps1 -SetupSecrets -Force
```

This script will:
- ✅ Check all prerequisites
- ✅ Set up GitHub secrets automatically
- ✅ Deploy your complete backend to AWS
- ✅ Run smoke tests to verify everything works
- ✅ Provide status updates and next steps

### Option 2: GitHub Actions (Manual)

1. **Set up secrets** (see [Setup Guide](scripts/setup-github-secrets.md))
2. **Push to main branch** - deployment happens automatically
3. **Monitor in Actions tab** - watch the deployment progress

---

## 🏗️ What Gets Deployed

### 🎯 Complete Backend Features

| Feature Category | Endpoints | Status |
|-----------------|-----------|--------|
| **Authentication** | `/api/auth/login`, `/api/auth/logout` | ✅ Ready |
| **Dashboard** | `/api/dashboard/stats` | ✅ Ready |
| **Subscribers** | `/api/subscribers` (CRUD) | ✅ Ready |
| **Bulk Operations** | `/api/operations/bulk-delete`, `/api/audit/compare` | ✅ Ready |
| **Migration** | `/api/migration/jobs`, `/api/migration/upload` | ✅ Ready |
| **Analytics** | `/api/analytics` | ✅ Ready |
| **Provisioning** | `/api/config/provisioning-mode` | ✅ Ready |
| **Export** | `/api/export/{system}` | ✅ Ready |
| **Audit** | `/api/audit/logs` | ✅ Ready |

### 🔧 Technical Stack

- **Backend**: Python 3.11 + Flask + AWS Lambda
- **Database**: DynamoDB (Cloud) + MySQL (Legacy)
- **Authentication**: JWT with role-based permissions
- **File Storage**: S3 for migration file uploads
- **Monitoring**: CloudWatch + comprehensive audit logging
- **Deployment**: GitHub Actions + automated testing

---

## 📋 Prerequisites

### Required Tools

```powershell
# 1. GitHub CLI (for secrets management)
winget install GitHub.cli
# or visit: https://cli.github.com/

# 2. AWS CLI (for deployment)
winget install Amazon.AWSCLI
# or visit: https://aws.amazon.com/cli/

# 3. Python 3.11+ (for local testing)
winget install Python.Python.3.11
```

### AWS Resources Required

1. **Lambda Function**: `subscriber-migration-portal-main-BackendLambda-prod`
2. **DynamoDB Tables**: 
   - `subscriber-table`
   - `audit-log-table` 
   - `migration-jobs-table`
   - `token-blacklist-table`
3. **S3 Bucket**: `migration-uploads`
4. **API Gateway**: (optional, for HTTP endpoints)
5. **IAM Role**: Lambda execution role with DynamoDB/S3 permissions

### GitHub Repository Setup

- **Actions enabled** in repository settings
- **Secrets configured** (see setup guide)
- **Workflows committed** to `.github/workflows/`

---

## 🎛️ Configuration Options

### Deployment Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **Development** | Single environment, minimal checks | Development/testing |
| **Staging** | Pre-production environment | User acceptance testing |
| **Production** | Full production deployment with approvals | Live application |

### Provisioning Modes

| Mode | Legacy DB | Cloud DB | Description |
|------|-----------|----------|-------------|
| **legacy** | ✅ Primary | ❌ Disabled | Legacy-only operations |
| **cloud** | ❌ Disabled | ✅ Primary | Cloud-only operations |
| **dual_prov** | ✅ Active | ✅ Active | Synchronized dual operations |

---

## 🚀 Deployment Methods

### Method 1: Automated Script (Recommended)

```powershell
# Full automated deployment with secrets setup
.\scripts\deploy-now.ps1 -SetupSecrets -Force

# Deploy to specific environment
.\scripts\deploy-now.ps1 -Environment prod -Force

# Quick deploy (skip tests)
.\scripts\deploy-now.ps1 -SkipTests -Force
```

**What it does:**
1. ✅ Validates all prerequisites
2. ✅ Sets up GitHub repository secrets
3. ✅ Commits and pushes changes
4. ✅ Triggers GitHub Actions deployment
5. ✅ Monitors deployment progress
6. ✅ Opens browser to track status

### Method 2: GitHub Actions (Manual Trigger)

1. **Go to Actions tab** in your repository
2. **Select "Backend Deploy"** workflow
3. **Click "Run workflow"** button
4. **Choose environment** (dev/stage/prod)
5. **Click "Run workflow"** to start

### Method 3: Git Push (Automatic)

```bash
# Any push to main triggers automatic deployment
git add .
git commit -m "Deploy backend updates"
git push origin main
```

### Method 4: Manual AWS Deployment

```powershell
# If you need to deploy manually to AWS
.\deploy-complete-backend.ps1
```

---

## 🔧 Setup Instructions

### Step 1: Clone and Prepare

```bash
git clone https://github.com/Jagadeesh2539/subscriber-migration-portal.git
cd subscriber-migration-portal
```

### Step 2: Configure AWS

```bash
# Configure AWS CLI with your credentials
aws configure
# Enter: Access Key, Secret Key, Region (us-east-1), Output (json)

# Verify your Lambda function exists
aws lambda get-function --function-name subscriber-migration-portal-main-BackendLambda-prod --region us-east-1
```

### Step 3: Set up GitHub Secrets

**Option A: Use the script**
```powershell
.\scripts\deploy-now.ps1 -SetupSecrets
```

**Option B: Manual setup**
1. Go to repository **Settings** → **Secrets and variables** → **Actions**
2. Add required secrets (see [Setup Guide](scripts/setup-github-secrets.md))

### Step 4: Deploy

```powershell
# One command deployment
.\scripts\deploy-now.ps1 -Force
```

---

## 📊 Monitoring & Verification

### GitHub Actions Dashboard
- **URL**: `https://github.com/Jagadeesh2539/subscriber-migration-portal/actions`
- **Monitor**: Build, test, and deployment progress
- **Logs**: Detailed logs for each step

### AWS Lambda Console
- **URL**: `https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/subscriber-migration-portal-main-BackendLambda-prod`
- **Monitor**: Function logs, metrics, configuration
- **Test**: Direct function invocation

### API Testing

```bash
# Test health endpoint
curl https://YOUR-API-GATEWAY-ID.execute-api.us-east-1.amazonaws.com/prod/api/health

# Test authentication
curl -X POST https://YOUR-API-GATEWAY-URL/prod/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123"}'
```

### Verification Checklist

- [ ] ✅ GitHub Actions workflow completes successfully
- [ ] ✅ Lambda function updated (check Last Modified timestamp)
- [ ] ✅ Health endpoint returns 200 with version info
- [ ] ✅ Authentication endpoint responds correctly
- [ ] ✅ No "KeyError: headers" in CloudWatch logs
- [ ] ✅ All API endpoints return proper responses

---

## 🧪 Testing

### Automated Tests (Part of Deployment)

1. **Smoke Tests**: Verify basic functionality
2. **Integration Tests**: Test API endpoints
3. **Security Tests**: Check for vulnerabilities
4. **Configuration Tests**: Validate setup

### Manual Testing

```powershell
# Run smoke tests manually
gh workflow run smoke-tests.yml

# Test specific function
aws lambda invoke --function-name subscriber-migration-portal-main-BackendLambda-prod --payload '{}' response.json
```

---

## 🔍 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| **Function not found** | Check Lambda function name in secrets |
| **Permission denied** | Verify AWS credentials and IAM policies |
| **Build failed** | Check Python dependencies in requirements.txt |
| **Secrets missing** | Run setup script or configure manually |
| **Tests failing** | Check CloudWatch logs for errors |

### Debug Commands

```powershell
# Check GitHub secrets
gh secret list

# Check AWS connection
aws sts get-caller-identity

# Check Lambda function
aws lambda get-function --function-name subscriber-migration-portal-main-BackendLambda-prod

# View recent deployments
gh run list --limit 5
```

### Log Locations

- **GitHub Actions**: Repository Actions tab
- **AWS Lambda**: CloudWatch Logs `/aws/lambda/subscriber-migration-portal-main-BackendLambda-prod`
- **Local builds**: Terminal output

---

## 🚀 Production Deployment

### Pre-Production Checklist

- [ ] ✅ All tests passing in development
- [ ] ✅ Security scan completed
- [ ] ✅ Environment variables configured
- [ ] ✅ Database connections tested
- [ ] ✅ Backup strategy in place
- [ ] ✅ Monitoring alerts configured

### Production Process

1. **Deploy to Staging** first
   ```powershell
   .\scripts\deploy-now.ps1 -Environment stage
   ```

2. **Run full test suite**
   ```bash
   gh workflow run smoke-tests.yml --ref main
   ```

3. **Deploy to Production**
   ```powershell
   .\scripts\deploy-now.ps1 -Environment prod
   ```

4. **Verify production deployment**

5. **Monitor for issues**

### Rollback Process

```powershell
# If issues occur, rollback to previous version
aws lambda update-function-code --function-name subscriber-migration-portal-main-BackendLambda-prod --s3-bucket your-backup-bucket --s3-key previous-version.zip
```

---

## 📈 Performance & Scaling

### Current Configuration
- **Memory**: 512 MB
- **Timeout**: 30 seconds  
- **Concurrent executions**: 1000 (AWS default)
- **Package size**: ~15-25 MB

### Scaling Considerations
- **DynamoDB**: Auto-scaling enabled
- **Lambda**: Increase memory for better performance
- **API Gateway**: Rate limiting configured
- **S3**: Unlimited storage

---

## 🔐 Security

### Security Features
- ✅ JWT authentication with role-based access
- ✅ Rate limiting on API endpoints
- ✅ Input sanitization and validation
- ✅ Audit logging for all operations
- ✅ Token blacklisting for secure logout
- ✅ CORS protection

### Security Best Practices
- 🔑 Rotate AWS keys regularly
- 🔑 Use least-privilege IAM policies
- 🔑 Monitor CloudWatch logs for anomalies
- 🔑 Keep dependencies updated
- 🔑 Use environment-specific secrets

---

## 📞 Support

### Getting Help

1. **Check logs** in GitHub Actions and CloudWatch
2. **Review documentation** in this repository
3. **Run diagnostic commands** from troubleshooting section
4. **Check AWS service health** status pages

### Quick Fixes

```powershell
# Reset deployment (clean slate)
git pull origin main
.\scripts\deploy-now.ps1 -SetupSecrets -Force

# Manual function update
.\deploy-complete-backend.ps1

# Run diagnostics
aws lambda get-function --function-name subscriber-migration-portal-main-BackendLambda-prod
gh run list --limit 3
```

---

## 🎉 Success Metrics

### Deployment Success Indicators
- ✅ GitHub Actions workflow shows green checkmark
- ✅ Lambda function "Last modified" timestamp updated
- ✅ Health endpoint returns version 2.2.0+
- ✅ All smoke tests pass
- ✅ No errors in CloudWatch logs
- ✅ Frontend can connect to backend APIs

### Application Ready Indicators
- ✅ Dashboard loads with real statistics
- ✅ Subscriber management CRUD operations work
- ✅ Bulk operations process correctly
- ✅ Migration jobs can be created and monitored
- ✅ Analytics show data trends
- ✅ File uploads process successfully
- ✅ Audit logs capture all activities

---

**🎯 Your Subscriber Migration Portal is now production-ready with complete automation!**

**Next Step**: Run `./scripts/deploy-now.ps1 -SetupSecrets -Force` to deploy everything automatically.