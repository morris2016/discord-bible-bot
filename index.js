const { Client, GatewayIntentBits } = require('discord.js');
const {
  joinVoiceChannel,
  createAudioPlayer,
  createAudioResource,
  AudioPlayerStatus
} = require('@discordjs/voice');
require('dotenv').config();

// ✅ Your Cloudflare R2 public URL base
const BASE_URL = 'https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/';

// ✅ Manually list all 100 files or generate dynamically if you have a list
const audioFiles = [
  'B01___01_Matthew_____ENGNKJN1DA.mp3',
  'B08___10_2CorinthiansENGNKJN1DA.mp3',
  // Add all others here
];

const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates] });

const CHANNEL_ID = process.env.CHANNEL_ID;

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
    if (index >= audioFiles.length) return console.log("✅ Finished all files.");
    const fileUrl = `${BASE_URL}${audioFiles[index]}`;
    console.log(`🎧 Now streaming: ${fileUrl}`);

    const resource = createAudioResource(fileUrl);
    player.play(resource);
    index++;
  };

  player.on(AudioPlayerStatus.Idle, playNext);
  player.on('error', error => console.error('❌ Audio Error:', error.message));

  connection.subscribe(player);
  playNext();
});

console.log("📛 TOKEN:", process.env.TOKEN ? "Found" : "Missing");
console.log("🎧 CHANNEL_ID:", process.env.CHANNEL_ID ? "Found" : "Missing");

client.login(process.env.TOKEN);
