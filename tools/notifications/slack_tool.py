"""Slack notification tool binding for DevOps agents."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


def send_slack_message(channel: str, text: str) -> dict[str, Any]:
    """Send a message to a Slack channel using an incoming webhook.

    Args:
        channel: The target Slack channel (e.g. '#devops-alerts').
        text: The message content to send.

    Returns:
        A dict containing status and status code/message.
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")

    if not webhook_url:
        # Mock mode if no webhook URL is configured
        logger.info(
            "[MOCK SLACK] (No SLACK_WEBHOOK_URL set) Send to %s:\n%s",
            channel,
            text,
        )
        return {
            "status": "mocked",
            "channel": channel,
            "message": "SLACK_WEBHOOK_URL not configured. Message logged to console.",
        }

    payload = {
        "channel": channel,
        "text": text,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return {
            "status": "success",
            "channel": channel,
            "status_code": resp.status_code,
        }
    except requests.RequestException as exc:
        logger.error("Failed to send Slack message: %s", exc)
        return {"status": "error", "error": str(exc)}
