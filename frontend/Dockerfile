# Use Node image
FROM node:18-alpine

# Set working directory
WORKDIR /app

# Install dependencies first
COPY package.json package-lock.json* ./
RUN npm install

# Copy application source code
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Run Vite with --host to allow network access
CMD ["npm", "run", "dev", "--", "--host"]
