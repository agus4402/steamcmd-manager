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
# /home/steam/Steam is the steamcmd cache (also a named volume). Both must exist
# AND be owned by steam here so Docker initializes the named volumes with steam
# ownership; otherwise the mountpoint is auto-created as root and steamcmd (uid
# 1000) fails to write its downloads with "I/O Operation Failed".
RUN mkdir -p /data /home/steam/Steam \
    && chown steam:steam /data /home/steam/Steam

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
# Game-specific prestart hooks (see PRESTART_HOOK in entrypoint.sh).
COPY hooks/ /opt/hooks/
# Normalize CRLF -> LF so the scripts run even if checked out on Windows, then
# make them executable.
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh /opt/hooks/*.sh \
    && chmod +x /usr/local/bin/entrypoint.sh /opt/hooks/*.sh

USER steam
ENV STEAMCMD_DIR=/home/steam/steamcmd \
    INSTALL_DIR=/data

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
