# Use an official Node.js image
FROM node:18

# Set working directory inside the container
WORKDIR /app

# Copy package.json and install dependencies
COPY package*.json ./
RUN npm install

# Copy rest of the project
COPY . .

# Expose port if needed (for local audio hosting)
EXPOSE 8000

# Start the bot
CMD ["node", "index.js"]