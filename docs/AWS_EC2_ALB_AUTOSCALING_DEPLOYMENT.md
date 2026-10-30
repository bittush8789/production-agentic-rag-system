# AWS EC2 Production Deployment with Application Load Balancer & Auto Scaling
## Complete Windows PowerShell & AWS CLI Deployment Guide

This guide details how to deploy the **Enterprise IT Support Agentic RAG Copilot** container onto AWS using **Amazon EC2**, an **Application Load Balancer (ALB)**, and an **Auto Scaling Group (ASG)** using Windows PowerShell and the AWS CLI.

---

## Architecture Overview

```text
                               Internet / Corporate Users
                                           │
                                           ▼ (Port 80 / 443)
                        ┌──────────────────────────────────────┐
                        │   Application Load Balancer (ALB)    │
                        │ - Public DNS Endpoint                │
                        │ - Healthcheck to /api/health         │
                        └──────────────────┬───────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼ (Traffic forwarded to Port 8080)    ▼
            ┌──────────────────────┐              ┌──────────────────────┐
            │ EC2 Instance 1 (AZ-A)│              │ EC2 Instance 2 (AZ-B)│
            │ Docker Container     │              │ Docker Container     │
            │ Port 8080            │              │ Port 8080            │
            └──────────────────────┘              └──────────────────────┘
                        ▲                                     ▲
                        └──────────────────┬──────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        │     Auto Scaling Group (ASG)        │
                        │ - Min: 2, Desired: 2, Max: 4        │
                        │ - Target Tracking CPU (60%)         │
                        │ - ELB Healthcheck Monitoring        │
                        └─────────────────────────────────────┘
```

---

## Step 0: Prerequisites on Windows

### 1. Install AWS CLI v2 (Run in PowerShell as Administrator)
```powershell
winget install Amazon.AWSCLI
# Or download the MSI installer from:
# https://awscli.amazonaws.com/AWSCLIV2.msi
```
Restart PowerShell and verify:
```powershell
aws --version
```

### 2. Configure AWS Credentials
```powershell
aws configure
# Enter AWS Access Key ID, Secret Access Key, Default region (e.g. us-east-1), format (json)
```

---

## Step 1: Set Variables in PowerShell

Open PowerShell and define your deployment variables:

```powershell
$AWS_REGION     = "us-east-1"
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --query "Account" --output text)
$APP_NAME       = "it-copilot"
$ECR_REPO_NAME  = "enterprise-it-copilot"
$IMAGE_TAG      = "latest"
$ECR_URI        = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

Write-Host "Deploying for Account: $AWS_ACCOUNT_ID in Region: $AWS_REGION"
```

---

## Step 2: Push Docker Image to Amazon ECR

### 1. Create ECR Repository
```powershell
aws ecr create-repository `
  --repository-name $ECR_REPO_NAME `
  --region $AWS_REGION `
  --image-scanning-configuration scanOnPush=true
```

### 2. Authenticate Docker with ECR
```powershell
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI
```

### 3. Build, Tag, and Push the Docker Container
```powershell
# Build local container
docker build -t $ECR_REPO_NAME .

# Tag for Amazon ECR
docker tag ${ECR_REPO_NAME}:latest "${ECR_URI}/${ECR_REPO_NAME}:${IMAGE_TAG}"

# Push to Amazon ECR
docker push "${ECR_URI}/${ECR_REPO_NAME}:${IMAGE_TAG}"
```

---

## Step 3: Fetch Default VPC and Subnets

High availability requires subnets in at least two different Availability Zones:

```powershell
# Get Default VPC ID
$VPC_ID = (aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region $AWS_REGION)

