#!/bin/bash

# NEXUS API Keys Setup Script
# Interactive guide for getting all API keys

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        NEXUS API Keys & Configuration Setup           ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"

ENV_FILE=".env"

# Create .env if doesn't exist
if [ ! -f "$ENV_FILE" ]; then
    cp backend/.env.example "$ENV_FILE"
    echo -e "${GREEN}✓ Created $ENV_FILE${NC}"
fi

echo -e "\n${YELLOW}Get your API keys (all free tier available):${NC}\n"

# Telegram
echo -e "${YELLOW}1. Telegram Bot (for alerts)${NC}"
echo "   a) Message @BotFather on Telegram"
echo "   b) Send: /newbot"
echo "   c) Follow prompts → receive bot token"
echo ""
read -p "Enter TELEGRAM_BOT_TOKEN: " TG_TOKEN
read -p "Enter TELEGRAM_CHAT_ID (your Telegram ID): " TG_CHAT_ID

# NewsAPI
echo -e "\n${YELLOW}2. NewsAPI (optional, for sentiment)${NC}"
echo "   a) Visit https://newsapi.org"
echo "   b) Sign up (free tier available)"
echo "   c) Copy API key from dashboard"
echo ""
read -p "Enter NEWS_API_KEY (or press Enter to skip): " NEWS_KEY

# Financial Modeling Prep
echo -e "\n${YELLOW}3. Financial Modeling Prep (optional)${NC}"
echo "   a) Visit https://financialmodelingprep.com"
echo "   b) Sign up for free API access"
echo "   c) Copy API key"
echo ""
read -p "Enter FMP_API_KEY (or press Enter to skip): " FMP_KEY

# FRED (St. Louis Fed)
echo -e "\n${YELLOW}4. FRED (Federal Reserve data - optional)${NC}"
echo "   a) Visit https://fred.stlouisfed.org/docs/api"
echo "   b) Register and get free API key"
echo ""
read -p "Enter FRED_API_KEY (or press Enter to skip): " FRED_KEY

# Twilio WhatsApp
echo -e "\n${YELLOW}5. Twilio WhatsApp (optional, for WhatsApp alerts)${NC}"
echo "   a) Visit https://www.twilio.com"
echo "   b) Sign up → get Account SID and Auth Token"
echo "   c) Verify WhatsApp number"
echo ""
read -p "Enter TWILIO_ACCOUNT_SID (or press Enter to skip): " TWILIO_SID
read -p "Enter TWILIO_AUTH_TOKEN (or press Enter to skip): " TWILIO_TOKEN
read -p "Enter TWILIO_WHATSAPP_FROM number (or press Enter to skip): " TWILIO_FROM
read -p "Enter WHATSAPP_TO (your WhatsApp number): " WA_TO

# Cloudflare
echo -e "\n${YELLOW}6. Cloudflare (for edge caching)${NC}"
echo "   a) Visit https://dash.cloudflare.com"
echo "   b) Copy Account ID from domain settings"
echo "   c) Generate API token"
echo ""
read -p "Enter CF_ACCOUNT_ID: " CF_ACCOUNT_ID
read -p "Enter CF_API_TOKEN: " CF_TOKEN

# Update .env
echo -e "\n${YELLOW}Updating $ENV_FILE...${NC}"

sed -i.bak "s/TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$TG_TOKEN/" "$ENV_FILE"
sed -i.bak "s/TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=$TG_CHAT_ID/" "$ENV_FILE"
sed -i.bak "s/NEWS_API_KEY=.*/NEWS_API_KEY=$NEWS_KEY/" "$ENV_FILE"
sed -i.bak "s/FMP_API_KEY=.*/FMP_API_KEY=$FMP_KEY/" "$ENV_FILE"
sed -i.bak "s/FRED_API_KEY=.*/FRED_API_KEY=$FRED_KEY/" "$ENV_FILE"
sed -i.bak "s/TWILIO_ACCOUNT_SID=.*/TWILIO_ACCOUNT_SID=$TWILIO_SID/" "$ENV_FILE"
sed -i.bak "s/TWILIO_AUTH_TOKEN=.*/TWILIO_AUTH_TOKEN=$TWILIO_TOKEN/" "$ENV_FILE"
sed -i.bak "s/TWILIO_WHATSAPP_FROM=.*/TWILIO_WHATSAPP_FROM=$TWILIO_FROM/" "$ENV_FILE"
sed -i.bak "s/WHATSAPP_TO=.*/WHATSAPP_TO=$WA_TO/" "$ENV_FILE"
sed -i.bak "s/CF_ACCOUNT_ID=.*/CF_ACCOUNT_ID=$CF_ACCOUNT_ID/" "$ENV_FILE"
sed -i.bak "s/CF_API_TOKEN=.*/CF_API_TOKEN=$CF_TOKEN/" "$ENV_FILE"

rm "$ENV_FILE.bak"

echo -e "${GREEN}✓ Configuration saved to $ENV_FILE${NC}"

# Verify
echo -e "\n${YELLOW}Verifying setup...${NC}"

python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()

required = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
optional = ['NEWS_API_KEY', 'FMP_API_KEY', 'FRED_API_KEY', 'CF_ACCOUNT_ID']

print('\nRequired:')
for key in required:
    val = os.getenv(key, '')
    status = '✓' if val else '✗'
    print(f'  {status} {key}')

print('\nOptional:')
for key in optional:
    val = os.getenv(key, '')
    status = '✓' if val else '○'
    print(f'  {status} {key}')
" || echo "Python not available for verification"

echo -e "\n${GREEN}✓ Setup complete!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Test Telegram: python backend/alerts/telegram_bot.py"
echo "2. Start API: python backend/main.py"
echo "3. Run scheduler: python backend/scheduler_runner.py"
echo ""
echo "Never commit .env to Git! It's in .gitignore."
