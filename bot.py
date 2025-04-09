import discord
from discord.ext import commands, tasks
from discord import app_commands, FFmpegPCMAudio
import aiohttp
import asyncio
import json
import random
import os

import time  # Add this with your imports if not already present

class SafeAudio(FFmpegPCMAudio):
    def __init__(self, source_url):
        super().__init__(source_url)
        self.start_time = time.time()

    def elapsed(self):
        return time.time() - self.start_time


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

manifest_url = "https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/manifest.json"
manifest_data = []
playback_index = {}
voice_clients = {}
playback_contexts = {}
bookmarks = {}  # user_id: (book, chapter)
settings_store = {}  # guild_id: {"voice_channel_id": int, "devotion_hour": int}

SAVE_FILE = "resume_state.json"
if os.path.exists(SAVE_FILE):
    with open(SAVE_FILE, "r") as f:
        try:
            bookmarks = json.load(f)
        except:
            bookmarks = {}

@bot.event
async def on_disconnect():
    with open(SAVE_FILE, "w") as f:
        json.dump(bookmarks, f)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await fetch_manifest()
    await tree.sync()
    #playback_watcher.start()
    #daily_devotion.start()

# -------- MANIFEST LOADER --------
async def fetch_manifest():
    global manifest_data
    async with aiohttp.ClientSession() as session:
        async with session.get(manifest_url) as resp:
            if resp.status == 200:
                manifest_data = await resp.json()
                print(f"📖 Loaded {len(manifest_data)} chapters from manifest")
            else:
                print(f"❌ Failed to fetch manifest ({resp.status})")

# -------- HELPER FUNCTIONS --------
def get_index(book: str, chapter: int):
    normalized_book = book.replace(" ", "").lower()
    for i, entry in enumerate(manifest_data):
        entry_book = entry['book'].replace(" ", "").lower()
        if entry_book == normalized_book and int(entry['chapter']) == int(chapter):
            return i
    return None


async def handle_after_playback(error, vcid, source):
    if error:
        print(f"Playback error: {error}")
        return

    # Safety buffer to wait before autoplay
    remaining_buffer = max(1.5, 10 - source.elapsed())  # waits 10s if audio was <10s
    await asyncio.sleep(remaining_buffer)

    next_index = playback_index.get(vcid, -1) + 1
    if 0 <= next_index < len(manifest_data):
        playback_index[vcid] = next_index
        next_entry = manifest_data[next_index]

        try:
            vc = voice_clients[vcid]
            new_source = SafeAudio(next_entry['url'])
            vc.play(new_source, after=lambda e: asyncio.run_coroutine_threadsafe(
                handle_after_playback(e, vcid, new_source), bot.loop
            ))

            ctx = playback_contexts.get(vcid)
            if ctx:
                await ctx.channel.send(f"▶️ Now playing: {next_entry['book']} {next_entry['chapter']}")
        except Exception as e:
            print(f"Error autoplaying next: {e}")


# --- MODIFIED play_entry with after callback ---
async def play_entry(interaction, index):
    try:
        entry = manifest_data[index]
        user_vc = interaction.user.voice.channel
        vcid = user_vc.id

        # If the bot is already connected to the same VC, reuse it
        if vcid in voice_clients and voice_clients[vcid].is_connected():
            vc = voice_clients[vcid]
        else:
            vc = await user_vc.connect()
            voice_clients[vcid] = vc

        playback_index[vcid] = index
        playback_contexts[vcid] = interaction

        if vc.is_playing():
            vc.stop()

        def after_playback(error):
    if error:
        print(f"Playback error: {error}")
        return

    next_index = playback_index.get(vcid, -1) + 1
    if 0 <= next_index < len(manifest_data):
        playback_index[vcid] = next_index
        next_entry = manifest_data[next_index]

        # Check if still connected
        if vc.is_connected():
            vc.play(FFmpegPCMAudio(next_entry['url']), after=after_playback)
            coro = interaction.followup.send(f"🎧 Auto-playing: {next_entry['book']} {next_entry['chapter']}")
            asyncio.run_coroutine_threadsafe(coro, bot.loop)
        else:
            print("❌ Skipping autoplay: bot is no longer connected to voice.")

# -------- AUTOCOMPLETE --------
async def book_autocomplete(interaction: discord.Interaction, current: str):
    books = sorted(set(entry["book"] for entry in manifest_data))
    return [app_commands.Choice(name=book, value=book) for book in books if current.lower() in book.lower()][:25]

async def chapter_autocomplete(interaction: discord.Interaction, current: str):
    book = interaction.namespace.book
    chapters = [entry['chapter'] for entry in manifest_data if entry['book'].lower() == book.lower()]
    unique_chapters = sorted(set(chapters))
    return [app_commands.Choice(name=str(ch), value=ch) for ch in unique_chapters if current in str(ch)][:25]

