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
#   STARTUP_CMD          command to exec to launch the server (rendered by panel)
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
    if [ "${VALIDATE:-0}" = "1" ]; then
        update_args+=("validate")
    fi

    log "installing/updating App ID ${STEAM_APP_ID} into ${INSTALL_DIR} ..."
    "${STEAMCMD_DIR}/steamcmd.sh" \
        +force_install_dir "${INSTALL_DIR}" \
        "${login_args[@]}" \
        "${update_args[@]}" \
        +quit
    log "steamcmd finished for App ID ${STEAM_APP_ID}"
}

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
cd "${INSTALL_DIR}"
# Run through bash -c so the rendered startup string (already validated by the
# panel against a placeholder whitelist) is interpreted as a command line.
exec bash -c "${STARTUP_CMD}"
