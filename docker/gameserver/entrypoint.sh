#!/usr/bin/env bash
# Generic entrypoint for a SteamCMD dedicated server container.
#
# Behaviour is driven entirely by environment variables injected by the panel:
#   STEAM_APP_ID         (required for install) Steam dedicated-server App ID
#   STEAM_LOGIN_USER     Steam account (default: "anonymous")
#   STEAM_LOGIN_PASSWORD Steam password (only for non-anonymous; never logged)
#   STEAM_GUARD_CODE     Steam Guard 2FA code (only when required; never logged)
#   INSTALL_DIR          install/force_install_dir target (default: /data)
#   RUN_INSTALL          "1" => run steamcmd app_update before anything else
#   VALIDATE             "1" => add "validate" to app_update (integrity check)
#   INSTALL_ONLY         "1" => exit after install (one-shot install/update job)
#   STEAM_BRANCH         Steam beta branch for app_update (-beta); empty = public
#   STARTUP_CMD          command to exec to launch the server (rendered by panel)
#   PRESTART_HOOK        name of a game-specific script in /opt/hooks run right
#                        before launch (e.g. writes the game's config file)
#
# Credentials are passed positionally to steamcmd and are NEVER echoed.
set -euo pipefail

STEAMCMD_DIR="${STEAMCMD_DIR:-/home/steam/steamcmd}"
INSTALL_DIR="${INSTALL_DIR:-/data}"
STEAM_LOGIN_USER="${STEAM_LOGIN_USER:-anonymous}"

log() { echo "[entrypoint] $*"; }

run_steamcmd() {
    if [ -z "${STEAM_APP_ID:-}" ]; then
        log "ERROR: STEAM_APP_ID is required to install/update"
        exit 2
    fi

    # Build the login fragment without ever printing the password / guard code.
    local login_args=("+login" "${STEAM_LOGIN_USER}")
    if [ "${STEAM_LOGIN_USER}" != "anonymous" ]; then
        login_args+=("${STEAM_LOGIN_PASSWORD:-}")
        if [ -n "${STEAM_GUARD_CODE:-}" ]; then
            login_args+=("${STEAM_GUARD_CODE}")
        fi
        log "logging in as user '${STEAM_LOGIN_USER}' (credentials hidden)"
    else
        log "logging in anonymously"
    fi

    local update_args=("+app_update" "${STEAM_APP_ID}")
    if [ -n "${STEAM_BRANCH:-}" ]; then
        if [[ ! "${STEAM_BRANCH}" =~ ^[A-Za-z0-9_.-]{1,64}$ ]]; then
            log "ERROR: invalid STEAM_BRANCH '${STEAM_BRANCH}'"
            exit 2
        fi
        update_args+=("-beta" "${STEAM_BRANCH}")
        log "using Steam branch '${STEAM_BRANCH}'"
    fi
    if [ "${VALIDATE:-0}" = "1" ]; then
        update_args+=("validate")
    fi

    log "installing/updating App ID ${STEAM_APP_ID} into ${INSTALL_DIR} ..."

    # On a fresh steamcmd-cache volume the first run self-updates and restarts
    # ("Restarting steamcmd by request..."); in that restarted session the app
    # metadata is cold and +app_update fails with "Missing configuration". The
    # next run finds steamcmd current and the appinfo cached, so it succeeds.
    # Retry a few times to absorb this (and transient Steam hiccups).
    local max_attempts=3
    local attempt=1
    local rc=0
    while [ "${attempt}" -le "${max_attempts}" ]; do
        log "steamcmd attempt ${attempt}/${max_attempts} for App ID ${STEAM_APP_ID}"
        # force_install_dir MUST come before +login (steamcmd requirement).
        set +e
        "${STEAMCMD_DIR}/steamcmd.sh" \
            +force_install_dir "${INSTALL_DIR}" \
            "${login_args[@]}" \
            "${update_args[@]}" \
            +quit
        rc=$?
        set -e

        if [ "${rc}" -eq 0 ]; then
            log "steamcmd finished for App ID ${STEAM_APP_ID}"
            return 0
        fi

        log "steamcmd attempt ${attempt} failed (exit ${rc})"
        attempt=$((attempt + 1))
        [ "${attempt}" -le "${max_attempts}" ] && sleep 5
    done

    log "ERROR: steamcmd failed for App ID ${STEAM_APP_ID} after ${max_attempts} attempts (exit ${rc})"
    exit "${rc}"
}

