require("dotenv").config();
require("libsodium-wrappers").ready;

const fs = require("fs");
const path = require("path");
const fetch = require("node-fetch");
const { Client, GatewayIntentBits } = require("discord.js");
const {
  joinVoiceChannel,
  createAudioPlayer,
  createAudioResource,
  entersState,
  AudioPlayerStatus,
  VoiceConnectionStatus,
} = require("@discordjs/voice");

// === ENV VALIDATION ===
const REQUIRED_ENV = ["TOKEN", "CHANNEL_ID", "MANIFEST_URL", "AUDIO_BASE_URL"];
REQUIRED_ENV.forEach((key) => {
  if (!process.env[key]) {
    console.error(`❌ Missing required .env key: ${key}`);
    process.exit(1);
  }
});

// === GLOBALS ===
const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates] });
const player = createAudioPlayer();
let manifest = [];
let index = 0;
let retryCount = 0;
const MAX_RETRIES = 3;

// === UTILITIES ===
const log = (msg, type = "info") => {
  const now = new Date().toISOString();
  const label = type === "error" ? "❌" : type === "warn" ? "⚠️" : "ℹ️";
  console.log(`[${now}] ${label} ${msg}`);
};

// === FETCH MANIFEST WITH RETRIES ===
const fetchManifest = async () => {
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const res = await fetch(process.env.MANIFEST_URL);
      const json = await res.json();
      if (!Array.isArray(json)) throw new Error("Manifest is not an array");
      manifest = json;
      log(`📦 Manifest loaded with ${manifest.length} items.`);
      return;
    } catch (err) {
      log(`Attempt ${attempt} - Failed to fetch manifest: ${err.message}`, "warn");
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  log("🛑 Giving up on fetching manifest after retries.", "error");
  process.exit(1);
};

// === MAIN BOT LOGIC ===
client.once("ready", async () => {
  log(`✅ Logged in as ${client.user.tag}`);

  await fetchManifest();

  const channel = await client.channels.fetch(process.env.CHANNEL_ID).catch((err) => {
    log(`Failed to fetch channel: ${err.message}`, "error");
    process.exit(1);
  });

  if (!channel || channel.type !== 2) {
    log("Invalid or non-voice channel.", "error");
    process.exit(1);
  }

  const connection = joinVoiceChannel({
    channelId: channel.id,
    guildId: channel.guild.id,
    adapterCreator: channel.guild.voiceAdapterCreator,
  });

  connection.on("error", (err) => {
    log(`Voice connection error: ${err.message}`, "error");
  });

  try {
    await entersState(connection, VoiceConnectionStatus.Ready, 30_000);
    connection.subscribe(player);
    log("🔗 Voice connection ready.");
    playNext();
  } catch (err) {
    log(`Could not enter voice state: ${err.message}`, "error");
  }
});

// === PLAYBACK HANDLER ===
player.on(AudioPlayerStatus.Idle, () => {
  playNext();
});

player.on("error", (err) => {
  log(`AudioPlayer error: ${err.message}`, "error");
  playNext();
});

const playNext = () => {
  if (index >= manifest.length) {
    log("🎉 Playback complete.");
    return;
  }

  const filename = manifest[index++];
  const url = `${process.env.AUDIO_BASE_URL}/${filename}`;
  log(`🎧 Playing: ${url}`);

  try {
    const resource = createAudioResource(url, {
      inputType: undefined,
      inlineVolume: false,
    });

    player.play(resource);
  } catch (err) {
    log(`⚠️ Failed to load audio resource: ${err.message}`, "warn");
    setTimeout(playNext, 2000); // brief pause before retrying next
  }
};

// === ERROR CATCHERS ===
process.on("unhandledRejection", (err) => {
  log(`UnhandledRejection: ${err}`, "error");
});

process.on("uncaughtException", (err) => {
  log(`UncaughtException: ${err}`, "error");
});

client.login(process.env.TOKEN);
