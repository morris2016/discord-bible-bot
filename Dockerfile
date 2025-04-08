FROM node:18

WORKDIR /app

COPY package*.json ./
RUN npm install

# Add ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

COPY . .

CMD ["node", "index.js"]
