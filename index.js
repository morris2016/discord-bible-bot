const { Client, GatewayIntentBits } = require('discord.js');
const {
  joinVoiceChannel,
  createAudioPlayer,
  createAudioResource,
  AudioPlayerStatus
} = require('@discordjs/voice');
require('dotenv').config();

// ✅ Bot setup
const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates]
});

// ✅ Constants
const CHANNEL_ID = process.env.CHANNEL_ID;
const BASE_URL = 'https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/';

// ✅ List your audio filenames here
const audioFiles = [
  'B01___01_Matthew_____ENGNKJN1DA.mp3',
  'B01___02_Matthew_____ENGNKJN1DA.mp3',
  'B08___10_2CorinthiansENGNKJN1DA.mp3',
  // 🔁 Add more files as needed...
];

console.log("🚀 The bot code started running...");
console.log("📛 TOKEN:", process.env.TOKEN ? "Found" : "Missing");
console.log("🎧 CHANNEL_ID:", process.env.CHANNEL_ID ? "Found" : "Missing");

client.once('ready', async () => {
  console.log("✅ Bot is connected to Discord.");
  console.log(`Logged in as ${client.user.tag}`);

  const voiceChannel = client.channels.cache.get(CHANNEL_ID);
  if (!voiceChannel || voiceChannel.type !== 2) {
    return console.error('❌ Voice channel not found or is not a voice type.');
  }

  const connection = joinVoiceChannel({
    channelId: voiceChannel.id,
    guildId: voiceChannel.guild.id,
    adapterCreator: voiceChannel.guild.voiceAdapterCreator,
  });

  const player = createAudioPlayer();
  let index = 0;

  const playNext = () => {
    if (!audioFiles.length) return console.error('❌ No audio files found.');
    const filename = audioFiles[index];
    const fileUrl = BASE_URL + filename;

    console.log(`🎧 Now streaming: ${filename}`);

    const resource = createAudioResource(fileUrl);
    player.play(resource);
    index = (index + 1) % audioFiles.length;
  };

  player.on(AudioPlayerStatus.Idle, () => playNext());
  player.on('error', error => console.error('⚠️ Error:', error.message));

  connection.subscribe(player);
  playNext();
});

client.login(process.env.TOKEN);
