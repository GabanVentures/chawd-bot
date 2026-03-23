#!/usr/bin/env python3
"""
Chawd — persistent Discord bot wrapper for Claude Code.

Listens for Discord messages, passes them to `claude -p` (Claude Code CLI),
and sends the response back to Discord. Uses the Max plan, not Console API.
"""

import asyncio
import json
import logging
import subprocess
import sys

import discord

from config import (
    ALLOWED_CHANNEL_IDS,
    CLAUDE_CLI_PATH,
    CLAUDE_MODEL,
    CLAUDE_TIMEOUT,
    DISCORD_BOT_TOKEN,
    MAX_BUDGET_USD,
    SYSTEM_PROMPT,
    WORKING_DIRECTORY,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("chawd")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Semaphore to serialize claude -p calls (one at a time)
claude_lock = asyncio.Semaphore(1)


def call_claude(prompt: str) -> str:
    """Invoke claude -p and return the text response."""
    cmd = [
        CLAUDE_CLI_PATH,
        "-p", prompt,
        "--output-format", "json",
        "--model", CLAUDE_MODEL,
        "--append-system-prompt", SYSTEM_PROMPT,
        "--allowedTools", "Bash,Read,Edit,Write,Grep,Glob",
        "--max-budget-usd", str(MAX_BUDGET_USD),
        "--no-session-persistence",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=CLAUDE_TIMEOUT,
        cwd=WORKING_DIRECTORY,
    )

    if result.returncode != 0:
        log.error("claude -p failed: %s", result.stderr[:500])
        return f"Sorry, I hit an error processing that request."

    # Parse JSON output to extract the response text
    try:
        data = json.loads(result.stdout)
        # claude -p --output-format json returns {"result": "...", ...}
        if isinstance(data, dict):
            return data.get("result", "") or data.get("text", "") or str(data)
        return str(data)
    except json.JSONDecodeError:
        # Fallback: return raw stdout if not valid JSON
        return result.stdout.strip()


async def process_message(message: discord.Message):
    """Process an incoming Discord message through Claude."""
    prompt = (
        f"Discord message from {message.author.name} "
        f"in channel #{message.channel.name} (ID: {message.channel.id}):\n\n"
        f"{message.content}"
    )

    # Handle attachments
    if message.attachments:
        attachment_info = ", ".join(
            f"{a.filename} ({a.content_type}, {a.size} bytes)"
            for a in message.attachments
        )
        prompt += f"\n\nAttachments: {attachment_info}"

    log.info("Processing message from %s: %s", message.author.name, message.content[:100])

    async with claude_lock:
        # Run claude -p in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(None, call_claude, prompt)
        except subprocess.TimeoutExpired:
            response = "That request timed out. Try breaking it into smaller pieces."
        except Exception as e:
            log.exception("Error calling claude")
            response = f"Something went wrong: {type(e).__name__}"

    if not response:
        return

    # Discord message limit is 2000 chars — chunk if needed
    for i in range(0, len(response), 1900):
        chunk = response[i:i + 1900]
        await message.channel.send(chunk)


@client.event
async def on_ready():
    log.info("Chawd is online as %s (ID: %s)", client.user.name, client.user.id)
    log.info("Watching channels: %s", ALLOWED_CHANNEL_IDS)


@client.event
async def on_message(message: discord.Message):
    # Ignore own messages
    if message.author == client.user:
        return

    # Only respond in allowed channels
    if message.channel.id not in ALLOWED_CHANNEL_IDS:
        return

    # Only respond when mentioned or when message mentions the bot's role
    bot_mentioned = client.user in message.mentions if client.user else False
    # Also respond if the message contains @Chawd or references the bot role
    text_mention = "chawd" in message.content.lower()

    if not bot_mentioned and not text_mention:
        return

    async with message.channel.typing():
        await process_message(message)


if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        log.error("DISCORD_BOT_TOKEN environment variable is not set")
        sys.exit(1)
    client.run(DISCORD_BOT_TOKEN, log_handler=None)
