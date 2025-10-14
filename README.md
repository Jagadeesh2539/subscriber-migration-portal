# Subscriber Migration Portal

This is a complete, production-ready full-stack application for managing and migrating subscriber data from a legacy system to a multi-region cloud environment. 

### Features

- **Subscriber Provisioning:** CRUD operations on subscriber data.
- **Intelligent Routing:** Automatically fetches data from either the cloud or the legacy system.
- **Dual Provisioning:** Ensures data consistency by updating both systems simultaneously.
- **Bulk Migration:** Upload a CSV to migrate thousands of subscribers asynchronously.
- **Multi-Region High Availability:** Deploys to two AWS regions with automatic failover.
- **Role-Based Access Control (RBAC):** Secure login with `admin`, `operator`, and `guest` roles.
- **Audit Logging:** Records every action for compliance and troubleshooting.
- **CI/CD:** Automated pipelines for Continuous Integration and Deployment using GitHub Actions.

## Getting Started

Follow the step-by-step guide to deploy this project to your AWS account.

### Prerequisites

- An AWS account with AdministratorAccess
- A registered domain in AWS Route 53
- GitHub Account
- Local tools: Git, AWS CLI, Node.js, Python, Docker

### Step 1: Deploy Infrastructure

1.  Run the `aws cloudformation deploy` command with your domain name.
2.  Wait for the stack to complete in the AWS console.

### Step 2: Set up GitHub Secrets

Add your AWS credentials and other details as secrets in your GitHub repository.

### Step 3: Trigger CI/CD

Make a change to the `main` branch to start the automated deployment.

### Step 4: Configure DNS

Create A records in Route 53 to point to the CloudFront distribution and the ALB.

### Step 5: Test the Application

- Login with test credentials: `admin/Admin@123`
- Use the UI to add a new subscriber.
- Upload the `sample-bulk-load.csv` to start a migration.
- Observe the audit logs and data in DynamoDB.

## Architecture

The architecture is a serverless-friendly, microservices-based design using:
- **Frontend:** React, S3, CloudFront
- **Backend:** Python (Flask), Docker, ECR, ECS (simulated), ALB, API Gateway
- **Database:** DynamoDB Global Tables
- **CI/CD:** GitHub Actions
- **Logging & Monitoring:** CloudWatch, DynamoDB AuditLog
