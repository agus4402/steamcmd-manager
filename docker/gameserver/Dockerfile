# Reusable base image for ANY SteamCMD dedicated server.
# App ID, startup command and variables are injected at runtime via env vars
# (see entrypoint.sh) — nothing game-specific is baked in here.
FROM debian:bookworm-slim

# steamcmd requires 32-bit libs even for 64-bit servers (lib32gcc-s1).
# ca-certificates + tzdata for TLS/clock; locales avoids steamcmd warnings.
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        locales \
        tzdata \
        curl \
        lib32gcc-s1 \
        lib32stdc++6 \
        libsdl2-2.0-0:i386 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user expected by Steam tooling.
RUN useradd -m -u 1000 steam
WORKDIR /home/steam

# Install steamcmd into /home/steam/steamcmd.
RUN mkdir -p /home/steam/steamcmd \
    && curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" \
        | tar zxvf - -C /home/steam/steamcmd \
    && chown -R steam:steam /home/steam

# /data is the per-server install dir (mounted as a named volume by the panel).
RUN mkdir -p /data && chown steam:steam /data

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER steam
ENV STEAMCMD_DIR=/home/steam/steamcmd \
    INSTALL_DIR=/data

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
