#!/usr/bin/env python3
"""
Chawd — persistent Discord bot for Sentient Trading.

Listens for Discord messages, passes them to the Anthropic API,
and sends the response back to Discord.
"""

import asyncio
import logging
import re
import sys

import anthropic
import discord

from config import (
    ALLOWED_CHANNEL_IDS,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_TIMEOUT,
    DISCORD_BOT_TOKEN,
    SYSTEM_PROMPT,
)
from twitter import is_configured as x_configured, post_tweet, send_dm

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


_NARRATION_PREFIXES = (
    "replied in discord",
    "done —",
    "done—",
    "memory updated",
    "updated memory",
    "saved memory",
    "feedback memory",
    "i've replied",
    "i've sent",
    "i've updated",
    "i've saved",
)


def strip_narration(text: str) -> str:
    """Remove internal Claude narration lines that should never reach Discord."""
    lines = text.splitlines()
    kept = []
    for line in lines:
        low = line.strip().lower()
        if any(low.startswith(prefix) for prefix in _NARRATION_PREFIXES):
            continue
        kept.append(line)
    # Strip trailing blank lines that may be left after removing narration
    return "\n".join(kept).rstrip()


def call_claude(prompt: str) -> str:
    """Call Claude via the Anthropic SDK and return the text response."""
    if not ANTHROPIC_API_KEY:
        return "ANTHROPIC_API_KEY is not set — ask Leon to add it to .env"

    sdk = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = sdk.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def extract_x_actions(text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Extract [TWEET: ...] and [DM: ...] markers from Claude's response.
    Returns (cleaned_text, [(action_type, content), ...]).
    action_type is 'tweet' or 'dm'.
    """
    actions = []

    def replace_marker(m):
        kind = m.group(1).lower()   # 'tweet' or 'dm'
        content = m.group(2).strip()
        actions.append((kind, content))
        return ""  # Remove marker from Discord text

    cleaned = re.sub(
        r'\[(TWEET|DM):\s*(.*?)\]',
        replace_marker,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return cleaned.strip(), actions


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
        except anthropic.APITimeoutError:
            response = "That request timed out. Try breaking it into smaller pieces."
        except Exception as e:
            log.exception("Error calling claude")
            response = f"Something went wrong: {type(e).__name__}"

    response = strip_narration(response)

    if not response:
        return

    # Extract any [TWEET: ...] or [DM: ...] markers before sending to Discord
    discord_text, x_actions = extract_x_actions(response)

    # Execute X actions
    if x_actions and x_configured():
        for action_type, content in x_actions:
            if action_type == "tweet":
                url = await asyncio.get_event_loop().run_in_executor(None, post_tweet, content)
                log.info("Tweet result: %s", url)
                discord_text += f"\n📣 Tweeted: {url}"
            elif action_type == "dm":
                result = await asyncio.get_event_loop().run_in_executor(None, send_dm, content)
                log.info("DM result: %s", result)
                discord_text += f"\n💬 {result}"

    if not discord_text:
        return

    # Discord message limit is 2000 chars — chunk if needed
    for i in range(0, len(discord_text), 1900):
        chunk = discord_text[i:i + 1900]
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
