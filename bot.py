import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
from discord.ui import Button, View
import aiohttp
import asyncio
import os
import time
from mutagen.oggvorbis import OggVorbis
from urllib.request import urlopen
from tempfile import NamedTemporaryFile

# === GLOBAL STATE ===
manifest_data = []
voice_clients = {}
playback_index = {}
playback_contexts = {}
active_verse_tasks = {}
last_panel_message = {}

MANIFEST_URL = "https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/manifest.json"

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# === AUDIO WRAPPER ===
class SafeAudio(FFmpegPCMAudio):
    def __init__(self, source_url):
        before_opts = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        options = "-vn -af apad=pad_dur=2"
        super().__init__(source_url, before_options=before_opts, options=options)
        try:
            with urlopen(source_url) as response, NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(response.read())
                tmp_file.flush()
                audio = OggVorbis(tmp_file.name)
                self.duration = audio.info.length
                self.tempfile_path = tmp_file.name
        except Exception as e:
            print(f"Audio error: {e}")
            self.duration = 60
            self.tempfile_path = None
        self.start_time = time.time()

    def elapsed(self):
        return time.time() - self.start_time

    def cleanup(self):
        if self.tempfile_path and os.path.exists(self.tempfile_path):
            os.remove(self.tempfile_path)

# === UTILITIES ===
async def fetch_manifest():
    global manifest_data
    async with aiohttp.ClientSession() as session:
        async with session.get(MANIFEST_URL) as resp:
            if resp.status == 200:
                manifest_data = await resp.json()
                print(f"✅ Loaded {len(manifest_data)} chapters.")

def get_index(book: str, chapter: int):
    for i, entry in enumerate(manifest_data):
        if entry['book'].lower() == book.lower() and int(entry['chapter']) == int(chapter):
            return i
    return None

# === STREAMER ===
async def stream_verses(channel, timestamps, vcid):
    def overlapping_chunks(data, size, overlap=1):
        step = size - overlap
        for i in range(0, len(data), step):
            yield data[i:i + size]

    chunks = list(overlapping_chunks(timestamps, 7, overlap=1))

    for i, group in enumerate(chunks):
        wait = group[0]["start"] - (time.time() - stream_verses.start_time)
        if wait > 0:
            await asyncio.sleep(wait)
        if vcid not in active_verse_tasks or active_verse_tasks[vcid].cancelled():
            return

        verses = []
        for j, v in enumerate(group):
            verse = f"🔁 **{v['verse']}**. *{v['text']}*" if i > 0 and j == 0 else f"**{v['verse']}**. {v['text']}"
            verses.append(verse)

        embed = discord.Embed(
            title="📖 Scripture Reading",
            description="\n\n".join(verses),
            color=discord.Color.teal()
        )
        embed.set_footer(text=f"Verses {group[0]['verse']}–{group[-1]['verse']}")
        await channel.send(embed=embed)
        await asyncio.sleep(0.3)

# === PLAYBACK ===
async def handle_after_playback(error, vcid, source):
    if error:
        print(f"Error: {error}")
    await asyncio.sleep(max(1.5, 10 - source.elapsed()))
    source.cleanup()
    if vcid not in voice_clients or not voice_clients[vcid].is_connected():
        return
    next_index = playback_index.get(vcid, -1) + 1
    if next_index < len(manifest_data):
        ctx = playback_contexts.get(vcid)
        if ctx:
            await play_entry(ctx, next_index)

async def play_entry(ctx, index):
    entry = manifest_data[index]
    vcid = ctx.author.voice.channel.id

    vc = voice_clients.get(vcid)
    if not vc or not vc.is_connected():
        vc = await ctx.author.voice.channel.connect()
        voice_clients[vcid] = vc

    if vc.is_playing():
        vc.stop()
    if vcid in active_verse_tasks:
        active_verse_tasks[vcid].cancel()

    playback_index[vcid] = index
    playback_contexts[vcid] = ctx

    source = SafeAudio(entry["url"])
    vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
        handle_after_playback(e, vcid, source), bot.loop))

    await ctx.send(f"▶️ Now playing: **{entry['book']} {entry['chapter']}**")

    # ✅ Show control panel and autodelete old one
    await send_panel(ctx.channel)

    await asyncio.sleep(1.5)
    stream_verses.start_time = time.time()
    task = asyncio.create_task(stream_verses(ctx.channel, entry["timestamps"], vcid))
    active_verse_tasks[vcid] = task

# === COMMANDS ===
@bot.command()
async def play(ctx, book: str, chapter: str = '1'):
    try:
        chapter = int(chapter)
    except:
        return await ctx.send("❌ Invalid chapter.")
    index = get_index(book, chapter)
    if index is None:
        return await ctx.send("❌ Chapter not found.")
    await play_entry(ctx, index)

@bot.command()
async def panel(ctx):
    await send_panel(ctx.channel)

