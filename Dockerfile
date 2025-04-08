# Use official Node.js image
FROM node:18

# Install necessary OS packages
RUN apt-get update && \
    apt-get install -y ffmpeg libsodium-dev && \
    apt-get clean

# Set working directory
WORKDIR /app

# Copy dependencies and install
COPY package*.json ./
RUN npm install

# Copy remaining files
COPY . .

# Run the bot
CMD ["node", "index.js"]
