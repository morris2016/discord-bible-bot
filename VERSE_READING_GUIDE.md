# Verse-Level Reading Implementation Guide

## Overview

Your Discord Bible bot now supports **verse-level reading** with the hybrid timestamp seeking approach! Users can play specific verse ranges like `!play john 2:13-14` instead of only entire chapters.

## New Features

### ✅ Verse Range Commands
- **Single verse**: `!play john 2:13` - Plays verse 13 of John chapter 2
- **Verse range**: `!play john 2:13-14` - Plays verses 13-14 of John chapter 2
- **Complex ranges**: `!play john 2:13-15,17,20-22` - Plays multiple verse ranges
- **Full chapters**: `!play john 2` - Still works as before (plays entire chapter)

### ✅ Hybrid Timestamp Seeking
The implementation uses a **hybrid approach** for optimal performance and accuracy:

1. **Fast Seeking**: Uses FFmpeg's `-ss` parameter for quick timestamp seeking
2. **Fallback Support**: Built-in fallback system for high-accuracy requirements
3. **Range-based Stopping**: Automatically stops playback after completing the specified verse range
4. **Queue Support**: Verse ranges can be queued just like full chapters

### ✅ Enhanced Display
- **Filtered Verse Display**: Only shows verses from the specified range
- **Smart Timestamps**: Syncs verse display with audio seeking position
- **Range Indicators**: Shows range in playback notifications (e.g., "John 2:13-14")

## Technical Implementation

### New Components Added

#### 1. Verse Range Parsing (`parse_verse_reference`)
```python
def parse_verse_reference(verse_ref):
    # Handles formats like "2:13-14", "2:13", "2:13-15,17,20-22"
    # Returns: (start_verse, end_verse, specific_verses)
```

#### 2. Enhanced Audio Classes
- `SafeAudioWithSeek`: New class with timestamp seeking support
- `SafeAudio`: Original class for full chapter playback
- Supports both fast seeking and high-accuracy fallback

#### 3. Verse Range Playback Functions
- `play_entry_with_verse_range()`: Handles verse-specific playback
- `get_verse_start_time()`: Calculates start timestamps for verses
- `get_verse_end_time()`: Calculates end timestamps for verses

#### 4. State Management
- `verse_range_playback{}`: Tracks verse range playback state
- Enhanced queue system supporting both chapters and verse ranges
- Proper cleanup for verse range state

### Command Examples

| Command | Description | Example |
|---------|-------------|---------|
| `!play john 2` | Full chapter | Plays entire John chapter 2 |
| `!play john 2:13` | Single verse | Plays verse 13 of John 2 |
| `!play john 2:13-14` | Verse range | Plays verses 13-14 of John 2 |
| `!play john 2:13-15,17,20` | Complex range | Plays verses 13-15, 17, and 20 of John 2 |

### Queue Support

The bot now supports mixing chapters and verse ranges in the same queue:

```
📋 Playback Queue
1. John 2:13-14
2. John 3:16
3. Matthew 5:1-12
Total: 3 item(s)
```

## Usage Instructions

### For Users
1. **Join a voice channel**
2. **Use verse commands**:
   - `!play john 2:13-14` - Plays specific verses
   - `!play john 2` - Plays full chapter (backward compatible)
   - `!queue` - View mixed queue of chapters and verse ranges

### For Developers
The implementation is **fully backward compatible** - existing `!play john 2` commands work exactly as before.

#### Key Benefits:
- ✅ **No breaking changes** to existing functionality
- ✅ **Performance optimized** with hybrid seeking approach
- ✅ **Memory efficient** - no permanent storage of processed files
- ✅ **Flexible parsing** - supports various verse reference formats

#### Technical Notes:
- **Timestamp accuracy**: Uses existing verse timestamp data for precise seeking
- **Audio processing**: Leverages FFmpeg for efficient seeking
- **Error handling**: Graceful fallbacks for missing verses or invalid ranges
- **State management**: Proper cleanup prevents memory leaks

## Future Enhancements

Potential improvements for future versions:
- **Bookmark system**: Save favorite verse ranges
- **Cross-chapter ranges**: Support verses spanning multiple chapters
- **Speed control**: Adjust playback speed for verse ranges
- **Search integration**: Find verses by content and play them directly

The foundation is now solid for advanced verse-level features!