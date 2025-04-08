require("libsodium-wrappers").ready;
const { Client, GatewayIntentBits } = require("discord.js");
const {
  joinVoiceChannel,
  createAudioPlayer,
  createAudioResource,
  AudioPlayerStatus,
} = require("@discordjs/voice");
const fetch = require("node-fetch");
require("dotenv").config();

console.log("🚀 Bot is starting...");

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates],
});

const CHANNEL_ID = process.env.CHANNEL_ID;
const MANIFEST_URL = process.env.MANIFEST_URL;
const AUDIO_BASE = process.env.AUDIO_BASE;

console.log("📛 TOKEN:", process.env.TOKEN ? "Found" : "Missing");
console.log("🎧 CHANNEL_ID:", CHANNEL_ID ? "Found" : "Missing");
console.log("📦 MANIFEST_URL:", MANIFEST_URL || "❌ Not Set");
console.log("🔗 AUDIO_BASE:", AUDIO_BASE || "❌ Not Set");

client.once("ready", async () => {
  console.log("✅ Logged in as " + client.user.tag);

  const voiceChannel = client.channels.cache.get(CHANNEL_ID);
  if (!voiceChannel || voiceChannel.type !== 2) {
    return console.error("❌ Invalid or missing voice channel.");
  }

  const connection = joinVoiceChannel({
    channelId: voiceChannel.id,
    guildId: voiceChannel.guild.id,
    adapterCreator: voiceChannel.guild.voiceAdapterCreator,
  });

  try {
    const res = await fetch(MANIFEST_URL);
    const manifest = await res.json();

    const files = manifest.files || manifest;
    if (!files || !Array.isArray(files) || files.length === 0) {
      return console.error("❌ No files in manifest");
    }

    console.log("📦 Manifest fetched:", files.slice(0, 10), "...");

    const player = createAudioPlayer();
    let index = 0;

    const playNext = () => {
      const filename = files[index];
      const audioUrl = AUDIO_BASE + filename;
      console.log("🎧 Now playing:", audioUrl);

      const resource = createAudioResource(audioUrl, {
        inlineVolume: false,
      });

      player.play(resource);
      index = (index + 1) % files.length;
    };

    player.on(AudioPlayerStatus.Idle, () => {
      setTimeout(playNext, 500); // slight delay to prevent overlap
    });

    player.on("error", (err) => {
      console.error("⚠️ FFmpeg error:", err.message);
      setTimeout(playNext, 1000); // skip to next
    });

    connection.subscribe(player);
    playNext();
  } catch (err) {
    console.error("❌ Failed to fetch or parse manifest:", err.message);
  }
});

client.login(process.env.TOKEN);
