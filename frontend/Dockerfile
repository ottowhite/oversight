# ---- builder: full deps (incl. devDependencies) so `next build` can run ----
FROM node:24-alpine AS builder

WORKDIR /app

# Copy package files first for better layer caching
COPY package*.json ./

# Install ALL dependencies (devDeps like typescript/@types are required to build)
RUN npm ci

# Copy source code
COPY . .

# Accept build argument for backend URL
ARG NEXT_PUBLIC_BACKEND_URL=http://oversight-backend:50
# Set environment variable for backend URL BEFORE building (required for Next.js build)
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL

# Build the Next.js application
RUN npm run build

# ---- runtime: lean image with prod-only deps ----
FROM node:24-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production

# Install only production dependencies (devDeps excluded → smaller image)
COPY package*.json ./
RUN npm ci --omit=dev

# Copy the build output and runtime config from the builder stage
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./next.config.js

# Expose port 3000
EXPOSE 3000

# Start the application
CMD ["npm", "start"]
