"""
X (Twitter) integration for Chawd.

Supports:
  - post_tweet(text)  — public tweet from @Chawd_bot
  - send_dm(text)     — private DM to Leon on X
  - is_configured()   — check if credentials are present

Credentials loaded from env:
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
  X_LEON_USER_ID  — Leon's X numeric user ID (for DMs)
"""

import logging
import os

log = logging.getLogger("chawd.twitter")

try:
    import tweepy
    _TWEEPY_AVAILABLE = True
except ImportError:
    _TWEEPY_AVAILABLE = False
    log.warning("tweepy not installed — X integration disabled. Run: pip install tweepy")


def _client() -> "tweepy.Client":
    return tweepy.Client(
        consumer_key=os.getenv("X_API_KEY"),
        consumer_secret=os.getenv("X_API_SECRET"),
        access_token=os.getenv("X_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
        wait_on_rate_limit=False,
    )


def is_configured() -> bool:
    """Return True if all required X credentials are set."""
    return _TWEEPY_AVAILABLE and all([
        os.getenv("X_API_KEY"),
        os.getenv("X_API_SECRET"),
        os.getenv("X_ACCESS_TOKEN"),
        os.getenv("X_ACCESS_TOKEN_SECRET"),
    ])


def post_tweet(text: str) -> str:
    """
    Post a public tweet from @Chawd_bot.
    Returns the tweet URL on success, or an error string on failure.
    Truncates to 280 chars automatically.
    """
    if not is_configured():
        return "X not configured — set X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET"

    text = text[:280]
    try:
        client = _client()
        response = client.create_tweet(text=text)
        tweet_id = response.data["id"]
        url = f"https://x.com/Chawd_bot/status/{tweet_id}"
        log.info("Tweet posted: %s", url)
        return url
    except Exception as e:
        log.error("Tweet failed: %s", e)
        return f"X post failed: {e}"


def send_dm(text: str, user_id: str = None) -> str:
    """
    Send a DM to Leon on X.
    user_id defaults to X_LEON_USER_ID env var.

    Note: Requires the X app to have 'Direct Messages' read+write permission.
    """
    if not is_configured():
        return "X not configured"

    recipient = user_id or os.getenv("X_LEON_USER_ID", "")
    if not recipient:
        return "X DM failed: X_LEON_USER_ID not set in .env"

    try:
        client = _client()
        client.create_direct_message(participant_id=str(recipient), text=text[:10000])
        log.info("DM sent to X user %s", recipient)
        return f"DM sent to Leon on X"
    except Exception as e:
        log.error("DM failed: %s", e)
        return f"X DM failed: {e}"
