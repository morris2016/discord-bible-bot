require("dotenv").config();
const { Client, GatewayIntentBits } = require("discord.js");
const {
  joinVoiceChannel,
  createAudioPlayer,
  createAudioResource,
  AudioPlayerStatus,
  StreamType,
} = require("@discordjs/voice");

const fetch = require("node-fetch");
const ffmpeg = require("ffmpeg-static");
const { spawn } = require("child_process");

// ⏱️ Optional: Needed if you want sodium to work everywhere
require("libsodium-wrappers").ready;

console.log("🚀 Bot is starting...");

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates],
});

const CHANNEL_ID = process.env.CHANNEL_ID;
const MANIFEST_URL = process.env.MANIFEST_URL;
const AUDIO_BASE = process.env.AUDIO_BASE; // Ends with /

console.log("📛 TOKEN:", process.env.TOKEN ? "Found" : "Missing");
console.log("🎧 CHANNEL_ID:", CHANNEL_ID ? "Found" : "Missing");

client.once("ready", async () => {
  console.log(`✅ Logged in as ${client.user.tag}`);

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
    const files = manifest.files;

    if (!files || files.length === 0) {
      return console.error("❌ No files in manifest");
    }

    console.log("📦 Manifest fetched:", files);

    const player = createAudioPlayer();
    let index = 0;

    const playNext = () => {
      const url = `${AUDIO_BASE}${files[index]}`;
      console.log("🎧 Now playing:", url);

      const ffmpegProcess = spawn(ffmpeg, [
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", url,
        "-analyzeduration", "0",
        "-loglevel", "error",
        "-f", "s16le",
        "-ar", "48000",
        "-ac", "2"
      ], { stdio: ["pipe", "pipe", "inherit"] });

      const resource = createAudioResource(ffmpegProcess.stdout, {
        inputType: StreamType.Raw,
      });

      player.play(resource);
      index = (index + 1) % files.length;
    };

    player.on(AudioPlayerStatus.Idle, () => {
      console.log("⏭️ Track ended, playing next...");
      playNext();
    });

    player.on("error", (error) => {
      console.error("⚠️ Audio error:", error.message);
      playNext(); // Skip to next on error
    });

    connection.subscribe(player);
    playNext();
  } catch (err) {
    console.error("❌ Failed to fetch or parse manifest:", err.message);
  }
});

client.login(process.env.TOKEN);