# Get 2 Public Subnets in different Availability Zones
$SUBNET_IDS = (aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[0:2].SubnetId" --output text --region $AWS_REGION) -split "`t"
$SUBNET_1 = $SUBNET_IDS[0]
$SUBNET_2 = $SUBNET_IDS[1]

Write-Host "VPC: $VPC_ID"
Write-Host "Subnet 1: $SUBNET_1 | Subnet 2: $SUBNET_2"
```

---

## Step 4: Create Security Groups

### 1. ALB Security Group (Allows Inbound Port 80 from Internet)
```powershell
$ALB_SG_ID = (aws ec2 create-security-group `
  --group-name "${APP_NAME}-alb-sg" `
  --description "Security Group for IT Copilot ALB" `
  --vpc-id $VPC_ID `
  --query "GroupId" --output text --region $AWS_REGION)

# Allow HTTP Port 80 inbound
aws ec2 authorize-security-group-ingress `
  --group-id $ALB_SG_ID `
  --protocol tcp `
  --port 80 `
  --cidr 0.0.0.0/0 `
  --region $AWS_REGION
```

### 2. EC2 Security Group (Allows Port 8080 ONLY from ALB SG)
```powershell
$EC2_SG_ID = (aws ec2 create-security-group `
  --group-name "${APP_NAME}-ec2-sg" `
  --description "Security Group for IT Copilot EC2 Instances" `
  --vpc-id $VPC_ID `
  --query "GroupId" --output text --region $AWS_REGION)

# Allow Port 8080 restricted to ALB Security Group
aws ec2 authorize-security-group-ingress `
  --group-id $EC2_SG_ID `
  --protocol tcp `
  --port 8080 `
  --source-group $ALB_SG_ID `
  --region $AWS_REGION
```

---

## Step 5: IAM Role for EC2 Instances (ECR Pull Permissions)

EC2 instances require IAM authorization to pull images from your private Amazon ECR repository:

```powershell
# 1. Create Trust Policy
@"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
"@ | Out-File -FilePath "$env:TEMP\ec2-trust-policy.json" -Encoding ascii

# 2. Create IAM Role and attach ECR read-only policy
aws iam create-role `
  --role-name "${APP_NAME}-ec2-role" `
  --assume-role-policy-document "file://$env:TEMP\ec2-trust-policy.json"

aws iam attach-role-policy `
  --role-name "${APP_NAME}-ec2-role" `
  --policy-arn "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"

# 3. Create Instance Profile & Attach Role
aws iam create-instance-profile --instance-profile-name "${APP_NAME}-instance-profile"

aws iam add-role-to-instance-profile `
  --instance-profile-name "${APP_NAME}-instance-profile" `
  --role-name "${APP_NAME}-ec2-role"

# Wait 10 seconds for IAM propagation
Start-Sleep -Seconds 10
```

---

## Step 6: Create Application Load Balancer & Target Group

### 1. Create Target Group
```powershell
$TARGET_GROUP_ARN = (aws elbv2 create-target-group `
  --name "${APP_NAME}-tg" `
  --protocol HTTP `
  --port 8080 `
  --vpc-id $VPC_ID `
  --target-type instance `
  --health-check-protocol HTTP `
  --health-check-path "/api/health" `
  --health-check-interval-seconds 15 `
  --health-check-timeout-seconds 5 `
  --healthy-threshold-count 2 `
  --unhealthy-threshold-count 3 `
  --query "TargetGroups[0].TargetGroupArn" --output text --region $AWS_REGION)

Write-Host "Target Group Created: $TARGET_GROUP_ARN"
```

### 2. Create Application Load Balancer (ALB)
```powershell
$ALB_ARN = (aws elbv2 create-load-balancer `
  --name "${APP_NAME}-alb" `
  --subnets $SUBNET_1 $SUBNET_2 `
  --security-groups $ALB_SG_ID `
  --scheme internet-facing `
  --type application `
  --query "LoadBalancers[0].LoadBalancerArn" --output text --region $AWS_REGION)

$ALB_DNS = (aws elbv2 describe-load-balancers `
  --load-balancer-arns $ALB_ARN `
  --query "LoadBalancers[0].DNSName" --output text --region $AWS_REGION)

Write-Host "ALB Created! DNS: http://$ALB_DNS"
```

### 3. Create HTTP Listener on Port 80
```powershell
aws elbv2 create-listener `
  --load-balancer-arn $ALB_ARN `
  --protocol HTTP `
  --port 80 `
  --default-actions Type=forward,TargetGroupArn=$TARGET_GROUP_ARN `
  --region $AWS_REGION
```

---

## Step 7: Create EC2 Launch Template with User Data

The User Data script initializes the EC2 instance, installs Docker, authenticates to Amazon ECR using instance role credentials, and starts the container:

```powershell
# 1. Prepare User Data Script
$UserDataScript = @"
#!/bin/bash
dnf update -y
dnf install -y docker
systemctl start docker
systemctl enable docker

# Log in to ECR using instance role
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin ${ECR_URI}

# Run Enterprise IT Support Copilot Container
docker run -d `
  -p 8080:8080 `
  --restart always `
  --name it-copilot `
  -e APP_ENV=production `
  -e ADMIN_API_KEY=change-me-in-production `
  ${ECR_URI}/${ECR_REPO_NAME}:${IMAGE_TAG}
"@

# Base64 encode User Data in PowerShell
$UserDataBase64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($UserDataScript))

# 2. Get Latest Amazon Linux 2023 AMI
$AMI_ID = (aws ec2 describe-images `
  --owners amazon `
  --filters "Name=name,Values=al2023-ami-2023.*-x86_64" "Name=state,Values=available" `
  --query "reverse(sort_by(Images, &CreationDate))[0].ImageId" `
  --output text --region $AWS_REGION)

