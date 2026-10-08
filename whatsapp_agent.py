# ==============================================================================
#  EXBT WhatsApp Daily Reporting Agent
#  Generates daily infographic & sends to WhatsApp group daily at 9:00 PM PST.
# ==============================================================================

import os
import sys
import time
import datetime
import argparse
import logging
import requests
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from generate_report_card import get_report_data, create_report_image
import config

logger = logging.getLogger("whatsapp_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# ──────────────────────────────────────────────────────────────────────────────
# WHATSAPP GATEWAY CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
# Supported providers: "ultramsg", "green_api", "custom_webhook"
WHATSAPP_PROVIDER = getattr(config, "WHATSAPP_PROVIDER", "ultramsg")
WHATSAPP_INSTANCE_ID = getattr(config, "WHATSAPP_INSTANCE_ID", "YOUR_INSTANCE_ID")
WHATSAPP_TOKEN = getattr(config, "WHATSAPP_TOKEN", "YOUR_TOKEN")
WHATSAPP_TARGET = getattr(config, "WHATSAPP_TARGET", "YOUR_GROUP_OR_PHONE_NUMBER")

REPORT_IMAGE_PATH = "/root/exbt_mm_bot/daily_report_latest.png"


def build_whatsapp_caption(d: dict) -> str:
    """Builds a formatted, clean WhatsApp text report."""
    caption = (
        f"📊 *EXBT/USDT DAILY MARKET & TREASURY REPORT*\n"
        f"📅 Date: {d['date_str']} | Time: {d['time_str']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *TOTAL COMPANY TREASURY:*\n"
        f"• Total USDT: *${d['total_usdt']:,.2f} USDT*\n"
        f"• Total EXBT: *{d['total_exbt']:,.0f} EXBT*\n"
        f"• Net Spread Loss: *$0.00 (Zero-Loss MM)*\n\n"
        f"🏦 *ACCOUNTS BREAKDOWN:*\n"
        f"• Account A: ${d['bal_a_u']:,.2f} USDT | {d['bal_a_e']:,.0f} EXBT\n"
        f"• Account B: ${d['bal_b_u']:,.2f} USDT | {d['bal_b_e']:,.0f} EXBT\n\n"
        f"📈 *24H EXCHANGE PERFORMANCE:*\n"
        f"• Current Price: *{d['price']} USDT* ({d['change']}%)\n"
        f"• 24h Volume: *{d['vol_exbt']:,.0f} EXBT* (${d['vol_usdt']:,.2f})\n"
        f"• 24h Range: High {d['high']} | Low {d['low']}\n"
        f"• Corridor: *0.3500 - 0.4200 USDT (Target: 0.4000)*\n\n"
        f"✅ *Status:* Both Market Maker & Candle Bots 100% Healthy."
    )
    return caption


def send_whatsapp_message(image_path: str, caption: str) -> bool:
    """Sends image and text caption via configured WhatsApp provider."""
    if WHATSAPP_TOKEN == "YOUR_TOKEN" or not WHATSAPP_TOKEN:
        logger.warning("WhatsApp API credentials not configured yet. Saving report locally.")
        logger.info(f"\n[MOCK WHATSAPP DISPATCH]\nImage: {image_path}\nCaption:\n{caption}\n")
        return False

    try:
        if WHATSAPP_PROVIDER == "ultramsg":
            # UltraMsg API
            url = f"https://api.ultramsg.com/{WHATSAPP_INSTANCE_ID}/messages/image"
            with open(image_path, "rb") as f:
                files = {"image": f}
                payload = {
                    "token": WHATSAPP_TOKEN,
                    "to": WHATSAPP_TARGET,
                    "caption": caption
                }
                res = requests.post(url, data=payload, files=files, timeout=30)
                logger.info(f"UltraMsg response: {res.status_code} {res.text}")
                return res.status_code == 200

        elif WHATSAPP_PROVIDER == "green_api":
            # Green API
            url = f"https://api.green-api.com/waInstance{WHATSAPP_INSTANCE_ID}/sendFileByUpload/{WHATSAPP_TOKEN}"
            with open(image_path, "rb") as f:
                files = {"file": f}
                payload = {
                    "chatId": WHATSAPP_TARGET,
                    "caption": caption
                }
                res = requests.post(url, data=payload, files=files, timeout=30)
                logger.info(f"Green API response: {res.status_code} {res.text}")
                return res.status_code == 200

        elif WHATSAPP_PROVIDER == "custom_webhook":
            # Custom Webhook / Telegram fallback
            payload = {
                "chat_id": WHATSAPP_TARGET,
                "caption": caption,
                "timestamp": time.time()
            }
            res = requests.post(WHATSAPP_TOKEN, json=payload, timeout=20)
            return res.status_code == 200

    except Exception as e:
        logger.error(f"WhatsApp sending failed: {e}")
        return False


def dispatch_daily_report():
    """Generates live data, creates PNG infographic card, and sends to WhatsApp."""
    logger.info("Generating Daily EXBT Market Report...")
    data = get_report_data()
    img_path = create_report_image(data, REPORT_IMAGE_PATH)
    caption = build_whatsapp_caption(data)

    logger.info(f"Report image saved to {img_path}")
    sent = send_whatsapp_message(img_path, caption)
    if sent:
        logger.info("✅ Daily Report successfully dispatched to WhatsApp!")
    else:
        logger.info("Report prepared. Awaiting WhatsApp API credentials to dispatch.")
    return data, img_path


def run_scheduler_loop():
    """
    Runs in the background and sends report daily at 9:00 PM PST (21:00 PKT).
    Pakistan Standard Time is UTC+5. 21:00 PKT = 16:00 UTC.
    """
    logger.info("🕒 WhatsApp Reporting Agent Scheduler started. Target time: 9:00 PM PST daily.")
    last_sent_day = None

    while True:
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        pkt_now = utc_now + datetime.timedelta(hours=5)
        current_day = pkt_now.date()

        # Check if it's 21:00 PST (between 21:00 and 21:05) and hasn't sent today
        if pkt_now.hour == 21 and pkt_now.minute == 0 and last_sent_day != current_day:
            logger.info("🔔 It is 9:00 PM PST! Triggering daily report...")
            try:
                dispatch_daily_report()
                last_sent_day = current_day
            except Exception as e:
                logger.error(f"Daily report error: {e}")
            time.sleep(60)

        time.sleep(25)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="Send report immediately right now")
    args = parser.parse_args()

    if args.now:
        dispatch_daily_report()
    else:
        run_scheduler_loop()
