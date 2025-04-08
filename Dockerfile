# Use official Node.js LTS image
FROM node:18

# Set working directory inside container
WORKDIR /app

# Copy dependency files first and install
COPY package*.json ./
RUN npm install

# FORCE REBUILD: change something below to invalidate cache
# Dummy change 2025-04-08
COPY . .

# Debug: ensure files are copied
RUN ls -l /app/public_audio || echo "⚠️ public_audio folder not found"

CMD ["node", "index.js"]