Write-Host "Using AMI: $AMI_ID"

# 3. Create Launch Template JSON Config
@"
{
  "ImageId": "$AMI_ID",
  "InstanceType": "t3.medium",
  "SecurityGroupIds": ["$EC2_SG_ID"],
  "IamInstanceProfile": { "Name": "${APP_NAME}-instance-profile" },
  "UserData": "$UserDataBase64"
}
"@ | Out-File -FilePath "$env:TEMP\launch-template.json" -Encoding ascii

# 4. Create Launch Template in AWS
aws ec2 create-launch-template `
  --launch-template-name "${APP_NAME}-lt" `
  --version-description "v1-production" `
  --launch-template-data "file://$env:TEMP\launch-template.json" `
  --region $AWS_REGION
```

---

## Step 8: Create Auto Scaling Group (ASG)

Deploy minimum 2, maximum 4 EC2 instances spanning multiple Availability Zones:

```powershell
aws autoscaling create-auto-scaling-group `
  --auto-scaling-group-name "${APP_NAME}-asg" `
  --launch-template "LaunchTemplateName=${APP_NAME}-lt,Version=`$Latest" `
  --min-size 2 `
  --max-size 4 `
  --desired-capacity 2 `
  --target-group-arns $TARGET_GROUP_ARN `
  --vpc-zone-identifier "$SUBNET_1,$SUBNET_2" `
  --health-check-type ELB `
  --health-check-grace-period 180 `
  --region $AWS_REGION
```

### Configure Target Tracking Scaling Policy (Average CPU 60%)
```powershell
@"
{
  "TargetValue": 60.0,
  "PredefinedMetricSpecification": {
    "PredefinedMetricType": "ASGAverageCPUUtilization"
  }
}
"@ | Out-File -FilePath "$env:TEMP\scaling-policy.json" -Encoding ascii

aws autoscaling put-scaling-policy `
  --auto-scaling-group-name "${APP_NAME}-asg" `
  --policy-name "${APP_NAME}-cpu-target-tracking" `
  --policy-type TargetTrackingScaling `
  --target-tracking-configuration "file://$env:TEMP\scaling-policy.json" `
  --region $AWS_REGION
```

---

## Step 9: Verify Deployment & Health

Wait 1 to 2 minutes for EC2 instances to launch and pass health checks:

```powershell
# 1. Check Target Group Health (State should become 'healthy')
aws elbv2 describe-target-health `
  --target-group-arn $TARGET_GROUP_ARN `
  --query "TargetHealthDescriptions[*].[Target.Id, TargetHealth.State]" `
  --output table `
  --region $AWS_REGION

# 2. Open Application in Web Browser
Start-Process "http://$ALB_DNS"

# 3. Verify Health Endpoint via PowerShell
Invoke-RestMethod -Uri "http://$ALB_DNS/api/health"
```

Expected JSON Response:
```json
{
  "status": "ok",
  "service": "Enterprise IT Support Agentic RAG Copilot",
  "environment": "production",
  "features": {
    "hybrid_rag": true,
    "presidio_guardrails": true,
    "nemo_guardrails": true,
    "keycloak_enabled": false,
    "dev_auth_bypass": true
  }
}
```

---

## Step 10: Clean-Up (Tear Down Resources)

To avoid incurring cloud charges after testing is finished:

```powershell
# 1. Delete Auto Scaling Group
aws autoscaling delete-auto-scaling-group --auto-scaling-group-name "${APP_NAME}-asg" --force-delete --region $AWS_REGION

# 2. Delete Load Balancer & Target Group
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN --region $AWS_REGION
Start-Sleep -Seconds 15
aws elbv2 delete-target-group --target-group-arn $TARGET_GROUP_ARN --region $AWS_REGION

# 3. Delete Launch Template
aws ec2 delete-launch-template --launch-template-name "${APP_NAME}-lt" --region $AWS_REGION

# 4. Delete Security Groups
Start-Sleep -Seconds 30
aws ec2 delete-security-group --group-id $EC2_SG_ID --region $AWS_REGION
aws ec2 delete-security-group --group-id $ALB_SG_ID --region $AWS_REGION

# 5. Delete IAM Profile & Role
aws iam remove-role-from-instance-profile --instance-profile-name "${APP_NAME}-instance-profile" --role-name "${APP_NAME}-ec2-role"
aws iam delete-instance-profile --instance-profile-name "${APP_NAME}-instance-profile"
aws iam detach-role-policy --role-name "${APP_NAME}-ec2-role" --policy-arn "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
aws iam delete-role --role-name "${APP_NAME}-ec2-role"

# 6. Delete ECR Repository
aws ecr delete-repository --repository-name $ECR_REPO_NAME --force --region $AWS_REGION
```
