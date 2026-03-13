import os
import logging
import asyncio
import threading
from flask import Flask
from telegram import Update, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode, ChatAction
from downloader import TeraboxDownloader
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
PORT = int(os.getenv("PORT", "10000"))

# ── Health Check Server ──────────────────────────────────────────────────────

health_app = Flask(__name__)

@health_app.route('/')
def health_check():
    return "OK", 200

def run_health_server():
    logger.info(f"🚀 Health check server starting on port {PORT}...")
    try:
        health_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"❌ Health check server failed to start: {e}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def is_terabox_url(text: str) -> bool:
    domains = [
        "terabox.com", "teraboxapp.com", "1024terabox.com",
        "terabox.fun", "terafileshare.com", "teraboxlink.com",
        "mirrobox.com", "nephobox.com", "4funbox.co",
        "momerybox.com", "tibibox.com",
    ]
    return any(domain in text.lower() for domain in domains)


async def send_progress(message: Message, text: str):
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        pass


# ── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Welcome to Terabox Downloader Bot!</b>\n\n"
        "Send me any <b>Terabox video link</b> and I'll download it for you.\n\n"
        "<b>Supported domains:</b>\n"
        "• terabox.com\n"
        "• teraboxapp.com\n"
        "• 1024terabox.com\n"
        "• and more variants…\n\n"
        "ℹ️ <i>Note: Files larger than 50 MB will be sent as a download link.</i>",
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>How to use:</b>\n\n"
        "1. Copy a Terabox share link\n"
        "2. Paste it here\n"
        "3. Wait while I download and send the video\n\n"
        "<b>Commands:</b>\n"
        "/start — Welcome message\n"
        "/help  — This help message",
        parse_mode=ParseMode.HTML,
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not is_terabox_url(text):
        await update.message.reply_text(
            "❌ That doesn't look like a Terabox link.\n"
            "Please send a valid Terabox share URL."
        )
        return

    status_msg = await update.message.reply_text("🔍 Fetching file info…")
    downloader = TeraboxDownloader()

    try:
        # Step 1: resolve metadata
        await update.effective_chat.send_action(ChatAction.TYPING)
        info = await downloader.get_info(text)

        if not info:
            await send_progress(status_msg, "❌ Could not retrieve file info. The link may be invalid or expired.")
            return

        name = info.get("name", "video")
        size_bytes = info.get("size", 0)
        size_mb = size_bytes / (1024 * 1024)
        direct_url = info.get("download_url")

        await send_progress(
            status_msg,
            f"📦 <b>{name}</b>\n"
            f"📏 Size: <code>{size_mb:.1f} MB</code>\n\n"
            "⬇️ Downloading…",
        )

        # Step 2: large files — just share the link
        if size_mb > MAX_FILE_SIZE_MB:
            await send_progress(
                status_msg,
                f"⚠️ File is <b>{size_mb:.1f} MB</b> — too large to upload via Telegram (limit: {MAX_FILE_SIZE_MB} MB).\n\n"
                f"🔗 <b>Direct download link:</b>\n<code>{direct_url}</code>\n\n"
                "<i>This link may expire. Use it soon!</i>",
            )
            return

        # Step 3: download to disk
        await update.effective_chat.send_action(ChatAction.UPLOAD_VIDEO)
        file_path = await downloader.download(info)

        if not file_path:
            await send_progress(status_msg, "❌ Download failed. Please try again later.")
            return

        # Step 4: send video
        await send_progress(status_msg, "📤 Uploading to Telegram…")
        with open(file_path, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption=f"🎬 <b>{name}</b>",
                parse_mode=ParseMode.HTML,
                supports_streaming=True,
            )

        await status_msg.delete()

        # Clean up
        try:
            os.remove(file_path)
        except OSError:
            pass

    except Exception as e:
        logger.exception("Error handling link: %s", e)
        await send_progress(status_msg, f"❌ An error occurred:\n<code>{e}</code>")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    # Start health check server IMMEDIATELY to satisfy Render's port scan
    threading.Thread(target=run_health_server, daemon=True).start()

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set. Check your .env file.")

    # Build the application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    logger.info("Bot is starting…")

    # Use run_polling which handles the loop internally when called via asyncio.run
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        
        logger.info("Bot is running…")
        # Keep the service running
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
