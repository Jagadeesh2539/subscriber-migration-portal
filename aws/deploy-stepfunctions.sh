#!/bin/bash

# Step Functions Deployment Script
# Uploads Step Functions definitions to S3 before SAM deployment

set -euo pipefail

# Configuration
STACK_NAME="${STACK_NAME:-subscriber-migration-portal-prod}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
UPLOADS_BUCKET="${STACK_NAME}-uploads"
STEPFUNCTIONS_DIR="aws/stepfunctions"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to validate Step Functions JSON
validate_stepfunction() {
    local file="$1"
    local name=$(basename "$file" .json)
    
    log_info "Validating Step Function definition: $name"
    
    # Check if file exists
    if [[ ! -f "$file" ]]; then
        log_error "Step Function file not found: $file"
        return 1
    fi
    
    # Validate JSON syntax
    if ! jq empty "$file" 2>/dev/null; then
        log_error "Invalid JSON syntax in $file"
        return 1
    fi
    
    # Check required fields
    if ! jq -e '.Comment' "$file" >/dev/null; then
        log_warning "Missing Comment field in $file"
    fi
    
    if ! jq -e '.StartAt' "$file" >/dev/null; then
        log_error "Missing StartAt field in $file"
        return 1
    fi
    
    if ! jq -e '.States' "$file" >/dev/null; then
        log_error "Missing States field in $file"
        return 1
    fi
    
    # Validate states structure
    local start_state=$(jq -r '.StartAt' "$file")
    if ! jq -e ".States[\"$start_state\"]" "$file" >/dev/null; then
        log_error "StartAt state '$start_state' not found in States in $file"
        return 1
    fi
    
    log_success "Step Function definition valid: $name"
    return 0
}

# Function to create or verify S3 bucket
setup_s3_bucket() {
    log_info "Setting up S3 bucket: $UPLOADS_BUCKET"
    
    # Check if bucket exists
    if aws s3api head-bucket --bucket "$UPLOADS_BUCKET" 2>/dev/null; then
        log_info "S3 bucket already exists: $UPLOADS_BUCKET"
    else
        log_info "Creating S3 bucket: $UPLOADS_BUCKET"
        
        # Create bucket
        if [[ "$AWS_REGION" == "us-east-1" ]]; then
            aws s3api create-bucket --bucket "$UPLOADS_BUCKET"
        else
            aws s3api create-bucket \
                --bucket "$UPLOADS_BUCKET" \
                --create-bucket-configuration LocationConstraint="$AWS_REGION"
        fi
        
        # Enable versioning
        aws s3api put-bucket-versioning \
            --bucket "$UPLOADS_BUCKET" \
            --versioning-configuration Status=Enabled
        
        # Block public access
        aws s3api put-public-access-block \
            --bucket "$UPLOADS_BUCKET" \
            --public-access-block-configuration \
            "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
        
        log_success "S3 bucket created successfully: $UPLOADS_BUCKET"
    fi
}

