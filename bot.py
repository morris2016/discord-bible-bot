import discord
from discord.ext import commands
from discord import FFmpegPCMAudio, app_commands
from discord.ui import Button, View
import aiohttp
import asyncio
import os
import time
import re
import subprocess
import tempfile
import socket
import traceback
from mutagen.oggvorbis import OggVorbis
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from tempfile import NamedTemporaryFile

# === GLOBAL STATE ===
manifest_data = []
voice_clients = {}
playback_index = {}
playback_contexts = {}
active_verse_tasks = {}
last_panel_message = {}
pause_state = {}  # Track pause timing for each voice client
# Format: {vcid: {'total_pause_time': float, 'pause_start_time': float | None}}
playback_queue = {}  # Queue chapters for each voice client
# Format: {vcid: [chapter_index1, chapter_index2, ...]}
verse_range_playback = {}  # Track verse range playback
# Format: {vcid: {'start_verse': int, 'end_verse': int, 'stop_after': bool}}

MANIFEST_URL = "https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/manifest.json"

# === VERSE RANGE PARSING ===
def parse_verse_reference(verse_ref):
    """
    Parse verse references like "3-5", "3", "1-2,5,8-10" (verse part only)
    Returns tuple: (start_verse, end_verse, specific_verses)
    """
    verse_ref = verse_ref.strip()
    
    # Parse verse ranges (verse part only, not full chapter:verse)
    specific_verses = set()
    ranges = verse_ref.split(',')
    
    for range_item in ranges:
        range_item = range_item.strip()
        if '-' in range_item:
            # Handle ranges like "13-14"
            try:
                start_verse, end_verse = map(int, range_item.split('-'))
                if start_verse <= 0 or end_verse <= 0:
                    return None, None, []
                specific_verses.update(range(start_verse, end_verse + 1))
            except (ValueError, IndexError):
                return None, None, []
        else:
            # Handle single verses like "13"
            try:
                verse_num = int(range_item)
                if verse_num <= 0:
                    return None, None, []
                specific_verses.add(verse_num)
            except ValueError:
                return None, None, []
    
    if not specific_verses:
        return None, None, []
    
    min_verse = min(specific_verses)
    max_verse = max(specific_verses)
    
    return min_verse, max_verse, sorted(list(specific_verses))

def get_verse_start_time(timestamps, target_verse):
    """Get the start time for a specific verse from timestamps"""
    if not timestamps or not isinstance(timestamps, list):
        print("⚠️ Invalid timestamps array")
        return 0.0
    
    for timestamp in timestamps:
        if not isinstance(timestamp, dict):
            continue
        if timestamp.get('verse') == target_verse:
            return float(timestamp.get('start', 0.0))
    
    print(f"⚠️ Verse {target_verse} not found in timestamps")
    return 0.0

def get_verse_end_time(timestamps, target_verse):
    """Get the end time for a specific verse from timestamps"""
    if not timestamps or not isinstance(timestamps, list):
        print("⚠️ Invalid timestamps array")
        return None
    
    for i, timestamp in enumerate(timestamps):
        if not isinstance(timestamp, dict):
            continue
        if timestamp.get('verse') == target_verse:
            # If this is the last verse, use the chapter duration
            if i + 1 < len(timestamps):
                next_start = timestamps[i + 1].get('start')
                if next_start is not None:
                    return float(next_start)
            # Estimate end time based on verse duration
            return float(timestamp.get('start', 0.0)) + 30.0  # Assume ~30 seconds per verse max
    
    print(f"⚠️ Verse {target_verse} not found in timestamps")
    return None

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# === ENHANCED AUDIO WRAPPER WITH TIMESTAMP SEEKING ===
class SafeAudioWithSeek(FFmpegPCMAudio):
    def __init__(self, source_url, seek_time=None, end_time=None, method='hybrid'):
        # Validate inputs
        if not source_url or not isinstance(source_url, str):
            raise ValueError("Invalid audio URL")
        if not source_url.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        if seek_time and (seek_time < 0 or seek_time > 86400):  # Max 24 hours
            raise ValueError("Invalid seek_time: must be between 0 and 86400 seconds")
        if end_time and seek_time and end_time <= seek_time:
            raise ValueError("end_time must be greater than seek_time")
        
        self.seek_time = max(0, seek_time) if seek_time else 0
        self.end_time = end_time
        self.method = method
        self.tempfile_path = None
        
        # Build FFmpeg options with safer formatting
        before_opts = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        options = "-vn -af apad=pad_dur=2"
        
        if self.seek_time > 0:
            before_opts += f" -ss {self.seek_time:.2f}"
        
        if end_time and end_time > self.seek_time:
            duration = end_time - self.seek_time
            options += f" -t {duration:.2f}"
        
        try:
            super().__init__(source_url, before_options=before_opts, options=options)
        except Exception as e:
            print(f"❌ FFmpeg initialization error: {e}")
            raise
        
        try:
            # Try to get duration information
            if seek_time:
                # For seeking, we'll use a simplified duration estimation
                self.duration = (end_time - seek_time) if end_time else 60.0
            else:
                # Get actual duration for non-seeked audio
                with urlopen(source_url, timeout=30) as response:
                    with NamedTemporaryFile(delete=False) as tmp_file:
                        tmp_file.write(response.read())
                        tmp_file.flush()
                        audio = OggVorbis(tmp_file.name)
                        self.duration = audio.info.length
                        self.tempfile_path = tmp_file.name
        except (URLError, HTTPError, socket.timeout) as e:
            print(f"🔌 Network error downloading audio metadata: {e}")
            self.duration = 60
            self.tempfile_path = None
        except Exception as e:
            print(f"⚠️ Audio metadata error: {e}")
            self.duration = 60
            self.tempfile_path = None
        
        self.start_time = time.time()

    def elapsed(self):
        return time.time() - self.start_time

    def cleanup(self):
        try:
            if self.tempfile_path and os.path.exists(self.tempfile_path):
                os.remove(self.tempfile_path)
                self.tempfile_path = None
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

