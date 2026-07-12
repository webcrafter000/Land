FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --silent --legacy-peer-deps
COPY . .
EXPOSE 5173 5174
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
