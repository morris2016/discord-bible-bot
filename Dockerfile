# Use the official Node.js image
FROM node:18

# Set working directory
WORKDIR /app

# Copy dependency files and install
COPY package*.json ./
RUN npm install

# Install FFmpeg and libsodium for voice/audio support
RUN apt-get update && \
    apt-get install -y ffmpeg libsodium-dev && \
    apt-get clean

# Copy all remaining files into the container
COPY . .

# Start the bot
CMD ["node", "index.js"]