class SafeAudio(FFmpegPCMAudio):
    def __init__(self, source_url):
        # Validate URL
        if not source_url or not isinstance(source_url, str):
            raise ValueError("Invalid audio URL")
        if not source_url.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        
        before_opts = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        options = "-vn -af apad=pad_dur=2"
        
        try:
            super().__init__(source_url, before_options=before_opts, options=options)
        except Exception as e:
            print(f"❌ FFmpeg initialization error: {e}")
            raise
        
        try:
            with urlopen(source_url, timeout=30) as response:
                with NamedTemporaryFile(delete=False) as tmp_file:
                    tmp_file.write(response.read())
                    tmp_file.flush()
                    audio = OggVorbis(tmp_file.name)
                    self.duration = audio.info.length
                    self.tempfile_path = tmp_file.name
        except (URLError, HTTPError, socket.timeout) as e:
            print(f"🔌 Network error downloading audio metadata: {e}")
            self.duration = 60
            self.tempfile_path = None
        except Exception as e:
            print(f"⚠️ Audio metadata error: {e}")
            self.duration = 60
            self.tempfile_path = None
        
        self.start_time = time.time()

    def elapsed(self):
        return time.time() - self.start_time

    def cleanup(self):
        try:
            if self.tempfile_path and os.path.exists(self.tempfile_path):
                os.remove(self.tempfile_path)
                self.tempfile_path = None
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

