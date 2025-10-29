# GitHub Secrets Setup Guide

## 🔐 Required Repository Secrets

To enable automated deployment, you need to configure the following secrets in your GitHub repository:

**Repository Settings → Secrets and variables → Actions → New repository secret**

### 📡 AWS Configuration

| Secret Name | Value | Description |
|-------------|--------|-------------|
| `AWS_ACCESS_KEY_ID` | Your AWS Access Key | AWS credentials for deployment |
| `AWS_SECRET_ACCESS_KEY` | Your AWS Secret Key | AWS credentials for deployment |
| `LAMBDA_BACKEND_NAME` | `subscriber-migration-portal-main-BackendLambda-prod` | Your Lambda function name |

### 🔑 Application Configuration

| Secret Name | Value | Description |
|-------------|--------|-------------|
| `JWT_SECRET` | `subscriber-portal-jwt-secret-2025` | JWT signing secret |
| `SUBSCRIBER_TABLE_NAME` | `subscriber-table` | DynamoDB subscribers table |
| `AUDIT_LOG_TABLE_NAME` | `audit-log-table` | DynamoDB audit logs table |
| `MIGRATION_JOBS_TABLE_NAME` | `migration-jobs-table` | DynamoDB migration jobs table |
| `TOKEN_BLACKLIST_TABLE_NAME` | `token-blacklist-table` | DynamoDB token blacklist table |
| `MIGRATION_UPLOAD_BUCKET_NAME` | `migration-uploads` | S3 bucket for file uploads |
| `FRONTEND_ORIGIN` | `*` | Allowed CORS origins |

### 📱 Legacy Database (Optional)

| Secret Name | Value | Description |
|-------------|--------|-------------|
| `LEGACY_DB_SECRET_ARN` | `arn:aws:secretsmanager:...` | Legacy DB credentials ARN |
| `LEGACY_DB_HOST` | `your-mysql-host.com` | Legacy MySQL host |
| `LEGACY_DB_PORT` | `3306` | Legacy MySQL port |
| `LEGACY_DB_NAME` | `legacydb` | Legacy database name |

### 📢 Notifications (Optional)

| Secret Name | Value | Description |
|-------------|--------|-------------|
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/...` | Slack notifications (optional) |

## 🚀 Quick Setup Script

Use GitHub CLI to set all secrets at once:

```bash
# Install GitHub CLI if needed
# https://cli.github.com/

# Login to GitHub
gh auth login

# Set AWS secrets
gh secret set AWS_ACCESS_KEY_ID --body "YOUR_ACCESS_KEY"
gh secret set AWS_SECRET_ACCESS_KEY --body "YOUR_SECRET_KEY"
gh secret set LAMBDA_BACKEND_NAME --body "subscriber-migration-portal-main-BackendLambda-prod"

# Set application secrets
gh secret set JWT_SECRET --body "subscriber-portal-jwt-secret-2025"
gh secret set SUBSCRIBER_TABLE_NAME --body "subscriber-table"
gh secret set AUDIT_LOG_TABLE_NAME --body "audit-log-table"
gh secret set MIGRATION_JOBS_TABLE_NAME --body "migration-jobs-table"
gh secret set TOKEN_BLACKLIST_TABLE_NAME --body "token-blacklist-table"
gh secret set MIGRATION_UPLOAD_BUCKET_NAME --body "migration-uploads"
gh secret set FRONTEND_ORIGIN --body "*"

# Set legacy database secrets (if using)
gh secret set LEGACY_DB_SECRET_ARN --body "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:NAME"
gh secret set LEGACY_DB_HOST --body "your-mysql-host.com"
gh secret set LEGACY_DB_PORT --body "3306"
gh secret set LEGACY_DB_NAME --body "legacydb"

echo "✅ All secrets configured!"
```

## 🔍 Verify Secrets

Check if secrets are properly set:

```bash
# List all repository secrets
gh secret list

# Should show:
# AWS_ACCESS_KEY_ID
# AWS_SECRET_ACCESS_KEY
# LAMBDA_BACKEND_NAME
# JWT_SECRET
# SUBSCRIBER_TABLE_NAME
# AUDIT_LOG_TABLE_NAME
# MIGRATION_JOBS_TABLE_NAME
# TOKEN_BLACKLIST_TABLE_NAME
# MIGRATION_UPLOAD_BUCKET_NAME
# FRONTEND_ORIGIN
# LEGACY_DB_SECRET_ARN (if configured)
# LEGACY_DB_HOST (if configured)
# LEGACY_DB_PORT (if configured)
# LEGACY_DB_NAME (if configured)
```

## 🎯 Environment Setup

### Option 1: Development Only
- Set secrets directly in repository
- Deployments go to development Lambda function

### Option 2: Multi-Environment (Recommended)

1. **Create Environments:**
   - Go to Repository Settings → Environments
   - Create: `dev`, `stage`, `prod`
   - Configure protection rules as needed

2. **Environment-specific secrets:**
   - `dev`: Use development AWS resources
   - `stage`: Use staging AWS resources
   - `prod`: Use production AWS resources (with approvals)

## 📦 Manual Secrets Entry

If you prefer to set secrets manually:

1. **Go to Repository Settings**
   - Click on your repository
   - Go to Settings tab
   - Click "Secrets and variables" → "Actions"

2. **Add Each Secret**
   - Click "New repository secret"
   - Enter secret name (exact case)
   - Enter secret value
   - Click "Add secret"

3. **Repeat for All Secrets**
   - Use the table above as reference
   - Ensure exact naming and proper values

## 🚀 Trigger Deployment

Once secrets are configured:

1. **Automatic Deployment:**
   ```bash
   # Any push to main branch triggers deployment
   git add .
   git commit -m "Deploy application"
   git push origin main
   ```

2. **Manual Deployment:**
   - Go to Actions tab in GitHub
   - Click "Backend Deploy"
   - Click "Run workflow"
   - Select environment and run

## 🔒 Security Best Practices

### ✅ Do This
- Use least-privilege AWS IAM policies
- Rotate AWS keys regularly
- Use unique JWT secrets
- Enable environment protection rules
- Monitor secret usage in Actions logs

### ❌ Don't Do This
- Don't commit secrets to code
- Don't use production keys for development
- Don't share secret values in issues/PRs
- Don't use weak JWT secrets

## 📊 AWS IAM Policy

Minimum IAM policy for deployment:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:GetFunction",
        "lambda:InvokeFunction",
        "lambda:ListFunctions"
      ],
      "Resource": "arn:aws:lambda:us-east-1:*:function:subscriber-migration-portal-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "apigateway:GET"
      ],
      "Resource": "arn:aws:apigateway:us-east-1::/restapis*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:FilterLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:*:*"
    }
  ]
}
```

## 🎉 Next Steps

1. **Configure Secrets** using this guide
2. **Push to Main** to trigger automatic deployment
3. **Monitor Actions** tab for deployment progress
4. **Check Deployment Status** in commit comments
5. **Test Your Application** using the deployed API

---

**🚨 Important:** Once secrets are configured, every push to `main` branch will automatically deploy to AWS. Make sure your AWS resources are properly set up first!