run_workshop_download() {
    # One-shot Steam Workshop item download. Driven by:
    #   WORKSHOP_APP_ID       Steam app whose workshop content is fetched
    #   WORKSHOP_ITEM_ID      workshop item id to download
    #   WORKSHOP_INSTALL_PATH where to place it under INSTALL_DIR (relative)
    if [ -z "${WORKSHOP_APP_ID:-}" ] || [ -z "${WORKSHOP_ITEM_ID:-}" ]; then
        log "ERROR: WORKSHOP_APP_ID and WORKSHOP_ITEM_ID are required"
        exit 2
    fi

    local login_args=("+login" "${STEAM_LOGIN_USER}")
    if [ "${STEAM_LOGIN_USER}" != "anonymous" ]; then
        login_args+=("${STEAM_LOGIN_PASSWORD:-}")
        [ -n "${STEAM_GUARD_CODE:-}" ] && login_args+=("${STEAM_GUARD_CODE}")
        log "logging in as user '${STEAM_LOGIN_USER}' (credentials hidden)"
    else
        log "logging in anonymously"
    fi

    log "downloading workshop item ${WORKSHOP_ITEM_ID} for app ${WORKSHOP_APP_ID} ..."
    local rc=0
    set +e
    "${STEAMCMD_DIR}/steamcmd.sh" \
        "${login_args[@]}" \
        +workshop_download_item "${WORKSHOP_APP_ID}" "${WORKSHOP_ITEM_ID}" \
        +quit
    rc=$?
    set -e
    if [ "${rc}" -ne 0 ]; then
        log "ERROR: steamcmd workshop download failed (exit ${rc})"
        exit "${rc}"
    fi

    # steamcmd writes items to <steam root>/steamapps/workshop/content/<app>/<item>.
    # The root varies by build, so probe the known locations.
    local rel="steamapps/workshop/content/${WORKSHOP_APP_ID}/${WORKSHOP_ITEM_ID}"
    local src=""
    for base in "/home/steam/Steam" "${STEAMCMD_DIR}" "/home/steam/.steam/steam"; do
        if [ -d "${base}/${rel}" ]; then src="${base}/${rel}"; break; fi
    done
    if [ -z "${src}" ]; then
        log "ERROR: downloaded item not found on disk after steamcmd reported success"
        exit 4
    fi

    local dest="${INSTALL_DIR}/${WORKSHOP_INSTALL_PATH:-steamapps/workshop}/${WORKSHOP_ITEM_ID}"
    log "installing workshop item into ${dest}"
    mkdir -p "$(dirname "${dest}")"
    rm -rf "${dest}"
    cp -a "${src}" "${dest}"
    log "workshop item ${WORKSHOP_ITEM_ID} ready"
}

if [ "${WORKSHOP_DOWNLOAD:-0}" = "1" ]; then
    run_workshop_download
    exit 0
fi

if [ "${RUN_INSTALL:-0}" = "1" ] || [ "${INSTALL_ONLY:-0}" = "1" ]; then
    run_steamcmd
fi

if [ "${INSTALL_ONLY:-0}" = "1" ]; then
    log "INSTALL_ONLY set — exiting after install"
    exit 0
fi

if [ -z "${STARTUP_CMD:-}" ]; then
    log "ERROR: STARTUP_CMD is empty and INSTALL_ONLY not set — nothing to run"
    exit 3
fi

log "starting server: ${STARTUP_CMD}"

# Valheim (and other Unity/Steamworks games) look for steamclient.so in
# ~/.steam/sdk64. SteamCMD ships it but doesn't install it there automatically.
mkdir -p /home/steam/.steam/sdk64 /home/steam/.steam/sdk32
STEAMCMD_SDK64="${STEAMCMD_DIR}/linux64/steamclient.so"
STEAMCMD_SDK32="${STEAMCMD_DIR}/linux32/steamclient.so"
[ -f "${STEAMCMD_SDK64}" ] && ln -sf "${STEAMCMD_SDK64}" /home/steam/.steam/sdk64/steamclient.so
[ -f "${STEAMCMD_SDK32}" ] && ln -sf "${STEAMCMD_SDK32}" /home/steam/.steam/sdk32/steamclient.so

cd "${INSTALL_DIR}"

# Steamworks dedicated servers (Valheim, etc.) ship libsteam_api.so alongside the
# binary in ./linux64 and expect it on the loader path. The official launch
# scripts do this manually; we set it generically so templates don't have to.
export LD_LIBRARY_PATH="${INSTALL_DIR}/linux64:${INSTALL_DIR}:${LD_LIBRARY_PATH:-}"

# Game-specific pre-launch hook (baked into the image, never user-supplied):
# e.g. write the game's config file from the panel's variables/ports/mods.
if [ -n "${PRESTART_HOOK:-}" ]; then
    hook="/opt/hooks/${PRESTART_HOOK}.sh"
    if [[ ! "${PRESTART_HOOK}" =~ ^[A-Za-z0-9_]+$ ]] || [ ! -f "${hook}" ]; then
        log "ERROR: unknown prestart hook '${PRESTART_HOOK}'"
        exit 3
    fi
    log "running prestart hook ${PRESTART_HOOK}"
    bash "${hook}"
fi

# Run through bash -c so the rendered startup string (already validated by the
# panel against a placeholder whitelist) is interpreted as a command line.
exec bash -c "${STARTUP_CMD}"
