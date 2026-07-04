"""
notify.py — send an alert to Discord (with a console fallback).

If DISCORD_WEBHOOK_URL is set in .env, this posts a nicely-formatted message to
your Discord channel. If it's NOT set, it just prints to the terminal, so you
can test the whole pipeline before wiring Discord up.
"""

import json
import os
import urllib.request
from datetime import datetime

from broker.config import get


def log_alert(symbol, sig, replay=False):
    """Append an alert to state/alerts.jsonl — the record we compute Adam's
    real setup statistics from. Replay-generated alerts are flagged so they
    never pollute the live stats."""
    path = os.path.join(os.path.dirname(__file__), "state", "alerts.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "symbol": symbol,
        "side": sig.get("side"),
        "reason": sig.get("reason"),
        "price": sig.get("price"),
        "levels": sig.get("levels"),
    }
    if replay:
        entry["replay"] = True
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def send(title: str, lines, url_hint: str | None = None):
    """Send an alert. `lines` is a list of 'label: value' strings."""
    webhook = get("DISCORD_WEBHOOK_URL")
    body = "\n".join(lines)

    if not webhook:
        print("\n" + "=" * 44)
        print(f"🔔 (dry-run, no Discord webhook set)  {title}")
        print("-" * 44)
        print(body)
        if url_hint:
            print(url_hint)
        print("=" * 44)
        return False

    # Discord "embed" makes it look clean on your phone.
    embed = {
        "title": title,
        "description": body,
        "color": 0x2ECC71,  # green
    }
    if url_hint:
        embed["url"] = url_hint
    payload = json.dumps({"embeds": [embed]}).encode()
    req = urllib.request.Request(
        webhook, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "paper-trading/0.1"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:  # noqa: BLE001 - never let a bad alert kill the scanner
        print(f"⚠️  Discord send failed ({e}); alert was:\n{title}\n{body}")
        return False


if __name__ == "__main__":
    send("✅ Test alert", ["This is a test.", "If you see this in Discord, it works."])