# === UTILITIES ===
async def fetch_manifest():
    global manifest_data
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(MANIFEST_URL) as resp:
                    if resp.status == 200:
                        manifest_data = await resp.json()
                        print(f"✅ Loaded {len(manifest_data)} chapters.")
                        return
                    else:
                        print(f"⚠️ Manifest fetch failed with status {resp.status}")
        except asyncio.TimeoutError:
            print(f"⏱️ Manifest fetch timeout (attempt {attempt + 1}/{max_retries})")
        except aiohttp.ClientError as e:
            print(f"🔌 Network error fetching manifest: {e}")
        except Exception as e:
            print(f"❌ Unexpected error fetching manifest: {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    print("❌ Failed to fetch manifest after retries")

def cleanup_voice_state(vcid):
    """Centralized cleanup for voice channel state"""
    if vcid in voice_clients:
        del voice_clients[vcid]
    if vcid in playback_index:
        del playback_index[vcid]
    if vcid in playback_contexts:
        del playback_contexts[vcid]
    if vcid in active_verse_tasks:
        try:
            active_verse_tasks[vcid].cancel()
        except:
            pass
        del active_verse_tasks[vcid]
    if vcid in pause_state:
        del pause_state[vcid]
    if vcid in playback_queue:
        del playback_queue[vcid]
    if vcid in verse_range_playback:
        del verse_range_playback[vcid]

async def ensure_voice_connection(ctx, vcid):
    """Ensure voice connection with retry logic"""
    vc = voice_clients.get(vcid)
    
    if vc and vc.is_connected():
        return vc
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if vc:
                try:
                    await vc.disconnect(force=True)
                except:
                    pass
            
            vc = await ctx.author.voice.channel.connect(timeout=10.0, reconnect=True)
            voice_clients[vcid] = vc
            return vc
        except asyncio.TimeoutError:
            print(f"⏱️ Voice connection timeout (attempt {attempt + 1}/{max_retries})")
        except discord.ClientException as e:
            print(f"🔌 Voice connection error: {e}")
        except Exception as e:
            print(f"❌ Unexpected voice connection error: {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(1)
    
    raise ConnectionError("Failed to establish voice connection after retries")

def get_index(book: str, chapter: int):
    # Normalize book name for better matching
    normalized_book = book.lower().strip()
    
    # Handle books with numbers (1, 2, 3 John, Peter, etc.)
    number_words = {
        '1': '1', '2': '2', '3': '3',
        'one': '1', 'two': '2', 'three': '3'
    }
    
    # Comprehensive book abbreviations
    book_abbreviations = {
        # Old Testament
        'gen': 'genesis', 'gen.': 'genesis', 'gn': 'genesis',
        'exo': 'exodus', 'exo.': 'exodus', 'ex': 'exodus',
        'lev': 'leviticus', 'lev.': 'leviticus', 'lv': 'leviticus',
        'num': 'numbers', 'num.': 'numbers', 'nm': 'numbers',
        'deu': 'deuteronomy', 'deu.': 'deuteronomy', 'dt': 'deuteronomy',
        'jos': 'joshua', 'jos.': 'joshua', 'js': 'joshua',
        'jud': 'judges', 'jud.': 'judges', 'jdg': 'judges',
        'rut': 'ruth', 'rut.': 'ruth', 'rt': 'ruth',
        '1sam': '1 samuel', '1sam.': '1 samuel', '1sa': '1 samuel',
        '2sam': '2 samuel', '2sam.': '2 samuel', '2sa': '2 samuel',
        '1kin': '1 kings', '1kin.': '1 kings', '1ki': '1 kings',
        '2kin': '2 kings', '2kin.': '2 kings', '2ki': '2 kings',
        '1chr': '1 chronicles', '1chr.': '1 chronicles', '1ch': '1 chronicles',
        '2chr': '2 chronicles', '2chr.': '2 chronicles', '2ch': '2 chronicles',
        'ezr': 'ezra', 'ezr.': 'ezra',
        'neh': 'nehemiah', 'neh.': 'nehemiah',
        'est': 'esther', 'est.': 'esther',
        'job': 'job',
        'psa': 'psalms', 'psa.': 'psalms', 'ps': 'psalms',
        'pro': 'proverbs', 'pro.': 'proverbs', 'pr': 'proverbs',
        'ecc': 'ecclesiastes', 'ecc.': 'ecclesiastes', 'ec': 'ecclesiastes',
        'sos': 'song of solomon', 'sos.': 'song of solomon', 'so': 'song of solomon',
        'isa': 'isaiah', 'isa.': 'isaiah',
        'jer': 'jeremiah', 'jer.': 'jeremiah',
        'lam': 'lamentations', 'lam.': 'lamentations',
        'ezk': 'ezekiel', 'ezk.': 'ezekiel',
        'dan': 'daniel', 'dan.': 'daniel',
        'hos': 'hosea', 'hos.': 'hosea',
        'joe': 'joel', 'joe.': 'joel',
        'amo': 'amos', 'amo.': 'amos',
        'oba': 'obadiah', 'oba.': 'obadiah', 'ob': 'obadiah',
        'jon': 'jonah', 'jon.': 'jonah',
        'mic': 'micah', 'mic.': 'micah',
        'nah': 'nahum', 'nah.': 'nahum',
        'hab': 'habakkuk', 'hab.': 'habakkuk',
        'zep': 'zephaniah', 'zep.': 'zephaniah',
        'hag': 'haggai', 'hag.': 'haggai',
        'zec': 'zechariah', 'zec.': 'zechariah',
        'mal': 'malachi', 'mal.': 'malachi',
        
        # New Testament
        'mat': 'matthew', 'mat.': 'matthew', 'mt': 'matthew',
        'mar': 'mark', 'mar.': 'mark', 'mk': 'mark',
        'luk': 'luke', 'luk.': 'luke', 'lk': 'luke',
        'joh': 'john', 'joh.': 'john', 'jn': 'john',
        'act': 'acts', 'act.': 'acts', 'ac': 'acts',
        'rom': 'romans', 'rom.': 'romans', 'ro': 'romans',
        '1co': '1 corinthians', '1co.': '1 corinthians',
        '2co': '2 corinthians', '2co.': '2 corinthians',
        'gal': 'galatians', 'gal.': 'galatians',
        'eph': 'ephesians', 'eph.': 'ephesians',
        'phi': 'philippians', 'phi.': 'philippians', 'ph': 'philippians',
        'col': 'colossians', 'col.': 'colossians',
        '1th': '1 thessalonians', '1th.': '1 thessalonians',
        '2th': '2 thessalonians', '2th.': '2 thessalonians',
        '1ti': '1 timothy', '1ti.': '1 timothy',
        '2ti': '2 timothy', '2ti.': '2 timothy',
        'tit': 'titus', 'tit.': 'titus',
        'phm': 'philemon', 'phm.': 'philemon', 'phm': 'philemon',
        'heb': 'hebrews', 'heb.': 'hebrews',
        'jam': 'james', 'jam.': 'james', 'jas': 'james',
        '1pe': '1 peter', '1pe.': '1 peter',
        '2pe': '2 peter', '2pe.': '2 peter',
        '1jo': '1 john', '1jo.': '1 john',
        '2jo': '2 john', '2jo.': '2 john',
        '3jo': '3 john', '3jo.': '3 john',
        'jud': 'jude', 'jud.': 'jude',
        'rev': 'revelation', 'rev.': 'revelation',
        
        # Common short abbreviations
        'pet': 'peter', 'pet.': 'peter',
        'john': 'john', 'john.': 'john',
        'matt': 'matthew', 'matt.': 'matthew',
        'mark': 'mark', 'mark.': 'mark',
        'luke': 'luke', 'luke.': 'luke',
        'acts': 'acts', 'acts.': 'acts',
        'rom': 'romans', 'rom.': 'romans',
        'cor': 'corinthians', 'cor.': 'corinthians',
        'gal': 'galatians', 'gal.': 'galatians',
        'eph': 'ephesians', 'eph.': 'ephesians',
        'phi': 'philippians', 'phi.': 'philippians',
        'col': 'colossians', 'col.': 'colossians',
        'thess': 'thessalonians', 'thess.': 'thessalonians',
        'tim': 'timothy', 'tim.': 'timothy',
        'tit': 'titus', 'tit.': 'titus',
        'heb': 'hebrews', 'heb.': 'hebrews',
        'jam': 'james', 'jam.': 'james',
        'jude': 'jude', 'jude.': 'jude',
        'rev': 'revelation', 'rev.': 'revelation'
    }
    
    # Check if the book is an abbreviation first
    if normalized_book in book_abbreviations:
        normalized_book = book_abbreviations[normalized_book]
    
    # Try exact match first
    for i, entry in enumerate(manifest_data):
        if entry['book'].lower() == normalized_book and int(entry['chapter']) == int(chapter):
            return i
    
    # Try fuzzy matching for books with numbers
    book_parts = normalized_book.split()
    
    if len(book_parts) >= 2:
        # Check if first part is a number
        first_part = book_parts[0]
        
        if first_part in number_words:
            number = number_words[first_part]
            remaining_parts = book_parts[1:]
            
            # Try "X Bookname" format
            for i, entry in enumerate(manifest_data):
                entry_book = entry['book'].lower()
                
                # Check if it starts with the number
                if entry_book.startswith(number + ' '):
                    book_part = entry_book[len(number) + 1:].strip()
                    expected_book = ' '.join(remaining_parts).strip()
                    
                    # Try exact match
                    if book_part == expected_book:
                        if int(entry['chapter']) == int(chapter):
                            return i
                    
                    # Try partial match (in case of extra words or slight differences)
                    elif expected_book in book_part or book_part in expected_book:
                        if int(entry['chapter']) == int(chapter):
                            return i
            
            # Try "Bookname X" format (like "Peter 2")
            for i, entry in enumerate(manifest_data):
                entry_book = entry['book'].lower()
                entry_parts = entry_book.split()
                if len(entry_parts) >= 2 and entry_parts[-1] == number:
                    book_name = ' '.join(entry_parts[:-1])
                    expected_book = ' '.join(remaining_parts)
                    
                    if (book_name == expected_book or 
                        expected_book in book_name or 
                        book_name in expected_book):
                        if int(entry['chapter']) == int(chapter):
                            return i
    
    # Try removing spaces and punctuation for compact formats
    compact_normalized = normalized_book.replace(' ', '').replace('.', '')
    for i, entry in enumerate(manifest_data):
        entry_compact = entry['book'].lower().replace(' ', '').replace('.', '')
        if entry_compact == compact_normalized and int(entry['chapter']) == int(chapter):
            return i
    
    return None

# === STREAMER ===
async def stream_verses(channel, timestamps, vcid):
    def overlapping_chunks(data, size, overlap=1):
        step = size - overlap
        for i in range(0, len(data), step):
            yield data[i:i + size]

    chunks = list(overlapping_chunks(timestamps, 7, overlap=1))
    base_start_time = time.time()
    
    for i, group in enumerate(chunks):
        vc = voice_clients.get(vcid)
        if not vc or not vc.is_connected():
            return
            
        # Calculate effective elapsed time accounting for pauses
        def get_effective_elapsed():
            current_elapsed = time.time() - base_start_time
            pause_info = pause_state.get(vcid, {'total_pause_time': 0.0, 'pause_start_time': None})
            # Subtract accumulated pause time
            current_elapsed -= pause_info['total_pause_time']
            # If currently paused, subtract the current pause duration too
            if pause_info['pause_start_time']:
                current_elapsed -= (time.time() - pause_info['pause_start_time'])
            return max(0, current_elapsed)  # Ensure non-negative

        while True:
            effective_elapsed = get_effective_elapsed()
            wait = group[0]["start"] - effective_elapsed
            if wait <= 0:
                break
            await asyncio.sleep(min(wait, 0.1))
            vc = voice_clients.get(vcid)
            if not vc or not vc.is_connected():
                return
                
        if vcid not in active_verse_tasks or active_verse_tasks[vcid].cancelled():
            return

        verses = []
        for j, v in enumerate(group):
            # Use elegant formatting with verse number and text
            if i > 0 and j == 0:
                # Repeated verse indicator with softer emphasis
                verse = f"🔁 **{v['verse']}**. *{v['text']}*"
            else:
                # Regular verse with clear number and readable text
                verse = f"**{v['verse']}**. {v['text']}"
            verses.append(verse)

        embed = discord.Embed(
            title="📖 Scripture Reading",
            description="\n\n".join(verses),
            color=discord.Color.from_rgb(106, 90, 205)  # Slate blue - elegant and readable
        )
        embed.set_footer(text=f"Verses {group[0]['verse']}–{group[-1]['verse']}")
        await channel.send(embed=embed)
        
        await asyncio.sleep(0.3)
    


# === PLAYBACK ===
async def handle_after_playback(error, vcid, source):
    if error:
        print(f"❌ Playback error (vcid={vcid}): {error}")
        traceback.print_exc()
    
    # Adaptive sleep based on actual playback duration
    actual_elapsed = source.elapsed()
    expected_duration = getattr(source, 'duration', 10)
    remaining = max(0.5, min(expected_duration - actual_elapsed, 10))
    
    await asyncio.sleep(remaining)
    
    try:
        source.cleanup()
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")
    
    # Check voice connection is still valid
    vc = voice_clients.get(vcid)
    if not vc or not vc.is_connected():
        print(f"🔌 Voice connection lost for vcid={vcid}")
        cleanup_voice_state(vcid)
        return
    
    # Check if this is verse range playback that should stop
    if vcid in verse_range_playback:
        range_info = verse_range_playback[vcid]
        if range_info.get('stop_after', False):
            # Verse range completed, stop playback and clean up
            vc = voice_clients[vcid]
            vc.stop()
            del verse_range_playback[vcid]
            if vcid in active_verse_tasks:
                active_verse_tasks[vcid].cancel()
                del active_verse_tasks[vcid]
            return
    
    # Check if there are queued chapters to play next
    if vcid in playback_queue and playback_queue[vcid]:
        next_item = playback_queue[vcid].pop(0)
        ctx = playback_contexts.get(vcid)
        if ctx:
            if isinstance(next_item, tuple):
                # Handle verse range in queue
                index, start_verse, end_verse = next_item
                await play_entry(ctx, index, start_verse, end_verse)
            else:
                # Handle regular chapter in queue
                await play_entry(ctx, next_item)
        return
    
    # Otherwise, play the next chapter from the manifest (sequential playback)
    next_index = playback_index.get(vcid, -1) + 1
    if next_index < len(manifest_data):
        ctx = playback_contexts.get(vcid)
        if ctx:
            await play_entry(ctx, next_index)

async def play_entry_with_verse_range(ctx, index, start_verse, end_verse):
    """Play a specific verse range from a chapter"""
    entry = manifest_data[index]
    vcid = ctx.author.voice.channel.id

    try:
        vc = await ensure_voice_connection(ctx, vcid)
    except ConnectionError as e:
        return await ctx.send(f"❌ {e}")

    # Check if something is already playing - if so, queue the new chapter
    if vc.is_playing() or vc.is_paused():
        if vcid not in playback_queue:
            playback_queue[vcid] = []
        playback_queue[vcid].append((index, start_verse, end_verse))
        await ctx.send(f"📝 Added to queue: **{entry['book']} {entry['chapter']}:{start_verse}-{end_verse}** (Position {len(playback_queue[vcid])})")
        return

    if vc.is_playing():
        vc.stop()
    if vcid in active_verse_tasks:
        active_verse_tasks[vcid].cancel()
    
    # Clean up pause state for new playback
    pause_state[vcid] = {'total_pause_time': 0.0, 'pause_start_time': None}

    playback_index[vcid] = index
    playback_contexts[vcid] = ctx

    # Calculate timestamps for verse range with contextual padding
    timestamps = entry["timestamps"]
    
    # Get all verses in the chapter to determine bounds
    all_verses = [t['verse'] for t in timestamps]
    min_verse = min(all_verses)
    max_verse = max(all_verses)
    
    # Extend range by one verse before and after for context
    # Handle edge cases where we can't extend before verse 1 or after the last verse
    audio_start_verse = max(start_verse - 1, min_verse)  # One verse before, but not before chapter start
    audio_end_verse = min(end_verse + 1, max_verse)      # One verse after, but not after chapter end
    
    # Calculate actual timing for the extended audio range
    start_time = get_verse_start_time(timestamps, audio_start_verse)
    end_time = get_verse_end_time(timestamps, audio_end_verse)
    
    # Use enhanced audio with seeking
    source = SafeAudioWithSeek(entry["url"], seek_time=start_time, end_time=end_time)
    vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
        handle_after_playback(e, vcid, source), bot.loop))

    await ctx.send(f"▶️ Now playing: **{entry['book']} {entry['chapter']}:{start_verse}-{end_verse}** (with context: {audio_start_verse}-{audio_end_verse})")

    # Show control panel and autodelete old one
    await send_panel(ctx.channel)
    
    # Filter timestamps for verse range display (original requested range only)
    filtered_timestamps = [t for t in timestamps if start_verse <= t['verse'] <= end_verse]
    
    # Adjust timestamps so first verse starts at 0.0s (for verse range playback)
    if filtered_timestamps:
        first_verse_start = filtered_timestamps[0]['start']
        for timestamp in filtered_timestamps:
            timestamp['start'] -= first_verse_start
    
    task = asyncio.create_task(stream_verses(ctx.channel, filtered_timestamps, vcid))
    active_verse_tasks[vcid] = task
    
    # Track verse range playback
    verse_range_playback[vcid] = {
        'start_verse': start_verse,
        'end_verse': end_verse,
        'stop_after': True
    }

