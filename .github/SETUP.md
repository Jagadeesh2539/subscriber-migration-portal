# 🚀 CI/CD Setup Guide - Complete Automation

This guide will help you set up **complete end-to-end automation** for your Subscriber Migration Portal using GitHub Actions.

## 🎯 Overview

The CI/CD pipeline provides **100% automation** including:

✅ **Template Validation** - SAM template syntax and structure validation  
✅ **Stack Management** - CloudFormation stack creation/updates with retries  
✅ **Lambda Deployment** - Automatic code deployment with debugging  
✅ **Database Initialization** - Schema setup with sample data  
✅ **Frontend Deployment** - React build and S3 deployment  
✅ **CORS Configuration** - Automatic S3 website and API Gateway setup  
✅ **Smoke Tests** - Comprehensive health and functionality checks  
✅ **Post-deployment Validation** - Configuration verification  

## 🔐 Required GitHub Secrets

### **Step 1: Create AWS IAM User**

First, create an IAM user with the necessary permissions:

```bash
# Create IAM user
aws iam create-user --user-name github-actions-subscriber-portal

# Create access key
aws iam create-access-key --user-name github-actions-subscriber-portal
```

### **Step 2: Create IAM Policy**

Create a policy with the required permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "apigateway:*",
        "dynamodb:*",
        "s3:*",
        "iam:*",
        "secretsmanager:*",
        "logs:*",
        "events:*",
        "application-autoscaling:*",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

Attach the policy to your user:

```bash
# Save the above JSON as policy.json
aws iam create-policy \
  --policy-name GitHubActionsSubscriberPortalPolicy \
  --policy-document file://policy.json

# Attach policy to user
aws iam attach-user-policy \
  --user-name github-actions-subscriber-portal \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/GitHubActionsSubscriberPortalPolicy
```

### **Step 3: Configure GitHub Secrets**

Go to your GitHub repository → Settings → Secrets and variables → Actions, and add these secrets:

| Secret Name | Description | Value |
|-------------|-------------|-------|
| `AWS_ACCESS_KEY_ID` | AWS Access Key ID | From IAM user creation |
| `AWS_SECRET_ACCESS_KEY` | AWS Secret Access Key | From IAM user creation |

## 🏗️ Environment Configuration

### **Automatic Environment Detection**

The pipeline automatically determines the deployment environment:

- **`main` branch** → **Production** environment
- **`develop` branch** → **Staging** environment  
- **Other branches** → **Development** environment
- **Manual dispatch** → User-selected environment

### **Manual Deployment**

Trigger manual deployment with custom options:

1. Go to **Actions** tab in your repository
2. Select **🚀 Deploy Subscriber Migration Portal**
3. Click **Run workflow**
4. Choose options:
   - **Environment**: `dev`, `staging`, or `prod`
   - **Force recreate stack**: Delete and recreate CloudFormation stack
   - **Cleanup resources**: Remove failed/orphaned resources

## 🚀 Deployment Process

### **Automatic Triggers**

```yaml
# Triggers deployment on:
- Push to main/develop branch
- Pull request to main branch  
- Manual workflow dispatch
```

### **Deployment Steps**

1. **🔍 Pre-deployment Validation**
   - Template syntax validation
   - Lambda function structure check
   - Frontend file validation
   - Environment variable setup

2. **🏗️ AWS Infrastructure Deployment**
   - Stack existence check and caching
   - Resource cleanup (if requested)
   - Force recreation (if requested)
   - Lambda layer building
   - SAM application deployment with retries
   - Lambda function configuration debugging

3. **🗄️ Database Initialization**
   - User credentials setup in Secrets Manager
   - Sample data insertion
   - Schema validation

4. **🌐 Frontend Deployment**
   - Dependency installation with cache management
   - Production build creation
   - S3 bucket setup with CORS configuration
   - Website hosting configuration
   - File upload with cache optimization

5. **🧪 Comprehensive Smoke Tests**
   - Health endpoint testing
   - Authentication flow validation
   - Protected endpoint access
   - Database connectivity verification

6. **🔧 Post-deployment Configuration**
   - CloudWatch logs verification
   - DynamoDB table status check
   - S3 bucket configuration validation
   - Lambda function performance checks
   - API Gateway throttling verification

## 📊 Deployment Outputs

### **Successful Deployment**

```
===============================================
🎉 DEPLOYMENT SUMMARY
===============================================
Stack Name:       subscriber-migration-portal-prod
Environment:      prod
Region:          us-east-1
API Endpoint:    https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod
Upload Bucket:   subscriber-migration-portal-uploads-prod
Subscriber Table: subscriber-migration-portal-subscribers
Table Status:    ACTIVE
===============================================
✅ All post-deployment checks completed!
🚀 Your application is ready for use!
===============================================
```

### **Generated Resources**

