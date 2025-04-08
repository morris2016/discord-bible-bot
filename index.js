const { Client, GatewayIntentBits } = require('discord.js');
const { joinVoiceChannel, createAudioPlayer, createAudioResource, AudioPlayerStatus } = require('@discordjs/voice');
require('dotenv').config();

console.log("🚀 Bot is starting...");

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates],
});

const CHANNEL_ID = process.env.CHANNEL_ID;
const AUDIO_URL = 'https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/B08___10_2CorinthiansENGNKJN1DA.mp3';

client.once('ready', async () => {
  console.log("✅ Logged in as", client.user.tag);

  const voiceChannel = client.channels.cache.get(CHANNEL_ID);
  if (!voiceChannel || voiceChannel.type !== 2) {
    return console.error('❌ Voice channel not found or invalid type.');
  }

  const connection = joinVoiceChannel({
    channelId: voiceChannel.id,
    guildId: voiceChannel.guild.id,
    adapterCreator: voiceChannel.guild.voiceAdapterCreator,
  });

  const player = createAudioPlayer();
  const resource = createAudioResource(AUDIO_URL);

  player.play(resource);
  connection.subscribe(player);

  player.on(AudioPlayerStatus.Playing, () => {
    console.log('🎧 Audio is now playing.');
  });

  player.on(AudioPlayerStatus.Idle, () => {
    console.log('✅ Playback finished. Leaving channel.');
    connection.destroy();
  });

  player.on('error', error => {
    console.error('🔥 Error playing audio:', error.message);
  });
});

console.log("📛 TOKEN:", process.env.TOKEN ? "Found" : "Missing");
console.log("🎧 CHANNEL_ID:", process.env.CHANNEL_ID ? "Found" : "Missing");

client.login(process.env.TOKEN);
