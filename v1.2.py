from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import os
import subprocess
import logging
import requests
import re

# Load .env file
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env file")

# Set up logging to suppress INFO logs
logging.basicConfig(level=logging.WARNING)

# Function to validate YouTube and Instagram links
def is_valid_link(url: str) -> bool:
    # Regular expressions for YouTube and Instagram
    youtube_regex = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"
    instagram_regex = r"(https?://)?(www\.)?instagram\.com/.+"

    # Check if the URL matches either regex
    return bool(re.match(youtube_regex, url)) or bool(re.match(instagram_regex, url))

# Normalize YouTube Shorts URL
def normalize_url(url: str) -> str:
    if "youtube.com/shorts/" in url:
        return url.replace("youtube.com/shorts/", "youtube.com/watch?v=")
    return url

# Function to shorten URL using TinyURL
def shorten_url(long_url: str) -> str:
    response = requests.get(f"https://tinyurl.com/api-create.php?url={long_url}")
    if response.status_code == 200:
        short_link = response.text
        logging.info(f"TinyURL shortened URL: {short_link}")
        return short_link
    else:
        logging.error("TinyURL API error: %s", response.text)
        return long_url

# Function to generate and send a combined direct download link
async def send_download_link(link: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        link = normalize_url(link)  # Normalize the URL
        command = ["yt-dlp", "-g", "--cookies", "cookies.txt", "-f", "best", link]  # Generate combined direct download link
        result = subprocess.run(command, capture_output=True, text=True)

        # Check for errors
        if result.returncode != 0:
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Error: {result.stderr.strip()} ⚠️")
            logging.error("yt-dlp error: %s", result.stderr.strip())
            return

        # Shorten the direct download link using TinyURL
        direct_link = result.stdout.strip()
        logging.info(f"Direct download link: {direct_link}")
        if direct_link:
            short_link = shorten_url(direct_link)
            logging.info(f"Shortened link to be sent: {short_link}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 Here is your direct download link:\n🔗 {short_link}\n\n📥 You can open it in your browser or a download manager."
            )
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❗ An unexpected error occurred: {e} ❗")
        logging.error("Unexpected error: %s", e)

# Message handler to process YouTube/Instagram links
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    user_name = update.effective_user.first_name if update.effective_user else "there"

    # Validate the link
    if not is_valid_link(text):
        await context.bot.send_message(chat_id=chat_id, text="🚫 The link you sent is not valid. Please send a proper YouTube or Instagram URL. 🚫")
        return

    # Identify the platform
    if "youtube.com" in text or "youtu.be" in text:
        platform = "YouTube"
    elif "instagram.com" in text:
        platform = "Instagram"
    else:
        platform = None

    # Proceed if a valid platform is detected
    if platform:
        await context.bot.send_message(chat_id=chat_id, text=f"🌟 Hi {user_name}, generating a direct download link for your {platform} link. Please wait... 🌟")
        await send_download_link(text, chat_id, context)

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name if update.effective_user else "there"
    await update.message.reply_text(f"👋 Hi {user_name}! Send me a YouTube or Instagram link, and I'll generate a direct download link for you!")

# Main function
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the bot
    app.run_polling()

if __name__ == "__main__":
    main()
