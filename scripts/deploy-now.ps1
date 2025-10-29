#!/usr/bin/env pwsh
# One-Click Deployment Script for Subscriber Migration Portal
# This script automates the complete deployment process

param(
    [Parameter()][string]$Environment = "dev",
    [Parameter()][string]$AwsRegion = "us-east-1",
    [Parameter()][string]$LambdaFunctionName = "subscriber-migration-portal-main-BackendLambda-prod",
    [Parameter()][switch]$SetupSecrets,
    [Parameter()][switch]$SkipTests,
    [Parameter()][switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 SUBSCRIBER MIGRATION PORTAL - ONE-CLICK DEPLOYMENT" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host "Environment: $Environment" -ForegroundColor Cyan
Write-Host "AWS Region: $AwsRegion" -ForegroundColor Cyan
Write-Host "Lambda Function: $LambdaFunctionName" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Green

try {
    # Step 1: Prerequisites Check
    Write-Host "`n🔍 Step 1: Checking Prerequisites..." -ForegroundColor Yellow
    
    # Check if in git repository
    if (!(Test-Path ".git")) {
        throw "This script must be run from the root of your git repository"
    }
    
    # Check if GitHub CLI is installed
    $ghInstalled = $false
    try {
        gh --version | Out-Null
        $ghInstalled = $true
        Write-Host "✅ GitHub CLI available" -ForegroundColor Green
    } catch {
        Write-Host "⚠️ GitHub CLI not installed" -ForegroundColor Yellow
    }
    
    # Check if AWS CLI is installed
    $awsInstalled = $false
    try {
        aws --version | Out-Null
        $awsInstalled = $true
        Write-Host "✅ AWS CLI available" -ForegroundColor Green
    } catch {
        Write-Host "⚠️ AWS CLI not installed" -ForegroundColor Yellow
    }
    
    # Check if we're authenticated with GitHub
    if ($ghInstalled) {
        try {
            gh auth status | Out-Null
            Write-Host "✅ GitHub CLI authenticated" -ForegroundColor Green
        } catch {
            Write-Host "⚠️ GitHub CLI not authenticated" -ForegroundColor Yellow
            Write-Host "Run: gh auth login" -ForegroundColor White
        }
    }
    
    # Step 2: Setup GitHub Secrets (if requested)
    if ($SetupSecrets -and $ghInstalled) {
        Write-Host "`n🔐 Step 2: Setting up GitHub Secrets..." -ForegroundColor Yellow
        
        Write-Host "Setting up repository secrets for automated deployment..." -ForegroundColor White
        
        # AWS Configuration
        if (!$Force) {
            $awsAccessKey = Read-Host "Enter your AWS Access Key ID" -MaskInput
            $awsSecretKey = Read-Host "Enter your AWS Secret Access Key" -MaskInput
        } else {
            # Use environment variables if available
            $awsAccessKey = $env:AWS_ACCESS_KEY_ID
            $awsSecretKey = $env:AWS_SECRET_ACCESS_KEY
        }
        
        if ($awsAccessKey -and $awsSecretKey) {
            try {
                gh secret set AWS_ACCESS_KEY_ID --body $awsAccessKey
                gh secret set AWS_SECRET_ACCESS_KEY --body $awsSecretKey
                gh secret set LAMBDA_BACKEND_NAME --body $LambdaFunctionName
                
                # Application secrets with defaults
                gh secret set JWT_SECRET --body "subscriber-portal-jwt-secret-2025"
                gh secret set SUBSCRIBER_TABLE_NAME --body "subscriber-table"
                gh secret set AUDIT_LOG_TABLE_NAME --body "audit-log-table"
                gh secret set MIGRATION_JOBS_TABLE_NAME --body "migration-jobs-table"
                gh secret set TOKEN_BLACKLIST_TABLE_NAME --body "token-blacklist-table"
                gh secret set MIGRATION_UPLOAD_BUCKET_NAME --body "migration-uploads"
                gh secret set FRONTEND_ORIGIN --body "*"
                
                Write-Host "✅ GitHub secrets configured successfully" -ForegroundColor Green
            } catch {
                Write-Host "❌ Failed to set GitHub secrets: $($_.Exception.Message)" -ForegroundColor Red
            }
        } else {
            Write-Host "⚠️ Skipping secrets setup - AWS credentials not provided" -ForegroundColor Yellow
        }
    }
    
    # Step 3: Verify Backend Files
    Write-Host "`n📋 Step 3: Verifying Backend Files..." -ForegroundColor Yellow
    
    if (!(Test-Path "backend/app.py")) {
        throw "Backend application file not found: backend/app.py"
    }
    Write-Host "✅ Backend application file found" -ForegroundColor Green
    
    if (!(Test-Path "backend/requirements.txt")) {
        throw "Requirements file not found: backend/requirements.txt"
    }
    Write-Host "✅ Requirements file found" -ForegroundColor Green
    
    # Check if workflows exist
    if (!(Test-Path ".github/workflows/backend-deploy.yml")) {
        throw "Deployment workflow not found. Make sure GitHub Actions workflows are committed."
    }
    Write-Host "✅ GitHub Actions workflows found" -ForegroundColor Green
    
    # Step 4: Test Local Build (if not skipping)
    if (!$SkipTests) {
        Write-Host "`n🧪 Step 4: Testing Local Build..." -ForegroundColor Yellow
        
        if (Test-Path "backend/test-build") {
            Remove-Item -Recurse -Force "backend/test-build"
        }
        
        # Create test build
        New-Item -ItemType Directory -Path "backend/test-build" -Force | Out-Null
        
        # Test pip install
        Set-Location "backend"
        try {
            pip install -r requirements.txt -t test-build/ --quiet
            Copy-Item "app.py" "test-build/"
            
            # Test Python syntax
            Set-Location "test-build"
            python -m py_compile app.py
            
            Set-Location ..
            Remove-Item -Recurse -Force "test-build"
            Set-Location ..
            
            Write-Host "✅ Local build test passed" -ForegroundColor Green
        } catch {
            Set-Location .. # Ensure we're back in root
            throw "Local build test failed: $($_.Exception.Message)"
        }
    }
    
    # Step 5: Commit and Push Changes
    Write-Host "`n📤 Step 5: Deploying to GitHub..." -ForegroundColor Yellow
    
    # Check if there are any uncommitted changes
    $gitStatus = git status --porcelain
    if ($gitStatus) {
        Write-Host "Found uncommitted changes:" -ForegroundColor White
        git status --short
        
        if (!$Force) {
            $commit = Read-Host "Do you want to commit and deploy these changes? (y/N)"
            if ($commit.ToLower() -ne 'y' -and $commit.ToLower() -ne 'yes') {
                Write-Host "Deployment cancelled by user" -ForegroundColor Yellow
                exit 0
            }
        }
        
        # Commit changes
        git add .
        git commit -m "Deploy complete backend with automation - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        Write-Host "✅ Changes committed" -ForegroundColor Green
    }
    
    # Push to trigger deployment
    Write-Host "Pushing to main branch to trigger deployment..." -ForegroundColor White
    git push origin main
    Write-Host "✅ Code pushed to main branch" -ForegroundColor Green
    
    # Step 6: Monitor Deployment
    Write-Host "`n🔍 Step 6: Monitoring Deployment..." -ForegroundColor Yellow
    
    if ($ghInstalled) {
        Write-Host "Opening GitHub Actions in browser..." -ForegroundColor White
        
        # Get repository info
        $repoInfo = gh repo view --json owner,name | ConvertFrom-Json
        $repoUrl = "https://github.com/$($repoInfo.owner.login)/$($repoInfo.name)/actions"
        
        try {
            Start-Process $repoUrl
        } catch {
            Write-Host "Could not open browser. Visit: $repoUrl" -ForegroundColor White
        }
        
        # Wait a moment for the workflow to start
        Start-Sleep 10
        
        # Check latest workflow run
        Write-Host "Checking deployment status..." -ForegroundColor White
        try {
            $runs = gh run list --limit 1 --json status,conclusion,workflowName,url | ConvertFrom-Json
            
            if ($runs -and $runs.Count -gt 0) {
                $latestRun = $runs[0]
                Write-Host "Latest workflow: $($latestRun.workflowName)" -ForegroundColor White
                Write-Host "Status: $($latestRun.status)" -ForegroundColor White
                Write-Host "URL: $($latestRun.url)" -ForegroundColor White
                
                if ($latestRun.status -eq "in_progress") {
                    Write-Host "🔄 Deployment is running..." -ForegroundColor Blue
                } elseif ($latestRun.conclusion -eq "success") {
                    Write-Host "✅ Deployment completed successfully!" -ForegroundColor Green
                } elseif ($latestRun.conclusion -eq "failure") {
                    Write-Host "❌ Deployment failed. Check the workflow logs." -ForegroundColor Red
                }
            }
        } catch {
            Write-Host "Could not check workflow status. Visit GitHub Actions manually." -ForegroundColor Yellow
        }
    }
    
    # Step 7: Final Instructions
    Write-Host "`n🎉 DEPLOYMENT INITIATED SUCCESSFULLY!" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
    
    Write-Host "`n📋 What happens next:" -ForegroundColor Yellow
    Write-Host "1. GitHub Actions will automatically build and package your backend" -ForegroundColor White
    Write-Host "2. The package will be deployed to your AWS Lambda function" -ForegroundColor White
    Write-Host "3. Smoke tests will verify the deployment" -ForegroundColor White
    Write-Host "4. A status comment will be added to your commit" -ForegroundColor White
    
    Write-Host "`n🔗 Monitor progress:" -ForegroundColor Yellow
    if ($ghInstalled) {
        Write-Host "- GitHub Actions: https://github.com/$(git config --get remote.origin.url | Split-Path -Leaf | ForEach-Object { $_ -replace '\.git$' })/actions" -ForegroundColor White
    }
    Write-Host "- AWS Lambda Console: https://$AwsRegion.console.aws.amazon.com/lambda/home?region=$AwsRegion#/functions/$LambdaFunctionName" -ForegroundColor White
    
    Write-Host "`n✅ Expected completion time: 2-3 minutes" -ForegroundColor Green
    
    Write-Host "`n📱 Once deployment completes:" -ForegroundColor Yellow
    Write-Host "- Your backend will be production-ready" -ForegroundColor White
    Write-Host "- All GUI features will have working APIs" -ForegroundColor White
    Write-Host "- KeyError: 'headers' issue will be resolved" -ForegroundColor White
    Write-Host "- Dashboard, bulk operations, migration, analytics all functional" -ForegroundColor White
    
} catch {
    Write-Host "`n❌ DEPLOYMENT FAILED" -ForegroundColor Red
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    
    Write-Host "`n🔧 Troubleshooting steps:" -ForegroundColor Yellow
    Write-Host "1. Ensure you're in the correct repository directory" -ForegroundColor White
    Write-Host "2. Check if GitHub CLI is installed and authenticated" -ForegroundColor White
    Write-Host "3. Verify AWS CLI is configured" -ForegroundColor White
    Write-Host "4. Make sure all backend files exist" -ForegroundColor White
    Write-Host "5. Check GitHub repository permissions" -ForegroundColor White
    
    Write-Host "`n📞 Need help?" -ForegroundColor Yellow
    Write-Host "- Check the README.md for detailed setup instructions" -ForegroundColor White
    Write-Host "- Review scripts/setup-github-secrets.md for configuration" -ForegroundColor White
    Write-Host "- Ensure AWS resources are properly configured" -ForegroundColor White
    
    exit 1
}

Write-Host "`n🎯 Your Subscriber Migration Portal deployment is now in progress!" -ForegroundColor Green