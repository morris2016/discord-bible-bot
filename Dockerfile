# Use official Node.js LTS image
FROM node:18

# Set working directory inside container
WORKDIR /app

# Copy dependency files first and install (for better caching)
COPY package*.json ./
RUN npm install

# Copy all source files
COPY . .
RUN rm -rf node_modules && npm install


# Start the bot
CMD ["node", "index.js"]