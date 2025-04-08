const { Client, GatewayIntentBits } = require('discord.js');
const { joinVoiceChannel, createAudioPlayer, createAudioResource, AudioPlayerStatus } = require('@discordjs/voice');
const { get } = require('https');
require('dotenv').config();

const MANIFEST_URL = 'https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/manifest.json';
const AUDIO_BASE_URL = 'https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/';
const CHANNEL_ID = process.env.CHANNEL_ID;
const TOKEN = process.env.TOKEN;

console.log("🚀 Bot starting up...");

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates],
});

const fetchJSON = (url) => {
  return new Promise((resolve, reject) => {
    get(url, res => {
      let data = '';
      res.on('data', chunk => (data += chunk));
      res.on('end', () => resolve(JSON.parse(data)));
    }).on('error', reject);
  });
};

client.once('ready', async () => {
  console.log(`✅ Logged in as ${client.user.tag}`);

  try {
    const audioFiles = await fetchJSON(MANIFEST_URL);
    if (!Array.isArray(audioFiles) || audioFiles.length === 0) {
      console.error("❌ Manifest is empty or invalid.");
      return;
    }

    const channel = client.channels.cache.get(CHANNEL_ID);
    if (!channel || channel.type !== 2) {
      console.error("❌ Voice channel not found or is not a voice type.");
      return;
    }

    const connection = joinVoiceChannel({
      channelId: channel.id,
      guildId: channel.guild.id,
      adapterCreator: channel.guild.voiceAdapterCreator,
    });

    const player = createAudioPlayer();
    let index = 0;

    const playNext = () => {
      if (index >= audioFiles.length) index = 0;
      const url = `${AUDIO_BASE_URL}${audioFiles[index]}`;
      console.log(`🎧 Now playing: ${audioFiles[index]}`);
      player.play(createAudioResource(url));
      index++;
    };

    player.on(AudioPlayerStatus.Idle, () => playNext());
    player.on('error', error => console.error("🎤 Audio error:", error.message));
    connection.subscribe(player);
    playNext();
  } catch (err) {
    console.error("❌ Failed to load manifest or start bot:", err);
  }
});

client.login(TOKEN);
