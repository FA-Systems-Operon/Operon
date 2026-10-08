# Builder stage: build React app
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies with security flags
# --ignore-scripts: prevent malicious lifecycle scripts
RUN npm install --ignore-scripts

# Copy source code
COPY . .

# Build the application
RUN npm run build --ignore-scripts

# Production stage: serve the built app
FROM node:20-alpine

WORKDIR /app

# Create non-root user and install serve in a single RUN to reduce layers
# Use UID/GID 1001 with -D (no password) and -H (no home dir)
# Lock serve to specific version (8.0.0) for reproducible builds
RUN addgroup -g 1001 appgroup && \
    adduser -D -u 1001 -G appgroup -s /sbin/nologin appuser && \
    npm install -g serve@8.0.0 --ignore-scripts && \
    npm cache clean --force

# Copy built app from builder
COPY --from=builder --chown=appuser:appgroup /app/dist ./dist

# Switch to non-root user
USER appuser

EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000 || exit 1

# Serve the app on port 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
