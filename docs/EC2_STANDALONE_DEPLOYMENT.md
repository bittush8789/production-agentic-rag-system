# Standalone Single EC2 Instance Deployment Guide
## Enterprise IT Support Agentic RAG Copilot

A simplified, step-by-step guide to deploy this application on a **single Amazon EC2 instance** without the complexity of Load Balancers or Auto Scaling.

---

## 1. Instance Sizing & Prerequisites

| Specification | Recommended Configuration |
|---|---|
| **Instance Type** | `t3.medium` (2 vCPU, 4 GB RAM) or `t3.large` |
| **Operating System** | Ubuntu 22.04 LTS or 24.04 LTS (or Amazon Linux 2023) |
| **Storage (EBS)** | 20 GB gp3 root volume |
| **Inbound Ports** | Port `22` (SSH), Port `8080` (Application), Port `80` (HTTP) |

---

## 2. Step-by-Step Deployment (AWS CLI or Console)

### Step 1: Launch EC2 Instance via AWS CLI (PowerShell / Terminal)

```powershell
# 1. Create Security Group
$SG_ID = (aws ec2 create-security-group `
  --group-name "it-copilot-single-sg" `
  --description "Security group for standalone IT Copilot EC2" `
  --query "GroupId" --output text)

# 2. Allow SSH (Port 22) and Application HTTP (Port 8080 & Port 80)
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 22 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 8080 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 80 --cidr 0.0.0.0/0

# 3. Launch t3.medium Ubuntu Instance
$INSTANCE_ID = (aws ec2 run-instances `
  --image-id ami-04b70fa74e45c3917 `
  --instance-type t3.medium `
  --key-name "your-ec2-keypair" `
  --security-group-ids $SG_ID `
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' `
  --query "Instances[0].InstanceId" --output text)

Write-Host "EC2 Instance Launched: $INSTANCE_ID"
```

*(If using the AWS Management Console: Navigate to **EC2 Dashboard -> Launch Instance -> Select Ubuntu 24.04 -> Instance Type t3.medium -> In Security Group open Port 22, Port 80, and Port 8080**).*

---

### Step 2: Connect to Your EC2 Instance

```bash
# Connect using SSH
ssh -i "your-key.pem" ubuntu@<YOUR-EC2-PUBLIC-IP>
```
*(Alternatively, use **EC2 Instance Connect** directly from the AWS Console).*

---

### Step 3: Install Docker on EC2

Execute the following commands in the EC2 terminal:

```bash
# Update system packages
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker and Git
sudo apt-get install -y docker.io git

# Add the current user to the docker group
sudo usermod -aG docker $USER
newgrp docker

# Start and enable Docker service
sudo systemctl enable --now docker
docker --version
```

---

### Step 4: Application Setup (Choose Option A or Option B)

#### Option A: Clone Repository directly on EC2 & Run with Docker (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/Enterprise-IT-Support-Agentic-RAG-Copilot.git
cd Enterprise-IT-Support-Agentic-RAG-Copilot

# 2. Configure environment variables (.env file)
cat << 'EOF' > .env
APP_ENV=production
ADMIN_API_KEY=your-secure-admin-key
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=pckey-...
TAVILY_API_KEY=tvly-...
EOF

# 3. Build Docker Image
docker build -t it-copilot .

# 4. Run Docker Container
# Bind Port 80 to 8080 so users can access directly at http://<EC2-IP>/
docker run -d \
  --name it-copilot \
  --restart always \
  -p 80:8080 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/uploads:/app/uploads \
  it-copilot
```

---

#### Option B: Run without Docker (Direct Python / Systemd Service)

To run natively with Python and a Systemd daemon:

```bash
cd Enterprise-IT-Support-Agentic-RAG-Copilot

# Create and activate Python virtual environment
sudo apt-get install -y python3-pip python3-venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies and NLP models
pip install --upgrade pip
pip install -r requirements.txt
python3 -m spacy download en_core_web_sm

# Test run
python3 run.py
```

To configure automatic restart on server reboot using Systemd:

```bash
sudo cat << 'EOF' > /etc/systemd/system/it-copilot.service
[Unit]
Description=Enterprise IT Support Copilot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Enterprise-IT-Support-Agentic-RAG-Copilot
ExecStart=/home/ubuntu/Enterprise-IT-Support-Agentic-RAG-Copilot/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2
Restart=always
Environment=TRANSFORMERS_NO_TF=1
Environment=USE_TF=0

[Install]
WantedBy=multi-user.target
EOF

# Reload and enable the service
sudo systemctl daemon-reload
sudo systemctl enable --now it-copilot
sudo systemctl status it-copilot
```

---

### Step 5: Verify Deployment

1. Check application health locally on the EC2 instance:
   ```bash
   curl http://localhost:8080/api/health
   ```
2. Open your web browser:
   ```text
   http://<YOUR-EC2-PUBLIC-IP>:8080
   ```
   *(Or `http://<YOUR-EC2-PUBLIC-IP>` if port 80 mapping was used).*

3. OpenAPI / Swagger documentation:
   ```text
   http://<YOUR-EC2-PUBLIC-IP>:8080/docs
   ```

---

### Step 6: Operational Maintenance Commands

```bash
# View live container logs
docker logs -f it-copilot

# Restart container
docker restart it-copilot

# Stop container
docker stop it-copilot

# Check running status
docker ps
```
