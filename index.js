require("libsodium-wrappers").ready;
const { Client, GatewayIntentBits } = require("discord.js");
const {
  joinVoiceChannel,
  createAudioPlayer,
  createAudioResource,
  AudioPlayerStatus,
  StreamType,
} = require("@discordjs/voice");
const fetch = require("node-fetch");
const prism = require("prism-media");
const ffmpeg = require("ffmpeg-static");
require("dotenv").config();

console.log("🚀 Bot is starting...");
const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates],
});

const CHANNEL_ID = process.env.CHANNEL_ID;
const MANIFEST_URL = process.env.MANIFEST_URL || "https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/manifest.json";
const AUDIO_BASE = process.env.AUDIO_BASE || "https://pub-9ced34a9f0ea4ebd9d5c6fe77774b23e.r2.dev/";

console.log("📛 TOKEN:", process.env.TOKEN ? "Found" : "Missing");
console.log("🎧 CHANNEL_ID:", CHANNEL_ID ? "Found" : "Missing");

client.once("ready", async () => {
  console.log("✅ Logged in as " + client.user.tag);

  const voiceChannel = client.channels.cache.get(CHANNEL_ID);
  if (!voiceChannel || voiceChannel.type !== 2) return console.error("❌ Invalid or missing voice channel.");

  const connection = joinVoiceChannel({
    channelId: voiceChannel.id,
    guildId: voiceChannel.guild.id,
    adapterCreator: voiceChannel.guild.voiceAdapterCreator,
  });

  try {
    const res = await fetch(MANIFEST_URL);
    const manifest = await res.json();
    const files = manifest.files || manifest;

    if (!files || files.length === 0) return console.error("❌ No files in manifest");

    console.log("📦 Manifest fetched:", files);
    const player = createAudioPlayer();
    let index = 0;

    const playNext = () => {
      const url = `${AUDIO_BASE}${files[index]}`;
      console.log("🎧 Now playing:", url);

      const stream = new prism.FFmpeg({
        args: [
          "-reconnect", "1",
          "-reconnect_streamed", "1",
          "-reconnect_delay_max", "5",
          "-i", url,
          "-analyzeduration", "0",
          "-loglevel", "0",
          "-f", "s16le",
          "-ar", "48000",
          "-ac", "2",
        ],
        executable: ffmpeg,
      });

      const resource = createAudioResource(stream, {
        inputType: StreamType.Raw,
      });

      player.play(resource);
      index = (index + 1) % files.length;
    };

    player.on(AudioPlayerStatus.Idle, playNext);
    player.on("error", (err) => {
      console.error("Audio error:", err.message);
      playNext(); // Skip on error
    });

    connection.subscribe(player);
    playNext();
  } catch (err) {
    console.error("❌ Failed to fetch or parse manifest:", err.message);
  }
});

client.login(process.env.TOKEN);