# -------- SLASH COMMANDS --------
@tree.command(name="play", description="Play a specific Bible chapter.")
@app_commands.describe(book="Book name", chapter="Chapter number")
@app_commands.autocomplete(book=book_autocomplete, chapter=chapter_autocomplete)
async def play(interaction: discord.Interaction, book: str, chapter: int):
    await interaction.response.defer(ephemeral=False)  # 👈 This prevents the timeout

    await fetch_manifest()
    index = get_index(book, chapter)
    if index is None:
        await interaction.followup.send("❌ Chapter not found in manifest.", ephemeral=True)
    else:
        await play_entry(interaction, index)


@tree.command(name="pause", description="Pause playback")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ Paused.")
    else:
        await interaction.response.send_message("⚠️ Nothing is playing.", ephemeral=True)

@tree.command(name="resume", description="Resume playback")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ Resumed.")
    else:
        await interaction.response.send_message("⚠️ Nothing to resume.", ephemeral=True)

@tree.command(name="stop", description="Stop playback")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
        await interaction.response.send_message("⏹️ Stopped and disconnected.")
    else:
        await interaction.response.send_message("⚠️ Not connected.", ephemeral=True)

@tree.command(name="next", description="Play next chapter")
async def next_chapter(interaction: discord.Interaction):
    gid = interaction.guild_id
    curr = playback_index.get(gid, -1) + 1
    if curr < len(manifest_data):
        await play_entry(interaction, curr)
    else:
     await interaction.followup.send(f"▶️ Now playing: {entry['book']} {entry['chapter']}")

@tree.command(name="prev", description="Play previous chapter")
async def prev_chapter(interaction: discord.Interaction):
    vcid = interaction.user.voice.channel.id
    curr = max(0, playback_index.get(gid, 1) - 1)
    await play_entry(interaction, curr)

@tree.command(name="bookmark", description="Bookmark current chapter")
async def bookmark(interaction: discord.Interaction):
    gid = interaction.guild_id
    index = playback_index.get(gid)
    if index is not None:
        entry = manifest_data[index]
        bookmarks[str(interaction.user.id)] = [entry['book'], entry['chapter']]
        await interaction.response.send_message(f"⭐ Bookmarked {entry['book']} {entry['chapter']}.")
    else:
        await interaction.response.send_message("⚠️ Nothing to bookmark.")

@tree.command(name="resume_bookmark", description="Resume last bookmark")
async def resume_bookmark(interaction: discord.Interaction):
    data = bookmarks.get(str(interaction.user.id))
    if data:
        await play(interaction, data[0], data[1])
    else:
        await interaction.response.send_message("❌ No bookmark found.")

@tree.command(name="list", description="List chapters")
@app_commands.describe(book="Optional book filter")
async def list_chapters(interaction: discord.Interaction, book: str = None):
    entries = [f"{e['book']} {e['chapter']}" for e in manifest_data if not book or e['book'].lower() == book.lower()]
    chunks = [entries[i:i+25] for i in range(0, len(entries), 25)]
    for chunk in chunks:
        await interaction.channel.send("\n".join(chunk))
    await interaction.response.send_message("✅ Listed.", ephemeral=True)

@tree.command(name="search", description="Search chapters")
async def search(interaction: discord.Interaction, keyword: str):
    results = [f"{e['book']} {e['chapter']}" for e in manifest_data if keyword.lower() in e['book'].lower()]
    await interaction.response.send_message("\n".join(results) if results else "❌ No match found.")

@tree.command(name="devotion", description="Play a random Bible chapter")
async def devotion(interaction: discord.Interaction):
    await fetch_manifest()
    chapter = random.choice(manifest_data)
    index = get_index(chapter['book'], chapter['chapter'])
    if index is not None:
        await play_entry(interaction, index)
    else:
        await interaction.response.send_message("❌ Failed to locate a chapter for devotion.", ephemeral=True)


@tree.command(name="books", description="List Bible books")
async def books(interaction: discord.Interaction, testament: str = None):
    old_books = ["Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job", "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi"]
    new_books = ["Matthew", "Mark", "Luke", "John", "Acts", "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation"]
    books = old_books if testament == "old" else new_books if testament == "new" else old_books + new_books
    await interaction.response.send_message("\n".join(books))

@tree.command(name="settings", description="Set server settings")
@app_commands.describe(voice_channel="Default VC", devotion_hour="Hour (0-23)")
async def settings(interaction: discord.Interaction, voice_channel: discord.VoiceChannel = None, devotion_hour: int = None):
    gid = interaction.guild_id
    if gid not in settings_store:
        settings_store[gid] = {}
    if voice_channel:
        settings_store[gid]["voice_channel_id"] = voice_channel.id
    if devotion_hour is not None and 0 <= devotion_hour <= 23:
        settings_store[gid]["devotion_hour"] = devotion_hour
    msg = ["🔧 Settings updated:"]
    if voice_channel:
        msg.append(f"• Voice Channel: {voice_channel.name}")
    if devotion_hour is not None:
        msg.append(f"• Devotion Hour: {devotion_hour}:00")
    await interaction.response.send_message("\n".join(msg))


# -------- START --------
if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise EnvironmentError("❌ BOT_TOKEN not set in environment variables.")
    bot.run(TOKEN)
