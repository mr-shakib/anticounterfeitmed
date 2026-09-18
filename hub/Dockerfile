# syntax=docker/dockerfile:1
# The project hub: a static entry page, the app install page, and the app build.
#
# Served from a container rather than a host directory so nginx needs no access
# into a user's home, and so updating it is a rebuild rather than a privileged
# file copy.
FROM nginx:alpine

COPY hub/ /usr/share/nginx/html/
RUN rm -f /usr/share/nginx/html/Dockerfile

# The APK must arrive as an Android package, or a phone opens it as a download
# of unknown type instead of offering to install it.
RUN printf '%s\n' \
    'server {' \
    '  listen 8080;' \
    '  root /usr/share/nginx/html;' \
    '  index index.html;' \
    '  location = /app { try_files /app.html =404; }' \
    '  location = /app/anticounterfeitmed.apk {' \
    '    alias /usr/share/nginx/html/anticounterfeitmed.apk;' \
    '    default_type application/vnd.android.package-archive;' \
    '    add_header Content-Disposition '"'"'attachment; filename="anticounterfeitmed.apk"'"'"';' \
    '  }' \
    '  location / { try_files $uri $uri/ =404; }' \
    '}' > /etc/nginx/conf.d/default.conf

EXPOSE 8080
