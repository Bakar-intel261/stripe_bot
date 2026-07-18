# 🤖 Telegram Donut Bot

Automated task bot using Donut Browser for anti-detection.

## Features
- ✅ Telegram commands
- ✅ Donut Browser integration
- ✅ 24-hour cooldown per user
- ✅ Auto-detects and bypasses fingerprinting
- ✅ Runs on GitHub Actions (free)

## Setup

### 1. Create Telegram Bot
- Message @BotFather on Telegram
- Send `/newbot` and follow instructions
- Copy your `BOT_TOKEN`

### 2. Configure GitHub Secrets
- Go to Settings → Secrets and variables → Actions
- Add secret: `BOT_TOKEN` = your bot token

### 3. Deploy
- Push to GitHub
- GitHub Actions will automatically deploy

## Commands
- `/start` - Welcome message
- `/start_task` - Begin automation
- `/stats` - View usage stats
- `/help` - Help message

## Testing
- Message your bot: `/start_task`
- Wait 30 seconds for response

## Notes
- 1 task per 24 hours per user
- Tasks complete in < 5 minutes
- Public repository = free GitHub Actions