# === UI PANEL ===
async def send_panel(channel):
    class AudioControlPanel(View):
        def __init__(self):
            super().__init__(timeout=None)
            self.selected_book = None
            self.selected_chapter = 1
            self.chapter_page = 0
            self.book_page = 0
            self.all_chapters = []

            canonical_order = [
                "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
                "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
                "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
                "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah",
                "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel",
                "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
                "Haggai", "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John",
                "Acts", "Romans", "1 Corinthians", "2 Corinthians", "Galatians",
                "Ephesians", "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
                "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
                "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation"
            ]

            seen = set()
            all_books = [entry["book"] for entry in manifest_data]
            self.sorted_books = [book for book in canonical_order if book in all_books and not (book in seen or seen.add(book))]

            self.book_select = discord.ui.Select(placeholder="📚 Select a book...", options=[], row=0)
            self.book_select.callback = self.book_selected
            self.add_item(self.book_select)

            self.prev_book_page = Button(label="⬅️ Book Page", style=discord.ButtonStyle.secondary, row=1)
            self.next_book_page = Button(label="➡️ Book Page", style=discord.ButtonStyle.secondary, row=1)
            self.prev_book_page.callback = self.prev_book
            self.next_book_page.callback = self.next_book
            self.add_item(self.prev_book_page)
            self.add_item(self.next_book_page)

            self.chapter_select = discord.ui.Select(placeholder="🔢 Select chapter...", options=[discord.SelectOption(label="1")], row=2)
            self.chapter_select.callback = self.chapter_changed
            self.add_item(self.chapter_select)

            self.prev_button = Button(label="⬅️ Chapter Page", style=discord.ButtonStyle.secondary, row=3)
            self.next_button = Button(label="➡️ Chapter Page", style=discord.ButtonStyle.secondary, row=3)
            self.prev_button.callback = self.prev_page
            self.next_button.callback = self.next_page
            self.add_item(self.prev_button)
            self.add_item(self.next_button)

            self.play_button = Button(label="▶️ Play", style=discord.ButtonStyle.green, row=4)
            self.pause_button = Button(label="⏸ Pause", style=discord.ButtonStyle.blurple, row=4)
            self.resume_button = Button(label="▶ Resume", style=discord.ButtonStyle.green, row=4)
            self.stop_button = Button(label="⏹ Stop", style=discord.ButtonStyle.red, row=4)
            self.play_button.callback = self.play
            self.pause_button.callback = self.pause
            self.resume_button.callback = self.resume
            self.stop_button.callback = self.stop
            self.add_item(self.play_button)
            self.add_item(self.pause_button)
            self.add_item(self.resume_button)
            self.add_item(self.stop_button)

            self.update_book_dropdown()

        def update_book_dropdown(self):
            start = self.book_page * 25
            end = start + 25
            sliced = self.sorted_books[start:end]
            self.book_select.options = [discord.SelectOption(label=book) for book in sliced]

        async def book_selected(self, interaction):
            self.selected_book = self.book_select.values[0]
            self.all_chapters = sorted({int(e["chapter"]) for e in manifest_data if e["book"] == self.selected_book})
            self.chapter_page = 0
            await self.update_chapter_dropdown()
            await interaction.response.edit_message(content=f"📘 {self.selected_book}", view=self)

        async def chapter_changed(self, interaction):
            self.selected_chapter = int(self.chapter_select.values[0])
            await interaction.response.edit_message(content=f"📘 {self.selected_book} {self.selected_chapter}", view=self)

        async def update_chapter_dropdown(self):
            start = self.chapter_page * 25
            end = start + 25
            self.chapter_select.options = [
                discord.SelectOption(label=str(ch)) for ch in self.all_chapters[start:end]
            ]

        async def prev_book(self, interaction):
            if self.book_page > 0:
                self.book_page -= 1
                self.update_book_dropdown()
                await interaction.response.edit_message(view=self)

        async def next_book(self, interaction):
            max_pages = (len(self.sorted_books) - 1) // 25
            if self.book_page < max_pages:
                self.book_page += 1
                self.update_book_dropdown()
                await interaction.response.edit_message(view=self)

        async def prev_page(self, interaction):
            if self.chapter_page > 0:
                self.chapter_page -= 1
                await self.update_chapter_dropdown()
                await interaction.response.edit_message(view=self)

        async def next_page(self, interaction):
            max_pages = (len(self.all_chapters) - 1) // 25
            if self.chapter_page < max_pages:
                self.chapter_page += 1
                await self.update_chapter_dropdown()
                await interaction.response.edit_message(view=self)

        async def play(self, interaction):
            await interaction.response.send_message("▶️ Playing...", ephemeral=True)
            if not interaction.user.voice or not interaction.user.voice.channel:
                return await interaction.followup.send("❌ Join a VC first.", ephemeral=True)
            index = get_index(self.selected_book, self.selected_chapter)
            if index is None:
                return await interaction.followup.send("❌ Not found.", ephemeral=True)
            ctx = await bot.get_context(interaction.message)
            ctx.author = interaction.user
            await play_entry(ctx, index)

        async def pause(self, interaction):
            vc = interaction.guild.voice_client
            if vc and vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸ Paused.", ephemeral=True)

        async def resume(self, interaction):
            vc = interaction.guild.voice_client
            if vc and vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶ Resumed.", ephemeral=True)

        async def stop(self, interaction):
            vc = interaction.guild.voice_client
            if vc:
                vc.stop()
                await vc.disconnect()
                await interaction.response.send_message("⏹ Stopped.", ephemeral=True)

    if channel.id in last_panel_message:
        try:
            await last_panel_message[channel.id].delete()
        except:
            pass

    panel_msg = await channel.send("🎛️ Bible Audio Control Panel", view=AudioControlPanel())
    await channel.send("🔗 **Join us & discuss Scripture:** https://discord.gg/py6neEZa98")
    last_panel_message[channel.id] = panel_msg

# === READY EVENT ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await fetch_manifest()

# === LAUNCH BOT ===
bot.run(os.getenv("BOT_TOKEN"))  # ✅ For Railway / Heroku deploy
