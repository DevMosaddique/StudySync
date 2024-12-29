from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import os
import subprocess
import logging
import httpx

# Load .env file
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env file")

# Set up logging to suppress httpx INFO logs
logging.basicConfig(level=logging.WARNING)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

# Function to download YouTube/Instagram video
async def download_video(link: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        video_file = "downloaded_video.mp4"
        command = [
            "yt-dlp",
            "--geo-bypass",  # Optional: Bypass geographical restrictions
            "--no-playlist",  # Download a single video
            "-f", "best",  # Download the best available format
            "--cookies", "cookies.txt",  # Use the existing cookies for authentication
            "-o", "downloaded_video.mp4",  # Output file
            link,  # Instagram video URL
        ]

        subprocess.run(command, check=True)

        # Send the video to the user
        await context.bot.send_message(chat_id=chat_id, text="Downloaded video successfully!")
        await context.bot.send_video(chat_id=chat_id, video=open(video_file, 'rb'))

        # Clean up the downloaded file
        os.remove(video_file)
    except subprocess.CalledProcessError as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Error downloading video: {e}")
        logging.error("Error downloading video: %s", e)
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"An unexpected error occurred: {e}")
        logging.error("Unexpected error: %s", e)
# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text

    if "youtube.com" in text or "youtu.be" in text or "instagram.com" in text:
        await context.bot.send_message(chat_id=chat_id, text="Downloading the video, please wait...")
        await download_video(text, chat_id, context)
    else:
        await context.bot.send_message(chat_id=chat_id, text="Please send a valid YouTube or Instagram link.")

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a YouTube or Instagram link, and I'll download the video for you!")

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