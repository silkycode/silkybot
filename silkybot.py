import re
import os
import uuid
import discord
import subprocess
import asyncio
import sys
from dotenv import load_dotenv
import os
from discord.ext import commands
import yt_dlp

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if TOKEN is None:
    print("Error: DISCORD_BOT_TOKEN environment variable not set.")
    sys.exit(1)

YT_URL_PATTERN = r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+[^\s]*)'

MAX_SIZE_BYTES = 100 * 1024 * 1024
MAX_DISCORD_FILE_SIZE = 8 * 1024 * 1024

ALLOWED_CHANNELS = {
        'the-funny', '🦝general🦝', 'bot-spam', 'bot-commands',
        'bot commands', 'music', '🎼music🎶', 'general'
    }

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

if not os.path.exists('thumbnails'):
    os.makedirs('thumbnails')

def compress_video_webm(input_file, output_file, target_size_bytes=10 * 1024 * 1024):
    crf = 30
    while crf <= 45:
        print(f"[compress_video_webm] Trying CRF {crf}")
        cmd = [
            'ffmpeg', '-y', '-i', input_file,
            '-preset', 'fast',
            '-c:v', 'libvpx-vp9', 
            '-crf', str(crf),
            '-b:v', '0',
            '-c:a', 'libopus',
            output_file
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0 or not os.path.exists(output_file):
            print("[compress_video_webm] FFmpeg error output:\n", res.stderr.decode())
            return False
        if os.path.getsize(output_file) <= target_size_bytes:
            print(f"[compress_video_webm] Compression successful: {os.path.getsize(output_file)} bytes")
            return True
        crf += 5

    print("[compress_video_webm] Attempting fallback low-res compression")
    cmd = [
        'ffmpeg', '-y', '-i', input_file,
        '-vf', 'scale=-2:240',
        '-preset', 'fast',
        '-c:v', 'libvpx-vp9',
        '-crf', '45',
        '-b:v', '0',
        '-c:a', 'libopus',
        output_file
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode == 0 and os.path.exists(output_file):
        return os.path.getsize(output_file) <= target_size_bytes
    return False

async def download(message, url):
    orig_file = f"source_{uuid.uuid4().hex}.mp4"
    comp_file = f"compressed_{uuid.uuid4().hex}.mp4"
    fallback_file = f"audio_thumb_{uuid.uuid4().hex}.mp4"

    ydl_opts = {
        'format': 'mp4[height<=360]/mp4',
        'outtmpl': orig_file,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'ignoreerrors': True,
        'nocheckcertificate': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return False, None

            filesize = info.get('filesize') or info.get('filesize_approx') or 0
            title = info.get('title', None)

            if filesize > MAX_SIZE_BYTES:
                print(f"[download] File too large: {filesize} bytes")
                return False, title

            ydl.download([url])

        print("[download] Attempting compression")
        compressed_success = await asyncio.to_thread(compress_video_webm, orig_file, comp_file)
        if compressed_success and os.path.getsize(comp_file) <= MAX_DISCORD_FILE_SIZE:
            with open(comp_file, "rb") as f:
                await message.channel.send(file=discord.File(f, comp_file))
            os.remove(orig_file)
            os.remove(comp_file)
            return True, title

        print("[download] Compression failed or result too large")
        os.remove(orig_file)
        return False, title

    except Exception as e:
        print(f"[download] Exception: {e}")
        for f in [orig_file, comp_file, fallback_file]:
            if os.path.exists(f):
                os.remove(f)
        return False, None

# on message handler
@bot.event
async def on_message(message):
    channel = message.channel
    content_lower = message.content.lower()

    if message.author == bot.user:
        return    
    if bot.user in message.mentions or "silky" in content_lower or "silkybot" in content_lower or "@silkybot" in content_lower:
        try:
            await message.add_reaction("👁️")
        except discord.HTTPException:
            pass
        return
    if isinstance(channel, discord.Thread):
        thread_name = channel.name.lower()
        parent_name = channel.parent.name.lower() if channel.parent else None
        if thread_name != 'wow-stuff' and parent_name not in ALLOWED_CHANNELS:
            return
    else:
        if channel.name.lower() not in ALLOWED_CHANNELS:
            return

    yt_match = re.search(YT_URL_PATTERN, message.content, re.IGNORECASE)
    if yt_match:
        url = yt_match.group(1)
        success, title = await download(message, url)
        if success:
            try:
                await message.delete()
            except Exception as e:
                print(f"[on_message] Failed to delete original message: {e}")

            title_text = f" ({title})" if title else ""
            await message.channel.send(f"{message.author.mention} posted: <{url}>{title_text}")

    await bot.process_commands(message)

bot.run(TOKEN)