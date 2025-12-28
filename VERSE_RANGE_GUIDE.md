# Verse Range Feature Guide

## Overview

Your Bible Audio Bot now supports playing specific verses or verse ranges instead of entire chapters! This feature allows for precise, targeted audio playback.

## How It Works

The bot automatically:
1. **Parses verse references** - Understands various verse reference formats
2. **Calculates timestamps** - Determines when each verse starts and ends
3. **Seeks audio precisely** - Uses FFmpeg to play only the requested verses
4. **Filters verse display** - Shows only the verses that are being played

## Command Formats

### Basic Verse Range
```
!play john 3:3-5
```
Plays verses 3 through 5 of John chapter 3.

### Single Verse
```
!play john 3:16
```
Plays only verse 16 of John chapter 3.

### Multiple Individual Verses
```
!play john 3:3,5,7
```
Plays verses 3, 5, and 7 of John chapter 3.

### Complex Combination
```
!play john 3:3-5,8,10-12
```
Plays verses 3-5, then verse 8, then verses 10-12 of John chapter 3.

### Multiple Chapters
```
!play john 3:3-5, matt 5:3-8
```
Plays John 3:3-5 followed by Matthew 5:3-8.

## Common Use Cases

### Famous Passages
```bash
# The Great Commission
!play matt 28:18-20

# The Lord's Prayer
!play matt 6:9-13

# Love Chapter
!play 1co 13:4-7

# Romans Road
!play rom 3:23, rom 5:8, rom 6:23, rom 10:9-10, rom 5:1
```

### Teaching Segments
```bash
# Parables
!play matt 13:3-23

# Beatitudes
!play matt 5:3-12

# Ten Commandments
!play exo 20:3-17
```

### Devotional Readings
```bash
# Daily Prayer
!play matt 6:9-13

# Comfort Verses
!play psa 23:1-6

# Hope Verses
!play jer 29:11-13, rom 8:28, phil 4:13
```

## Queue Feature with Verse Ranges

You can queue multiple verse ranges just like whole chapters:

```bash
!queue john 3:3-5    # Queue John 3:3-5
!queue matt 5:3-8    # Queue Matthew 5:3-8
!play                # Start playing the Tips for Best queue
```

## Results

1. **Use Abbreviations**: Common book abbreviations work (rom, gen, exo, psa, etc.)
2. **Check Verse Numbers**: Make sure verse numbers exist in the chapter
3. **Queue Multiple Ranges**: For longer devotionals, queue several verse ranges
4. **Combine Related Verses**: Use comma separation for verses that go together

## Technical Details

- **Audio Seeking**: The bot uses FFmpeg to seek to precise timestamps
- **Verse Calculation**: Verse start/end times are calculated based on total chapter length
- **Error Handling**: Invalid verse references are caught and reported
- **Performance**: Verse range playback is as efficient as whole chapter playback

## Examples That Work

✅ **Working Commands**:
- `!play john 3:3-5`
- `!play gen 1:1-3,5-7`
- `!play psa 23:1-6`
- `!play matt 5:3-8, 6:9-13`
- `!queue rom 8:28-30, 1co 13:4-7`

❌ **Invalid Commands**:
- `!play john 3:999` (verse doesn't exist)
- `!play john 0:3` (chapter doesn't exist)
- `!play invalidbook 3:3` (book doesn't exist)

## Troubleshooting

If a verse range doesn't work:
1. Check that the book name is correct
2. Verify the chapter exists
3. Confirm the verse numbers are valid for that chapter
4. Try the whole chapter first: `!play john 3`

The bot will provide helpful error messages for invalid references.