async def play_entry(ctx, index, start_verse=None, end_verse=None):
    """Enhanced play_entry that supports verse ranges"""
    if start_verse is not None and end_verse is not None:
        return await play_entry_with_verse_range(ctx, index, start_verse, end_verse)
    
    # Original play_entry logic for full chapter playback
    entry = manifest_data[index]
    vcid = ctx.author.voice.channel.id

    try:
        vc = await ensure_voice_connection(ctx, vcid)
    except ConnectionError as e:
        return await ctx.send(f"❌ {e}")

    # Check if something is already playing - if so, queue the new chapter
    if vc.is_playing() or vc.is_paused():
        if vcid not in playback_queue:
            playback_queue[vcid] = []
        playback_queue[vcid].append(index)
        await ctx.send(f"📝 Added to queue: **{entry['book']} {entry['chapter']}** (Position {len(playback_queue[vcid])})")
        return

    if vc.is_playing():
        vc.stop()
    if vcid in active_verse_tasks:
        active_verse_tasks[vcid].cancel()
    
    # Clean up pause state for new playback
    pause_state[vcid] = {'total_pause_time': 0.0, 'pause_start_time': None}

    playback_index[vcid] = index
    playback_contexts[vcid] = ctx

    source = SafeAudio(entry["url"])
    vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
        handle_after_playback(e, vcid, source), bot.loop))

    await ctx.send(f"▶️ Now playing: **{entry['book']} {entry['chapter']}**")

    # ✅ Show control panel and autodelete old one
    await send_panel(ctx.channel)

    task = asyncio.create_task(stream_verses(ctx.channel, entry["timestamps"], vcid))
    active_verse_tasks[vcid] = task

