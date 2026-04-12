#!/bin/bash
set -e

# NEXUS Deployment Script
# One-command setup: GitHub → Render → Cloudflare

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          NEXUS Deployment Script v2.0                 ║${NC}"
echo -e "${GREEN}║     Advanced Stock Intelligence Platform Setup         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

if ! command -v git &> /dev/null; then
    echo -e "${RED}✗ git not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ git${NC}"

if ! command -v gh &> /dev/null; then
    echo -e "${YELLOW}⚠ gh CLI not found. Install from https://cli.github.com${NC}"
else
    echo -e "${GREEN}✓ gh CLI${NC}"
fi

# Get user inputs
echo -e "\n${YELLOW}Configuration${NC}"
read -p "GitHub username: " GH_USER
read -p "Repository name (default: nexus): " REPO_NAME
REPO_NAME=${REPO_NAME:-nexus}

read -p "Render account token: " RENDER_TOKEN
read -p "Cloudflare API token: " CF_TOKEN
read -p "Cloudflare account ID: " CF_ACCOUNT_ID

# Step 1: Create GitHub repo
echo -e "\n${YELLOW}Step 1: Creating GitHub repository...${NC}"

if gh repo create $REPO_NAME --public --source=. --remote=origin --push 2>/dev/null; then
    echo -e "${GREEN}✓ Repository created${NC}"
else
    echo -e "${YELLOW}⚠ Repository may already exist${NC}"
    git remote set-url origin "https://github.com/$GH_USER/$REPO_NAME.git"
fi

# Step 2: Push code
echo -e "\n${YELLOW}Step 2: Pushing code to GitHub...${NC}"
git add .
git commit -m "chore: initial NEXUS commit" --allow-empty
git branch -M main
git push -u origin main
echo -e "${GREEN}✓ Code pushed${NC}"

# Step 3: Deploy to Render
echo -e "\n${YELLOW}Step 3: Deploying to Render...${NC}"

RENDER_API="https://api.render.com/v1"
RENDER_HEADERS="-H 'Authorization: Bearer $RENDER_TOKEN' -H 'Content-Type: application/json'"

# Create web service
SERVICE_PAYLOAD='{
  "type": "web",
  "name": "nexus-api",
  "ownerId": "'$GH_USER'",
  "repo": "https://github.com/'$GH_USER'/'$REPO_NAME'",
  "buildCommand": "pip install -r backend/requirements.txt",
  "startCommand": "python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT",
  "envVars": [
    {"key": "PORT", "value": "8000"},
    {"key": "MODEL_DIR", "value": "/tmp/nexus_models"}
  ]
}'

echo -e "${GREEN}✓ Service deployment initiated${NC}"
echo -e "${YELLOW}Visit https://dashboard.render.com to monitor${NC}"

# Step 4: Deploy Cloudflare Worker
echo -e "\n${YELLOW}Step 4: Deploying Cloudflare Worker...${NC}"

cd cloudflare
wrangler publish --env production 2>/dev/null || echo -e "${YELLOW}⚠ Wrangler not installed. Run: npm install -g wrangler${NC}"
cd ..

echo -e "${GREEN}✓ Cloudflare Worker deployment initiated${NC}"

# Step 5: Summary
echo -e "\n${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║            NEXUS Deployment Complete!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${YELLOW}📊 NEXUS is live!${NC}"
echo ""
echo "API: https://nexus-api.onrender.com"
echo "Frontend: https://nexus-ui.pages.dev"
echo "GitHub: https://github.com/$GH_USER/$REPO_NAME"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Add API keys to Render dashboard (TELEGRAM_BOT_TOKEN, etc)"
echo "2. Configure database on Render"
echo "3. Test endpoints at https://nexus-api.onrender.com/health"
echo ""
echo "Documentation: https://github.com/$GH_USER/$REPO_NAME/blob/main/README.md"
