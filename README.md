# Bible Audio Bot

A Discord bot that plays Bible audio verses with precise verse-level control.

## Features

- **Whole Chapter Playback**: Play entire chapters with `!play john 3`
- **Verse Range Playback**: Play specific verse ranges with `!play john 3:3-5`
- **Multiple Verses**: Play individual verses with `!play john 3:3,5,7`
- **Complex Ranges**: Combine ranges and individual verses with `!play john 3:3-5,8,10-12`
- **Queue Support**: Add multiple references to the playback queue
- **Precise Audio Seeking**: Automatically seeks to correct timestamps in audio files
- **Verse Filtering**: Only displays requested verses in chat

## Commands

### Basic Commands
- `!join` - Join the voice channel
- `!play <reference>` - Play Bible audio (chapter, verse, or verse range)
- `!queue <reference>` - Add to playback queue without playing immediately
- `!pause` - Pause playback
- `!resume` - Resume playback
- `!stop` - Stop playback and clear queue
- `!skip` - Skip to next item in queue
- `!leave` - Leave the voice channel

### Queue Management
- `!queue show` - Display current queue
- `!queue clear` - Clear the queue

### Search Commands
- `!search <book> <chapter>:<verse>` - Search for specific verses
- `!list <book> <chapter>` - List all verses in a chapter
- `!books` - List all available Bible books

## Supported Reference Formats

The bot supports flexible Bible reference formats:

1. **Whole Chapter**: `!play john 3`
2. **Single Verse**: `!play john 3:3`
3. **Verse Range**: `!play john 3:3-5`
4. **Multiple Individual Verses**: `!play john 3:3,5,7`
5. **Complex Combinations**: `!play john 3:3-5,8,10-12`
6. **Multiple Chapters**: `!play john 3:3-5, matt 5:3-8`

### Examples

```bash
# Play the famous "For God so loved the world" passage
!play john 3:3-5

# Play the Beatitudes
!play matt 5:3-8

# Play Romans 8:28-30
!play rom 8:28-30

# Play Genesis creation account
!play gen 1:1-5

# Play multiple individual verses
!play psa 23:1,4,6

# Combine ranges and individual verses
!play 1co 13:4-7,13

# Queue multiple references
!queue john 3:3-5
!queue rom 8:28-30
```

## Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure your Discord bot token in environment variables
4. Run the bot: `python bot.py`

## Requirements

- Python 3.7+
- discord.py
- FFmpeg (for audio processing)
- Bible audio files in MP3 format

## Configuration

Set the following environment variables:
- `DISCORD_BOT_TOKEN` - Your Discord bot token
- `AUDIO_DIRECTORY` - Path to directory containing Bible audio files

## Audio File Structure

Organize audio files in the following structure:
```
audio_directory/
├── Genesis/
│   ├── 1.mp3
│   ├── 2.mp3
│   └── ...
├── Exodus/
├── Matthew/
└── ...
```

## Bot Permissions

The bot requires the following permissions in Discord:
- Join voice channels
- Speak in voice channels
- Send messages in text channels
- Read message history