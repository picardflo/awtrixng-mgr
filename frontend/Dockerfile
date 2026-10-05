FROM node:22-alpine AS build
WORKDIR /srv/app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
# Les fichiers statiques servis tels quels — le favicon. Oubliés ici, ils
# existent en local et disparaissent de l'image : un défaut qu'aucun test du
# dépôt ne voit, puisque tout marche hors conteneur.
COPY public ./public
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /srv/app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