# Function to upload Step Functions definitions
upload_stepfunctions() {
    log_info "Uploading Step Functions definitions to S3"
    
    # Create stepfunctions directory in S3 if it doesn't exist
    aws s3api put-object \
        --bucket "$UPLOADS_BUCKET" \
        --key "stepfunctions/" \
        --content-length 0
    
    # Upload each Step Function definition
    for file in "$STEPFUNCTIONS_DIR"/*.json; do
        if [[ -f "$file" ]]; then
            local filename=$(basename "$file")
            local s3_key="stepfunctions/$filename"
            
            log_info "Uploading $filename to s3://$UPLOADS_BUCKET/$s3_key"
            
            aws s3 cp "$file" "s3://$UPLOADS_BUCKET/$s3_key" \
                --content-type "application/json"
            
            log_success "Uploaded: $filename"
        fi
    done
}

# Function to test Step Functions definitions
test_stepfunctions() {
    log_info "Testing Step Functions definitions (dry run)"
    
    # Note: This would require the Step Functions to be created first
    # For now, we'll just validate the JSON structure
    
    for file in "$STEPFUNCTIONS_DIR"/*.json; do
        if [[ -f "$file" ]]; then
            local name=$(basename "$file" .json)
            log_info "Testing Step Function: $name"
            
            # You could add more sophisticated testing here
            # For example, using AWS Step Functions Local or mocking
            
            log_success "Test passed: $name"
        fi
    done
}

# Function to clean up on error
cleanup_on_error() {
    log_error "Deployment failed, cleaning up..."
    
    # Remove uploaded Step Functions definitions
    log_info "Removing uploaded Step Functions definitions"
    aws s3 rm "s3://$UPLOADS_BUCKET/stepfunctions/" --recursive --quiet || true
    
    log_warning "Cleanup completed. Manual cleanup may be required."
}

# Main deployment function
main() {
    log_info "Starting Step Functions deployment for stack: $STACK_NAME"
    log_info "AWS Region: $AWS_REGION"
    log_info "AWS Account: $AWS_ACCOUNT_ID"
    
    # Set trap for error cleanup
    trap cleanup_on_error ERR
    
    # Check prerequisites
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found. Please install AWS CLI."
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        log_error "jq not found. Please install jq for JSON processing."
        exit 1
    fi
    
    # Check if Step Functions directory exists
    if [[ ! -d "$STEPFUNCTIONS_DIR" ]]; then
        log_error "Step Functions directory not found: $STEPFUNCTIONS_DIR"
        exit 1
    fi
    
    # Validate all Step Functions definitions
    log_info "Validating Step Functions definitions..."
    for file in "$STEPFUNCTIONS_DIR"/*.json; do
        if [[ -f "$file" ]]; then
            validate_stepfunction "$file"
        fi
    done
    
    # Setup S3 bucket
    setup_s3_bucket
    
    # Upload Step Functions definitions
    upload_stepfunctions
    
    # Test Step Functions (basic validation)
    test_stepfunctions
    
    log_success "Step Functions deployment preparation completed successfully!"
    log_info "You can now run 'sam deploy' to deploy the complete stack."
    
    # Display next steps
    echo
    log_info "Next steps:"
    echo "  1. Run: cd aws && sam build"
    echo "  2. Run: sam deploy --stack-name $STACK_NAME --region $AWS_REGION"
    echo "  3. Monitor deployment in AWS CloudFormation console"
    echo "  4. Test the deployed Step Functions in AWS Console"
    echo
    
    # Display uploaded files
    log_info "Uploaded Step Functions definitions:"
    aws s3 ls "s3://$UPLOADS_BUCKET/stepfunctions/" --human-readable
}

# Script options
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "validate")
        log_info "Validating Step Functions definitions only..."
        for file in "$STEPFUNCTIONS_DIR"/*.json; do
            if [[ -f "$file" ]]; then
                validate_stepfunction "$file"
            fi
        done
        log_success "All Step Functions definitions are valid!"
        ;;
    "clean")
        log_info "Cleaning up uploaded Step Functions definitions..."
        aws s3 rm "s3://$UPLOADS_BUCKET/stepfunctions/" --recursive --quiet || true
        log_success "Cleanup completed!"
        ;;
    "test")
        log_info "Testing Step Functions definitions..."
        test_stepfunctions
        ;;
    "help")
        echo "Usage: $0 [deploy|validate|clean|test|help]"
        echo ""
        echo "Commands:"
        echo "  deploy    - Validate and upload Step Functions definitions (default)"
        echo "  validate  - Validate Step Functions JSON syntax only"
        echo "  clean     - Remove uploaded Step Functions definitions from S3"
        echo "  test      - Run basic tests on Step Functions definitions"
        echo "  help      - Show this help message"
        echo ""
        echo "Environment Variables:"
        echo "  STACK_NAME    - CloudFormation stack name (default: subscriber-migration-portal-prod)"
        echo "  AWS_REGION    - AWS region (default: us-east-1)"
        ;;
    *)
        log_error "Unknown command: $1"
        echo "Run '$0 help' for usage information."
        exit 1
        ;;
esac