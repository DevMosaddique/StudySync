from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
import os
import subprocess
import logging
import requests
import re
import uuid

# Load .env file
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env file")

# Set up logging
logging.basicConfig(level=logging.WARNING)

# Temporary cache to store URLs and fetched formats
URL_CACHE = {}
FORMAT_CACHE = {}

# Function to validate YouTube and Instagram links
def is_valid_link(url: str) -> bool:
    youtube_regex = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"
    instagram_regex = r"(https?://)?(www\.)?instagram\.com/.+"
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
        return response.text
    return long_url

# Function to fetch available formats for YouTube
def fetch_formats(url: str) -> list:
    command = ["yt-dlp", "-F", "--cookies", "cookies.txt", url]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        logging.error(f"yt-dlp error: {result.stderr.strip()}")
        return None

    formats = []
    for line in result.stdout.splitlines():
        if re.match(r"^\d+", line):  # Format lines start with a number
            parts = line.split()
            format_id = parts[0]
            resolution = " ".join(parts[1:])  # Combine remaining parts for resolution/quality
            formats.append((format_id, resolution))
    return formats

# Function to generate and send the direct download link for Instagram
async def send_instagram_download_link(chat_id: int, link: str, context):
    try:
        command = ["yt-dlp", "-g", link]
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0:
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Error: {result.stderr.strip()} ⚠️")
            logging.error(f"yt-dlp error: {result.stderr.strip()}")
            return

        direct_link = result.stdout.strip()
        if direct_link:
            short_link = shorten_url(direct_link)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 Here is your direct download link:\n🔗 {short_link}\n\n📥 Open it in your browser or a download manager."
            )
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❗ An unexpected error occurred: {e} ❗")
        logging.error(f"Unexpected error: {e}")

# Function to generate and send the direct download link for YouTube
async def send_youtube_download_link(format_id: str, chat_id: int, link: str, context):
    try:
        command = ["yt-dlp", "-g", "--cookies", "cookies.txt", "-f", format_id, link]
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0:
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Error: {result.stderr.strip()} ⚠️")
            logging.error(f"yt-dlp error: {result.stderr.strip()}")
            return

        direct_link = result.stdout.strip()
        if direct_link:
            short_link = shorten_url(direct_link)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 Here is your direct download link:\n🔗 {short_link}\n\n📥 Open it in your browser or a download manager."
            )
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❗ An unexpected error occurred: {e} ❗")
        logging.error(f"Unexpected error: {e}")

# Callback query handler for format selection
async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    format_code = data[0]
    unique_id = data[1]
    chat_id = query.message.chat_id

    # Inform user and process the download
    await context.bot.send_message(chat_id=chat_id, text="📥 Generating your download link, please wait...")
    await send_youtube_download_link(format_code, chat_id, URL_CACHE[unique_id], context)

# Message handler for YouTube/Instagram links
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text

    if not is_valid_link(text):
        await context.bot.send_message(chat_id=chat_id, text="🚫 Invalid link. Please send a valid YouTube or Instagram link.")
        return

    # Normalize the link
    link = normalize_url(text)

    if "instagram.com" in link:
        # Directly send the download link for Instagram
        await context.bot.send_message(chat_id=chat_id, text="🔍 Fetching your download link, please wait...")
        await send_instagram_download_link(chat_id, link, context)
    else:
        # Fetch available formats for YouTube
        await context.bot.send_message(chat_id=chat_id, text="🔍 Fetching available formats, please wait...")
        formats = fetch_formats(link)
        if not formats:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Failed to fetch available formats. Please try again.")
            return

        # Filter formats to include only specified quality options
        desired_resolutions = ['144p', '240p', '360p', '480p', '720p', '1080p']
        filtered_formats = {}

        for format_id, resolution in formats:
            # Prioritize mp4, fallback to webm if mp4 is not available for video
            for quality in desired_resolutions:
                if quality in resolution and 'mp4' in resolution:
                    filtered_formats[quality] = format_id
                elif quality in resolution and 'webm' in resolution and quality not in filtered_formats:
                    filtered_formats[quality] = format_id
            # Handle audio only formats
            if 'audio only' in resolution:
                if 'best_audio' not in filtered_formats or 'DRC' not in resolution:
                    filtered_formats['best_audio'] = format_id

        # Cache the URL with a unique ID
        unique_id = str(uuid.uuid4())
        URL_CACHE[unique_id] = link
        FORMAT_CACHE[unique_id] = filtered_formats

        # Generate inline keyboard with available formats
        keyboard = []
        row = []
        for resolution, format_id in filtered_formats.items():
            if resolution == 'best_audio':
                button_text = "Best Quality Audio"
            else:
                button_text = resolution
            row.append(InlineKeyboardButton(button_text, callback_data=f"{format_id}|{unique_id}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text="🎥 Select the desired format for your download:",
            reply_markup=reply_markup
        )

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
    app.add_handler(CallbackQueryHandler(handle_format_selection))

    app.run_polling()

if __name__ == "__main__":
    main()