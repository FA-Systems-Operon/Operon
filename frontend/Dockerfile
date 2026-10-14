FROM node:24-alpine

WORKDIR /app

RUN chown node:node /app

COPY --chown=node:node package.json package-lock.json ./
USER node
RUN npm ci --ignore-scripts

COPY --chown=node:node index.html vite.config.ts tsconfig.json tsconfig.node.json ./
COPY --chown=node:node src ./src

EXPOSE 5173
CMD ["npm", "run", "dev"]
