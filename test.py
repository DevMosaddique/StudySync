from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
from datetime import datetime
import os
import subprocess
import logging
import requests
import re
import uuid
import json
import time
import asyncio

# Function to send progress updates
async def send_progress_update(context, chat_id, message_id, task_duration=10):
    for i in range(1, 101):
        # Simulating a task by sleeping for some time
        await asyncio.sleep(task_duration / 100)  # Adjust this duration according to your task
        progress_text = f"Generating download links... {i}% complete"
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=progress_text)
        except Exception as e:
            logging.error(f"Failed to update message: {e}")
            break

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

# File path for download history
HISTORY_FILE = "download_history.json"

# Load history from file
def load_history() -> dict:
    try:
        with open(HISTORY_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

# Save history to file
def save_history(history: dict):
    with open(HISTORY_FILE, "w") as file:
        json.dump(history, file, indent=4)

# Add a new entry to a user's history
def add_to_history(user_id: int, url: str, format: str):
    history = load_history()
    if str(user_id) not in history:
        history[str(user_id)] = []

    # Add new entry
    history[str(user_id)].append({
        "url": url,
        "format": format,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    # Limit history to the last 10 downloads per user
    history[str(user_id)] = history[str(user_id)][-10:]
    save_history(history)

PREFERENCE_FILE = "user_preferences.json"

# Load preferences from file
def load_preferences() -> dict:
    try:
        with open(PREFERENCE_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

# Save preferences to file
def save_preferences(preferences: dict):
    with open(PREFERENCE_FILE, "w") as file:
        json.dump(preferences, file, indent=4)

# Set a user's preference
def set_user_preference(user_id: int, preference_key: str, preference_value: str):
    preferences = load_preferences()
    if str(user_id) not in preferences:
        preferences[str(user_id)] = {}
    preferences[str(user_id)][preference_key] = preference_value
    save_preferences(preferences)

# Get a user's preference
def get_user_preference(user_id: int, preference_key: str = None, default_value: str = None) -> str:
    preferences = load_preferences()
    if preference_key:
        return preferences.get(str(user_id), {}).get(preference_key, default_value)
    return preferences.get(str(user_id), default_value)

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

# Function to delete messages after expiration
async def delete_expired_message(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    message_id = job_data.get("message_id")

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logging.info(f"Deleted expired message: {message_id} in chat: {chat_id}")
    except Exception as e:
        asyncio.create_task(send_progress_update(context, chat_id, message.message_id, task_duration=10))

        command = ["yt-dlp", "-g", "-f", "best", link]
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
    history = load_history()

    # Check if user has any history
    user_history = history.get(str(chat_id), [])
    if not user_history:
        await context.bot.send_message(chat_id=chat_id, text="📜 No download history found!", parse_mode='Markdown')
        return

    # Send the first page
    await send_history_page(chat_id, user_history, 0, context)

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

            # Log the download in history
            add_to_history(chat_id, link, format_id)
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❗ An unexpected error occurred: {e} ❗")
        logging.error(f"Unexpected error: {e}")


# Message handler for YouTube/Instagram links
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text

    if not is_valid_link(text):
        await context.bot.send_message(chat_id=chat_id, text="🚫 Invalid link. Please send a valid *YouTube* or *Instagram* link.", parse_mode='Markdown')
        return

    link = normalize_url(text)

    if "instagram.com" in link:
        await context.bot.send_message(chat_id=chat_id, text="🔍 Fetching your download link, please wait...")
        await send_instagram_download_link(chat_id, link, context)
    else:
        await context.bot.send_message(chat_id=chat_id, text="🔍 Fetching available formats, please wait...")
        formats = fetch_formats(link)

        if not formats:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Failed to fetch available formats. Please try again.", parse_mode='Markdown')
            return

        # Update handle_message to pass preference key
        default_quality = get_user_preference(chat_id, "default_quality")

        # Filter and organize available formats
        desired_resolutions = ['144p', '240p', '360p', '480p', '720p', '1080p']
        filtered_formats = {}

        for format_id, resolution in formats:
            for quality in desired_resolutions:
                if quality in resolution and 'mp4' in resolution:
                    filtered_formats[quality] = format_id
                elif quality in resolution and 'webm' in resolution and quality not in filtered_formats:
                    filtered_formats[quality] = format_id
            if 'audio only' in resolution:
                if 'best_audio' not in filtered_formats or 'DRC' not in resolution:
                    filtered_formats['best_audio'] = format_id

        # Check if user's default quality is available
        if default_quality and default_quality in filtered_formats:
            format_id = filtered_formats[default_quality]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎥 Using your default preference: *{default_quality}*. Generating download link..."
            )
            await send_youtube_download_link(format_id, chat_id, link, context)
            return

        # Cache unique ID and formats
        unique_id = str(uuid.uuid4())
        URL_CACHE[unique_id] = link
        FORMAT_CACHE[unique_id] = filtered_formats

        # Generate buttons for available formats
        keyboard = []
        row = []
        for resolution, format_id in filtered_formats.items():
            button_text = "Best Quality Audio" if resolution == 'best_audio' else resolution
            row.append(InlineKeyboardButton(button_text, callback_data=f"{format_id}|{unique_id}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Ask the user to select a format
        await context.bot.send_message(
            chat_id=chat_id,
            text="🎥 Select the desired format for your download:",
            reply_markup=reply_markup
        )

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name if update.effective_user else "there"
    await update.message.reply_text(
        f"👋 *Hi {user_name}!* Send me a _YouTube_ or _Instagram_ link, and I'll generate a direct download link for you!",
        parse_mode='Markdown'
    )

# Function to show history with pagination
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    history = load_history()

    # Check if user has any history
    user_history = history.get(str(chat_id), [])
    if not user_history:
        await context.bot.send_message(chat_id=chat_id, text="📜 No download history found!")
        return

    # Send the first page
    await send_history_page(chat_id, user_history, 0, context)

# Function to send history page with pagination
async def send_history_page(chat_id: int, history: list, page: int, context):
    items_per_page = 5
    start = page * items_per_page
    end = start + items_per_page
    current_page_items = history[start:end]

    # Generate the message
    message = f"📜 *Your Download History (Page {page + 1}/{(len(history) - 1) // items_per_page + 1})*:\n\n"
    for entry in current_page_items:
        message += f"🔗 *URL*: {entry['url']}\n🎥 *Format*: {entry['format']}\n📅 *Time*: {entry['timestamp']}\n\n"

    # Inline keyboard for pagination
    keyboard = []
    if page > 0:  # Add "Previous" button if not on the first page
        keyboard.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"history|{page - 1}"))
    if end < len(history):  # Add "Next" button if not on the last page
        keyboard.append(InlineKeyboardButton("➡️ Next", callback_data=f"history|{page + 1}"))

    reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else None

    # Send the message
    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown", reply_markup=reply_markup)

# Callback query handler for format selection
async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if len(data) == 2:
        format_code = data[0]
        unique_id = data[1]
        chat_id = query.message.chat_id

        #unique id check 
        if unique_id in URL_CACHE:
            await context.bot.send_message(chat_id=chat_id, text="📥 Generating your download link, please wait...", parse_mode='Markdown')
            await send_youtube_download_link(format_code, chat_id, URL_CACHE[unique_id], context)
        else:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Error: Invalid selection. Please try again.", parse_mode='Markdown')

# Callback query handler for pagination (Previous/Next)
async def handle_history_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if data[0] == "history":
        page = int(data[1])
        chat_id = query.message.chat_id
        history = load_history().get(str(chat_id), [])

        await send_history_page(chat_id, history, page, context)

async def set_default(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args

    if len(args) != 1:
        await context.bot.send_message(chat_id=chat_id, text="❌ Usage: /setdefault <quality>\n\nExample: /setdefault *720p* or /setdefault *best_audio*", parse_mode='Markdown')
        return

    quality = args[0].lower()
    valid_qualities = ['144p', '240p', '360p', '480p', '720p', '1080p', 'best_audio']
    if quality not in valid_qualities:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Invalid quality. Please choose one of the following: {', '.join(valid_qualities)}")
        return

    set_user_preference(chat_id, "default_quality", quality)
    await context.bot.send_message(chat_id=chat_id, text=f"✅ Default quality set to *{quality}*.", parse_mode='Markdown')

async def get_default(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    default_quality = get_user_preference(chat_id, "default_quality", "None set")

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📋 Your default download quality is: *{default_quality}*.",
        parse_mode='Markdown'
    )

async def delete_default(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    preferences = load_preferences()

    if str(chat_id) in preferences and "default_quality" in preferences[str(chat_id)]:
        del preferences[str(chat_id)]["default_quality"]
        save_preferences(preferences)
        await context.bot.send_message(chat_id=chat_id, text="🗑 Default quality setting has been deleted.", parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ No default quality setting found to delete.")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_format_selection, pattern=r"^\d+\|.+$"))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CallbackQueryHandler(handle_history_pagination, pattern=r"^history\|\d+$"))
    app.add_handler(CommandHandler("setdefault", set_default))
    app.add_handler(CommandHandler("getdefault", get_default))
    app.add_handler(CommandHandler("deletedefault", delete_default))

    app.run_polling()

if __name__ == "__main__":
    main()