# === COMMANDS ===
@commands.hybrid_command(description="Play a specific Bible chapter or verse range")
async def play(ctx, *, args: str):
    # Parse the arguments manually to handle multi-word book names
    parts = args.strip().split()
    if len(parts) < 1:
        return await ctx.send("❌ Please provide a book name and chapter or verse range.")
    
    # Check if last part contains verse reference (contains colon)
    last_part = parts[-1]
    start_verse = None
    end_verse = None
    
    if ':' in last_part:
        # Parse verse reference - support both formats:
        # Format 1: "john 3:3-5" (chapter:verse)
        # Format 2: "john 3 3-5" (chapter verse)
        chapter_verse = last_part.split(':')
        if len(chapter_verse) == 2:
            try:
                chapter = int(chapter_verse[0])
                verse_ref = chapter_verse[1]
                
                # Parse verse range
                start_verse, end_verse, specific_verses = parse_verse_reference(verse_ref)
                if start_verse is None:
                    return await ctx.send("❌ Invalid verse reference format. Use format like '2:13-14' or '2:13'.")
                
                book_parts = parts[:-1]  # Everything except the last part with verse reference
                book = ' '.join(book_parts)
            except (ValueError, IndexError):
                return await ctx.send("❌ Invalid chapter or verse format.")
        else:
            return await ctx.send("❌ Invalid verse reference format.")
    elif len(parts) >= 3 and parts[-2].isdigit() and any(c in parts[-1] for c in '-,'):
        # Handle format: "john 3 3-5" (book chapter verse_range)
        try:
            chapter = int(parts[-2])
            verse_ref = parts[-1]
            
            # Parse verse range
            start_verse, end_verse, specific_verses = parse_verse_reference(verse_ref)
            if start_verse is None:
                return await ctx.send("❌ Invalid verse reference format. Use format like 'john 3 3-5'.")
            
            book_parts = parts[:-2]  # Everything except the last two parts
            book = ' '.join(book_parts)
        except (ValueError, IndexError):
            return await ctx.send("❌ Invalid chapter or verse format.")
    else:
        # No verse reference, play full chapter
        try:
            chapter = int(parts[-1])
            book_parts = parts[:-1]
        except ValueError:
            # If the last part isn't a number, assume chapter 1
            chapter = 1
            book_parts = parts
        
        book = ' '.join(book_parts)
    
    index = get_index(book, chapter)
    if index is None:
        return await ctx.send("❌ Chapter not found.")
    
    if start_verse is not None and end_verse is not None:
        await play_entry(ctx, index, start_verse, end_verse)
    else:
        await play_entry(ctx, index)

