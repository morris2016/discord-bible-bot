import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import aiohttp
import os
import asyncio
import random

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

manifest_url = "https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/manifest.json"
manifest_data = []
bookmarks = {}
current_chapter_index = {}


def chapter_key(book, chapter):
    return f"{book.lower()}:{chapter}"


async def fetch_manifest():
    global manifest_data
    if not manifest_data:
        async with aiohttp.ClientSession() as session:
            async with session.get(manifest_url) as resp:
                manifest_data = await resp.json()


async def play_entry(interaction, index):
    try:
        await fetch_manifest()
        entry = manifest_data[index]
        url = entry['url']
        guild = interaction.guild

        if not guild.voice_client:
            if interaction.user.voice:
                vc = await interaction.user.voice.channel.connect()
            else:
                await interaction.response.send_message("❌ You're not in a voice channel.", ephemeral=True)
                return
        else:
            vc = guild.voice_client

        for _ in range(5):
            if vc.is_connected():
                break
            await asyncio.sleep(0.5)

        if vc.is_playing():
            vc.stop()

        current_chapter_index[guild.id] = index
        vc.play(discord.FFmpegPCMAudio(url), after=lambda e: asyncio.run_coroutine_threadsafe(auto_next(interaction), bot.loop))

        try:
            await interaction.response.send_message(f"▶️ Playing {entry['book']} {entry['chapter']}", ephemeral=True)
        except discord.errors.InteractionResponded:
            await interaction.followup.send(f"▶️ Playing {entry['book']} {entry['chapter']}", ephemeral=True)

    except Exception as e:
        print("Playback error:", e)
        try:
            await interaction.response.send_message(f"❌ Failed to play: {e}", ephemeral=True)
        except discord.errors.InteractionResponded:
            await interaction.followup.send(f"❌ Failed to play: {e}", ephemeral=True)


async def auto_next(interaction):
    try:
        index = current_chapter_index.get(interaction.guild.id, -1)
        if index + 1 < len(manifest_data):
            await play_entry(interaction, index + 1)
    except Exception as e:
        print("Error autoplay:", e)


@bot.event
async def on_ready():
    await fetch_manifest()
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")


bot.run(os.getenv("BOT_TOKEN"))