- **API Gateway**: RESTful API with Lambda integration
- **Lambda Functions**: Individual functions per endpoint
- **DynamoDB Tables**: Subscribers, audit logs, migration jobs
- **S3 Buckets**: File uploads and frontend hosting
- **IAM Roles**: Function execution and service permissions
- **CloudWatch**: Logs, metrics, and alarms
- **Secrets Manager**: User credentials storage

## 🛠️ Troubleshooting

### **Common Issues and Solutions**

#### **1. AWS Permissions Error**

```
Error: User: arn:aws:iam::123456789012:user/github-actions 
is not authorized to perform: cloudformation:CreateStack
```

**Solution**: Verify IAM policy is attached correctly:

```bash
# Check attached policies
aws iam list-attached-user-policies --user-name github-actions-subscriber-portal

# Verify policy permissions
aws iam get-policy-version --policy-arn YOUR_POLICY_ARN --version-id v1
```

#### **2. CloudFormation Stack Creation Failed**

```
Resource handler returned message: "Resource of type 
'AWS::DynamoDB::Table' with identifier 'MyTable' already exists."
```

**Solution**: Use force recreate option:

1. Go to Actions → Run workflow
2. Check **Force recreate stack** option
3. This will delete and recreate the entire stack

#### **3. Lambda Function Deployment Issues**

```
InvalidParameterValueException: The role defined for the function 
cannot be assumed by Lambda.
```

**Solution**: IAM role propagation delay - wait and retry:

```bash
# The workflow automatically retries with exponential backoff
# Manual retry: Re-run the failed job
```

#### **4. Frontend Build Failures**

```
npm ERR! EINTEGRITY: sha512 integrity checksum failed
```

**Solution**: The workflow automatically handles this:

```yaml
# Automatic npm cache cleanup and retry
npm cache verify
npm install --force --no-audit
```

#### **5. S3 Bucket Name Conflicts**

```
BucketAlreadyExists: The requested bucket name is not available
```

**Solution**: Bucket names include stack name and are unique per deployment.

### **Debug Logs**

To access detailed logs:

1. Go to **Actions** tab
2. Click on the failed workflow run
3. Expand the failed job step
4. Check the detailed logs for error messages

### **Manual Recovery**

If automation fails, you can deploy manually:

```bash
# Clone the repository
git clone https://github.com/Jagadeesh2539/subscriber-migration-portal.git
cd subscriber-migration-portal

# Deploy infrastructure
cd aws
./deploy.sh --stage dev --region us-east-1

# Deploy frontend
cd ../frontend
npm install
npm run build
# Upload to S3 manually
```

## 📈 Monitoring and Alerts

### **CloudWatch Integration**

The deployment automatically creates:

- **Custom Metrics**: API requests, errors, latency
- **Log Groups**: Function logs with retention policies
- **Alarms**: High error rates, performance issues
- **Dashboards**: System health visualization

### **GitHub Actions Monitoring**

- **Workflow Status**: Badge in README
- **Deployment History**: All runs logged
- **Failure Notifications**: GitHub notifications on failure
- **Manual Intervention**: Ability to re-run failed jobs

## 🔄 Rollback Strategy

### **Automatic Rollback**

If smoke tests fail, the deployment is considered failed but resources remain for investigation.

### **Manual Rollback**

```bash
# Rollback to previous version
aws cloudformation update-stack \
  --stack-name subscriber-migration-portal-prod \
  --use-previous-template \
  --capabilities CAPABILITY_IAM

# Or deploy specific commit
git checkout PREVIOUS_COMMIT_SHA
# Trigger manual deployment
```

## 🌐 Multi-Environment Setup

### **Branch Strategy**

```
main branch    → Production (prod)
develop branch → Staging (staging)  
feature/*      → Development (dev)
```

### **Environment-Specific Configuration**

| Environment | API Gateway | CORS Origins | Error Reporting |
|-------------|------------|--------------|----------------|
| **dev** | `dev` stage | `localhost:3000` | Detailed |
| **staging** | `staging` stage | `staging.domain.com` | Moderate |
| **prod** | `prod` stage | `yourdomain.com` | Minimal |

## 📞 Support

If you encounter issues:

1. **Check Workflow Logs**: GitHub Actions detailed logs
2. **AWS Console**: CloudFormation events and logs
3. **CloudWatch**: Application and system logs
4. **Create Issue**: GitHub repository issues

## 🔒 Security Considerations

- **AWS Credentials**: Stored as GitHub encrypted secrets
- **IAM Policies**: Principle of least privilege
- **Resource Encryption**: All data encrypted at rest
- **Network Security**: VPC isolation where applicable
- **Access Control**: Role-based authentication

---

## 🎉 Ready to Deploy!

Once you've configured the secrets:

1. **Push to `main`** for production deployment
2. **Push to `develop`** for staging deployment
3. **Use manual dispatch** for custom deployments

**Your serverless application will be automatically deployed with zero manual intervention!** 🚀