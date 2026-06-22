FROM nginx:alpine

# Custom config (no proxy needed — browser calls backend:8000 directly)
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Static files (build context = repo root)
COPY index.html style.css app.js /usr/share/nginx/html/
COPY engine/ /usr/share/nginx/html/engine/

EXPOSE 80
