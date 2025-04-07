const { Client, GatewayIntentBits } = require('discord.js');
const { joinVoiceChannel, createAudioPlayer, createAudioResource, AudioPlayerStatus } = require('@discordjs/voice');
const path = require('path');
const fs = require('fs');
require('dotenv').config();

console.log("🚀 The bot code started running...");

const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates] });

const CHANNEL_ID = process.env.CHANNEL_ID;
const AUDIO_DIR = path.join(__dirname, 'public_audio');

const audioFiles = fs.readdirSync(AUDIO_DIR)
  .filter(file => file.toLowerCase().endsWith('.mp3'))
  .sort();

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
    const file = audioFiles[index];
    const filePath = path.join(AUDIO_DIR, file);
    console.log(`🎧 Now playing: ${file}`);

    const resource = createAudioResource(filePath);
    player.play(resource);
    index = (index + 1) % audioFiles.length;
  };

  player.on(AudioPlayerStatus.Idle, () => playNext());
  player.on('error', error => console.error('Error:', error.message));

  connection.subscribe(player);
  playNext();
});

console.log("📛 TOKEN:", process.env.TOKEN ? "Found" : "Missing");
console.log("🎧 CHANNEL_ID:", process.env.CHANNEL_ID ? "Found" : "Missing");

client.login(process.env.TOKEN);
