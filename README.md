# Chawd Bot

Chawd is an agentic engineer for [Sentient Trading](https://sentienttrading.ai) — a persistent Discord bot that connects teammates to Claude Code for autonomous code changes.

---
▁▃▅▇▒░ S E N T I E N T   T R A D I N G
##### Agentic Autonomous Trading Infrastructure by GabanVentures.
---

## What it does

Chawd listens for messages in Discord and processes them through Claude Code (`claude -p`), giving it full access to the trading strategy codebase. When Senti (the analyst bot) posts a review with action items, Chawd can read the findings, modify strategy code, and deploy changes — all without a human opening a terminal.

```
Discord message → discord.py listener → claude -p (Claude Code CLI) → response back to Discord
                                              │
                                              ├── reads/edits strategy code
                                              ├── runs shell commands
                                              └── deploys to AMS server
```

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file with your Discord bot token:
   ```bash
   cp .env.example .env
   # edit .env and add your token
   ```

3. Run:
   ```bash
   ./start.sh
   ```

Or use the shell alias (added to `.zshrc`):
```bash
chawd        # start the bot
chawd-stop   # stop it
```

## How it works

- Uses `discord.py` to listen for messages in allowed channels
- When mentioned or addressed, passes the message to `claude -p` (non-interactive Claude Code CLI)
- Claude processes the request using the Max plan (not API billing)
- Claude has full tool access: Bash, Read, Edit, Write, Grep, Glob
- Response is sent back to Discord through the bot

## Team workflow

| Role | Bot | Responsibility |
|------|-----|----------------|
| Analyst | **Senti** | Pulls DB data, reviews shadow/live results, writes review memos |
| Engineer | **Chawd** | Takes review findings, refactors strategy code, deploys |
