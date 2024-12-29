import os
import logging
import requests
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Load .env file
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env file")

# Set up logging to suppress INFO logs
logging.basicConfig(level=logging.WARNING)

# Normalize YouTube Shorts URL
def normalize_url(url: str) -> str:
    if "youtube.com/shorts/" in url:
        return url.replace("youtube.com/shorts/", "youtube.com/watch?v=")
    return url

# Function to shorten the URL using TinyURL
def shorten_url(long_url: str) -> str:
    try:
        response = requests.get(f'http://tinyurl.com/api-create.php?url={long_url}')
        if response.status_code == 200:
            return response.text
        else:
            return long_url  # Fallback to the original URL if the shortening fails
    except Exception as e:
        logging.error("Error in shortening URL: %s", e)
        return long_url  # Fallback to the original URL if an error occurs

# Function to generate and send direct download link
async def send_download_link(link: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        link = normalize_url(link)  # Normalize the URL
        command = ["yt-dlp", "-g", "--cookies", "cookies.txt", link]  # Generate direct download link
        result = subprocess.run(command, capture_output=True, text=True)

        # Check for errors
        if result.returncode != 0:
            await context.bot.send_message(chat_id=chat_id, text=f"Error: {result.stderr.strip()}")
            logging.error("yt-dlp error: %s", result.stderr.strip())
            return

        # Shorten the direct download link using TinyURL
        direct_link = shorten_url(result.stdout.strip())
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Here is your direct download link:\n{direct_link}\n\nYou can open it in your browser or a download manager."
        )
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"An unexpected error occurred: {e}")
        logging.error("Unexpected error: %s", e)

# Message handler to process YouTube/Instagram links
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text

    if "youtube.com" in text or "youtu.be" in text or "instagram.com" in text:
        await context.bot.send_message(chat_id=chat_id, text="Generating a direct download link, please wait...")
        await send_download_link(text, chat_id, context)
    else:
        await context.bot.send_message(chat_id=chat_id, text="Please send a valid YouTube or Instagram link.")

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to ClipSphere! Send me a YouTube or Instagram link, and I'll generate a direct download link for you!")

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