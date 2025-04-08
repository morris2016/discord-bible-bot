# Use official Node.js LTS image
FROM node:18

# Install required system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg libsodium-dev && \
    apt-get clean

# Set working directory
WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy the rest of the project files
COPY . .

# Start the bot
CMD ["node", "index.js"]
