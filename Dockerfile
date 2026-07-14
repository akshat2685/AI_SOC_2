FROM node:22-alpine

WORKDIR /app

# Copy dependency files
COPY package*.json ./
COPY frontend/package*.json ./frontend/

# Install dependencies
RUN npm install
RUN cd frontend && npm install

# Copy application code
COPY . .

# Build the frontend
RUN npm run build

# Expose port 3000 (Cloud Run listens on the PORT env var, which defaults to 8080 but we can map it)
# By default, we use 3000 because our app handles process.env.PORT || 3000
EXPOSE 3000

ENV NODE_ENV=production

# Start the application
CMD ["npm", "start"]
