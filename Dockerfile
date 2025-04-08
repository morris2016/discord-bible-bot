# Use official Node.js LTS image
FROM node:18

# Set working directory inside container
WORKDIR /app

# Copy dependency files first and install (for better caching)
COPY package*.json ./
RUN npm install

# Copy all source files including audio
COPY . .

# Optional: debug - list contents of public_audio during build
RUN ls -l /app/public_audio || echo "⚠️ public_audio folder not found"

# Set environment variables if needed (optional; Railway uses its own ENV system)
# ENV TOKEN=your_token_here
# ENV CHANNEL_ID=your_channel_id_here

# Start the bot
CMD ["node", "index.js"]
