FROM node:18

# Install system dependencies
RUN apt-get update && apt-get install -y \
  libsodium-dev \
  && apt-get clean

# Set work directory
WORKDIR /app

# Copy dependencies and install
COPY package*.json ./
RUN npm install

# Copy app source
COPY . .

# Start bot
CMD ["node", "index.js"]
