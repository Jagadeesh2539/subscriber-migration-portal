# PowerShell script to find and fix the Lambda function
Write-Host "🔍 Finding Lambda functions in ap-south-1..." -ForegroundColor Green

# List all Lambda functions
try {
    $functions = aws lambda list-functions --region ap-south-1 --query 'Functions[].{Name:FunctionName,Runtime:Runtime,Handler:Handler}' --output json | ConvertFrom-Json
    
    if ($functions.Count -eq 0) {
        Write-Host "❌ No Lambda functions found in ap-south-1 region" -ForegroundColor Red
        Write-Host "📋 Available regions with Lambda functions:" -ForegroundColor Yellow
        
        # Check common regions for Lambda functions
        $regions = @("us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1", "ap-northeast-1")
        
        foreach ($region in $regions) {
            try {
                $regionFunctions = aws lambda list-functions --region $region --query 'Functions[].FunctionName' --output json 2>$null | ConvertFrom-Json
                if ($regionFunctions -and $regionFunctions.Count -gt 0) {
                    Write-Host "  📍 $region : $($regionFunctions -join ', ')" -ForegroundColor Cyan
                }
            } catch {
                # Ignore errors for regions without functions
            }
        }
        
        Write-Host "`n💡 To deploy a new Lambda function, run the CloudFormation stack first:" -ForegroundColor Yellow
        Write-Host "aws cloudformation deploy --template-file aws/cloudformation-template.yaml --stack-name subscriber-migration-stack --region ap-south-1 --capabilities CAPABILITY_IAM"
        exit 1
    }
    
    Write-Host "📋 Found Lambda functions in ap-south-1:" -ForegroundColor Green
    $functions | ForEach-Object { 
        Write-Host "  • $($_.Name) (Runtime: $($_.Runtime), Handler: $($_.Handler))" -ForegroundColor Cyan
    }
    
    # Look for subscriber migration related functions
    $migrationFunctions = $functions | Where-Object { 
        $_.Name -like "*subscriber*" -or 
        $_.Name -like "*migration*" -or 
        $_.Name -like "*backend*" -or
        $_.Name -like "*api*"
    }
    
    if ($migrationFunctions.Count -eq 0) {
        Write-Host "`n⚠️  No migration-related Lambda functions found." -ForegroundColor Yellow
        Write-Host "Available functions:" -ForegroundColor White
        $functions | ForEach-Object { Write-Host "  - $($_.Name)" }
        
        Write-Host "`n❓ Which function would you like to update? Enter the exact name:" -ForegroundColor Yellow
        $selectedFunction = Read-Host
        
        if ($selectedFunction -and ($functions | Where-Object { $_.Name -eq $selectedFunction })) {
            $functionName = $selectedFunction
        } else {
            Write-Host "❌ Invalid function name" -ForegroundColor Red
            exit 1
        }
    } elseif ($migrationFunctions.Count -eq 1) {
        $functionName = $migrationFunctions[0].Name
        Write-Host "`n🎯 Auto-selected function: $functionName" -ForegroundColor Green
    } else {
        Write-Host "`n🎯 Multiple migration functions found:" -ForegroundColor Yellow
        for ($i = 0; $i -lt $migrationFunctions.Count; $i++) {
            Write-Host "  $($i + 1). $($migrationFunctions[$i].Name)" -ForegroundColor Cyan
        }
        
        do {
            $choice = Read-Host "Enter number (1-$($migrationFunctions.Count))"
            $choiceNum = [int]$choice - 1
        } while ($choiceNum -lt 0 -or $choiceNum -ge $migrationFunctions.Count)
        
        $functionName = $migrationFunctions[$choiceNum].Name
    }
    
    Write-Host "`n🔧 Updating Lambda function: $functionName" -ForegroundColor Green
    
    # Check if lambda-package.zip exists
    if (!(Test-Path "backend\lambda-package.zip")) {
        Write-Host "📦 Creating Lambda package..." -ForegroundColor Yellow
        
        # Clean up previous builds
        if (Test-Path "backend\lambda-package") { Remove-Item -Recurse -Force "backend\lambda-package" }
        if (Test-Path "backend\lambda-package.zip") { Remove-Item -Force "backend\lambda-package.zip" }
        
        # Create package directory
        New-Item -ItemType Directory -Path "backend\lambda-package" -Force | Out-Null
        
        # Copy application files
        Copy-Item "backend\app.py" "backend\lambda-package\"
        Get-ChildItem "backend\*.py" | Copy-Item -Destination "backend\lambda-package\" -ErrorAction SilentlyContinue
        
        # Install dependencies
        Write-Host "📥 Installing Python dependencies..." -ForegroundColor Yellow
        Set-Location "backend"
        pip install -r requirements.txt -t lambda-package\
        
        # Create ZIP
        Write-Host "🗜️ Creating ZIP package..." -ForegroundColor Yellow
        Set-Location "lambda-package"
        
        # Try 7zip first, fallback to PowerShell compression
        try {
            & 7z a -tzip "..\lambda-package.zip" "*" -r | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "7zip failed" }
        } catch {
            # Fallback to PowerShell compression
            Set-Location ..
            Compress-Archive -Path "lambda-package\*" -DestinationPath "lambda-package.zip" -Force
        }
        
        Set-Location ..
        Set-Location ..
    }
    
    # Update Lambda function code
    Write-Host "🚀 Updating Lambda function code..." -ForegroundColor Green
    Set-Location "backend"
    $updateResult = aws lambda update-function-code --region ap-south-1 --function-name "$functionName" --zip-file fileb://lambda-package.zip
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "⏳ Waiting for update to complete..." -ForegroundColor Yellow
        aws lambda wait function-updated --region ap-south-1 --function-name "$functionName"
        
        Write-Host "⚙️ Updating function configuration..." -ForegroundColor Yellow
        aws lambda update-function-configuration --region ap-south-1 --function-name "$functionName" --handler "app.lambda_handler" --runtime "python3.9" --timeout 30 --memory-size 512
        
        Write-Host "`n🧪 Testing Lambda function..." -ForegroundColor Green
        
        # Test with empty event
        Write-Host "Testing empty event..." -ForegroundColor Cyan
        aws lambda invoke --region ap-south-1 --function-name "$functionName" --payload "{}" response1.json
        
        Write-Host "Response:" -ForegroundColor White
        $response1 = Get-Content response1.json | ConvertFrom-Json
        $response1 | ConvertTo-Json -Depth 4
        
        # Test health check
        Write-Host "`nTesting health check..." -ForegroundColor Cyan
        $healthPayload = @{
            httpMethod = "GET"
            path = "/api/health"
            headers = @{
                "Content-Type" = "application/json"
            }
        } | ConvertTo-Json -Depth 3 -Compress
        
        $healthPayload | Out-File -FilePath "health-payload.json" -Encoding utf8
        aws lambda invoke --region ap-south-1 --function-name "$functionName" --payload file://health-payload.json response2.json
        
        Write-Host "Response:" -ForegroundColor White
        $response2 = Get-Content response2.json | ConvertFrom-Json
        $response2 | ConvertTo-Json -Depth 4
        
        # Clean up
        Remove-Item -Force response1.json, response2.json, health-payload.json -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force lambda-package -ErrorAction SilentlyContinue
        Remove-Item -Force lambda-package.zip -ErrorAction SilentlyContinue
        
        Set-Location ..
        
        Write-Host "`n✅ Lambda function updated successfully!" -ForegroundColor Green
        Write-Host "🔍 The KeyError: 'headers' issue has been fixed." -ForegroundColor Green
        
        # Show function info
        Write-Host "`n📋 Function Details:" -ForegroundColor Yellow
        $functionInfo = aws lambda get-function --region ap-south-1 --function-name "$functionName" --query 'Configuration.{Handler:Handler,Runtime:Runtime,LastModified:LastModified}' --output json | ConvertFrom-Json
        Write-Host "  • Handler: $($functionInfo.Handler)" -ForegroundColor White
        Write-Host "  • Runtime: $($functionInfo.Runtime)" -ForegroundColor White
        Write-Host "  • Last Modified: $($functionInfo.LastModified)" -ForegroundColor White
        
    } else {
        Set-Location ..
        Write-Host "❌ Failed to update Lambda function" -ForegroundColor Red
        Write-Host "Error details: $updateResult" -ForegroundColor Red
    }
    
} catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "💡 Make sure you have AWS CLI configured and proper permissions" -ForegroundColor Yellow
}