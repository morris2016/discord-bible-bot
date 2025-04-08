# Use official Node.js image
FROM node:18

# Set working directory
WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Install system dependencies for Discord voice
RUN apt-get update && \
    apt-get install -y ffmpeg libsodium-dev && \
    apt-get clean

# Copy all remaining app files
COPY . .

# Start the bot
CMD ["node", "index.js"]