@commands.hybrid_command(description="Show the Bible audio control panel")
async def panel(ctx):
    await send_panel(ctx.channel)

@commands.hybrid_command(description="Show current playback queue")
async def queue(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Join a VC first.")
    
    vcid = ctx.author.voice.channel.id
    if vcid not in playback_queue or not playback_queue[vcid]:
        return await ctx.send("📝 Queue is empty.")
    
    queue_list = []
    for i, item in enumerate(playback_queue[vcid], 1):
        if isinstance(item, tuple):
            # Handle verse range in queue
            index, start_verse, end_verse = item
            entry = manifest_data[index]
            queue_list.append(f"**{i}**. {entry['book']} {entry['chapter']}:{start_verse}-{end_verse}")
        else:
            # Handle regular chapter in queue
            entry = manifest_data[item]
            queue_list.append(f"**{i}**. {entry['book']} {entry['chapter']}")
    
    embed = discord.Embed(
        title="📋 Playback Queue",
        description="\n".join(queue_list),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Total: {len(playback_queue[vcid])} item(s)")
    await ctx.send(embed=embed)

@commands.hybrid_command(description="Pause current playback")
async def pause(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Join a VC first.")
    
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vcid = ctx.author.voice.channel.id
        vc.pause()
        # Track pause state for verse synchronization
        if vcid not in pause_state:
            pause_state[vcid] = {'total_pause_time': 0.0, 'pause_start_time': None}
        pause_state[vcid]['pause_start_time'] = time.time()
        await ctx.send("⏸ Paused.")
    else:
        await ctx.send("❌ Nothing is playing.")

@commands.hybrid_command(description="Resume paused playback")
async def resume(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Join a VC first.")
    
    vc = ctx.guild.voice_client
    if vc and vc.is_paused():
        vcid = ctx.author.voice.channel.id
        vc.resume()
        # Calculate and store accumulated pause time
        if vcid in pause_state and pause_state[vcid]['pause_start_time']:
            pause_duration = time.time() - pause_state[vcid]['pause_start_time']
            pause_state[vcid]['total_pause_time'] += pause_duration
            pause_state[vcid]['pause_start_time'] = None
        await ctx.send("▶ Resumed.")
    else:
        await ctx.send("❌ Nothing is paused.")

@commands.hybrid_command(description="Skip to next chapter in queue")
async def next(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Join a VC first.")
    
    vcid = ctx.author.voice.channel.id
    vc = ctx.guild.voice_client
    
    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await ctx.send("❌ Nothing is playing.")
    
    # Stop current playback
    vc.stop()
    
    # Clean up current verse task
    if vcid in active_verse_tasks:
        active_verse_tasks[vcid].cancel()
    
    # Clear pause state
    if vcid in pause_state:
        del pause_state[vcid]
    
    # Clear verse range playback state
    if vcid in verse_range_playback:
        del verse_range_playback[vcid]
    
    await ctx.send("⏭️ Skipped to next chapter.")

@commands.hybrid_command(description="Stop all playback and clear queue")
async def stop(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Join a VC first.")
    
    vcid = ctx.author.voice.channel.id
    vc = ctx.guild.voice_client
    
    if vc:
        vc.stop()
        await vc.disconnect()
        
        # Clean up all state
        if vcid in pause_state:
            del pause_state[vcid]
        if vcid in active_verse_tasks:
            active_verse_tasks[vcid].cancel()
            del active_verse_tasks[vcid]
        if vcid in playback_queue:
            del playback_queue[vcid]
        if vcid in verse_range_playback:
            del verse_range_playback[vcid]
        
        await ctx.send("⏹ Stopped and cleared queue.")
    else:
        await ctx.send("❌ Nothing is playing.")

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
            
            # Update main message to show current selection
            selection_text = f"📘 {self.selected_book} {self.selected_chapter}"
            await interaction.response.edit_message(content=selection_text, view=self)

        async def chapter_changed(self, interaction):
            self.selected_chapter = int(self.chapter_select.values[0])
            
            # Update main message to show current selection
            selection_text = f"📘 {self.selected_book} {self.selected_chapter}"
            await interaction.response.edit_message(content=selection_text, view=self)

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
                
                # Update main message to show current selection
                selection_text = f"📘 {self.selected_book} {self.selected_chapter}" if self.selected_book else "🎛️ Bible Audio Control Panel"
                await interaction.response.edit_message(content=selection_text, view=self)

        async def next_book(self, interaction):
            max_pages = (len(self.sorted_books) - 1) // 25
            if self.book_page < max_pages:
                self.book_page += 1
                self.update_book_dropdown()
                
                # Update main message to show current selection
                selection_text = f"📘 {self.selected_book} {self.selected_chapter}" if self.selected_book else "🎛️ Bible Audio Control Panel"
                await interaction.response.edit_message(content=selection_text, view=self)

        async def prev_page(self, interaction):
            if self.chapter_page > 0:
                self.chapter_page -= 1
                await self.update_chapter_dropdown()
                
                # Update main message to show current selection
                selection_text = f"📘 {self.selected_book} {self.selected_chapter}" if self.selected_book else "🎛️ Bible Audio Control Panel"
                await interaction.response.edit_message(content=selection_text, view=self)

        async def next_page(self, interaction):
            max_pages = (len(self.all_chapters) - 1) // 25
            if self.chapter_page < max_pages:
                self.chapter_page += 1
                await self.update_chapter_dropdown()
                
                # Update main message to show current selection
                selection_text = f"📘 {self.selected_book} {self.selected_chapter}" if self.selected_book else "🎛️ Bible Audio Control Panel"
                await interaction.response.edit_message(content=selection_text, view=self)

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
                vcid = interaction.guild.voice_client.channel.id
                vc.pause()
                # Track pause state for verse synchronization
                if vcid not in pause_state:
                    pause_state[vcid] = {'total_pause_time': 0.0, 'pause_start_time': None}
                pause_state[vcid]['pause_start_time'] = time.time()
                await interaction.response.send_message("⏸ Paused.", ephemeral=True)

        async def resume(self, interaction):
            vc = interaction.guild.voice_client
            if vc and vc.is_paused():
                vcid = interaction.guild.voice_client.channel.id
                vc.resume()
                # Calculate and store accumulated pause time
                if vcid in pause_state and pause_state[vcid]['pause_start_time']:
                    pause_duration = time.time() - pause_state[vcid]['pause_start_time']
                    pause_state[vcid]['total_pause_time'] += pause_duration
                    pause_state[vcid]['pause_start_time'] = None
                await interaction.response.send_message("▶ Resumed.", ephemeral=True)

        async def stop(self, interaction):
            vc = interaction.guild.voice_client
            if vc:
                vcid = interaction.guild.voice_client.channel.id
                vc.stop()
                await vc.disconnect()
                # Clean up all state
                if vcid in pause_state:
                    del pause_state[vcid]
                if vcid in active_verse_tasks:
                    active_verse_tasks[vcid].cancel()
                    del active_verse_tasks[vcid]
                if vcid in playback_queue:
                    del playback_queue[vcid]
                if vcid in verse_range_playback:
                    del verse_range_playback[vcid]
                await interaction.response.send_message("⏹ Stopped and cleared queue.", ephemeral=True)

    if channel.id in last_panel_message:
        try:
            await last_panel_message[channel.id].delete()
        except:
            pass

    panel_msg = await channel.send("🎛️ Bible Audio Control Panel", view=AudioControlPanel())
    last_panel_message[channel.id] = panel_msg

# === EVENTS ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await fetch_manifest()
    await bot.tree.sync()
    bot.add_command(play)
    bot.add_command(panel)
    bot.add_command(queue)
    bot.add_command(pause)
    bot.add_command(resume)
    bot.add_command(next)
    bot.add_command(stop)

@bot.event
async def on_voice_state_update(member, before, after):
    """Clean up when bot is disconnected from voice"""
    if member == bot.user and before.channel and not after.channel:
        vcid = before.channel.id
        cleanup_voice_state(vcid)
        print(f"🧹 Cleaned up state for voice channel {vcid}")

# === LAUNCH BOT ===
bot.run(os.getenv("BOT_TOKEN"))  # ✅ For Railway / Heroku deploy
