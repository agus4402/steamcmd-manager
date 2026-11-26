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
        [ "${attempt}" -le "${max_attempts}" ] && sleep "${WS_RETRY_SLEEP:-5}"
    done

    log "ERROR: steamcmd failed for App ID ${STEAM_APP_ID} after ${max_attempts} attempts (exit ${rc})"
    exit "${rc}"
}

# Machine-readable per-item outcome, parsed by the panel:
#   [workshop-result] <item_id> ok
#   [workshop-result] <item_id> failed <reason>
ws_result() { echo "[workshop-result] $*"; }

# install_workshop_item ITEM — copy a downloaded item into the server's data
# volume. Prints a result line; returns non-zero on failure.
install_workshop_item() {
    local item="$1"
    # steamcmd writes items to <steam root>/steamapps/workshop/content/<app>/<item>.
    # The root varies by build, so probe the known locations.
    local rel="steamapps/workshop/content/${WORKSHOP_APP_ID}/${item}"
    local src=""
    for base in "/home/steam/Steam" "${STEAMCMD_DIR}" "/home/steam/.steam/steam"; do
        if [ -d "${base}/${rel}" ]; then src="${base}/${rel}"; break; fi
    done
    if [ -z "${src}" ]; then
        ws_result "${item}" failed "not found on disk after steamcmd reported success"
        return 1
    fi
    # An item with folders but no files is a failed download, not a mod.
    if [ -z "$(find "${src}" -type f -print -quit)" ]; then
        ws_result "${item}" failed "downloaded no files"
        return 1
    fi
    local dest="${INSTALL_DIR}/${WORKSHOP_INSTALL_PATH:-steamapps/workshop}/${item}"
    mkdir -p "$(dirname "${dest}")"
    rm -rf "${dest}"
    if ! cp -a "${src}" "${dest}"; then
        ws_result "${item}" failed "could not copy into ${dest} (disk full?)"
        return 1
    fi
    ws_result "${item}" ok
}

STEAM_ROOTS=("/home/steam/Steam" "${STEAMCMD_DIR}" "/home/steam/.steam/steam")

# reset_workshop_item ITEM — drop steamcmd's cached copy and partial download of
# one item so the next attempt starts clean. A download that keeps ending in
# "failed (Failure)" (not Timeout) usually has a corrupt partial state that
# resuming can never get past.
reset_workshop_item() {
    local item="$1" base dl
    for base in "${STEAM_ROOTS[@]}"; do
        dl="${base}/steamapps/workshop/downloads"
        rm -rf "${base}/steamapps/workshop/content/${WORKSHOP_APP_ID}/${item}" \
            "${dl}/${item}" "${dl}/${WORKSHOP_APP_ID}/${item}" \
            "${base}/steamapps/workshop/temp/${WORKSHOP_APP_ID}/${item}"
        rm -f "${dl}/state_${WORKSHOP_APP_ID}_${item}"*
    done
}

# reset_workshop_manifest — forget steamcmd's record of downloaded items for the
# app (appworkshop_<app>.acf). A stale entry also causes "failed (Failure)".
# Only the shared cache's bookkeeping: items already copied into servers stay.
reset_workshop_manifest() {
    local base
    for base in "${STEAM_ROOTS[@]}"; do
        rm -f "${base}/steamapps/workshop/appworkshop_${WORKSHOP_APP_ID}.acf"
    done
}

run_workshop_download() {
    # One-shot Steam Workshop download of one or more items. Driven by:
    #   WORKSHOP_APP_ID       Steam app whose workshop content is fetched
    #   WORKSHOP_ITEM_IDS     ";"/space-separated item ids (or WORKSHOP_ITEM_ID)
    #   WORKSHOP_INSTALL_PATH where to place them under INSTALL_DIR (relative)
    local ids_raw="${WORKSHOP_ITEM_IDS:-${WORKSHOP_ITEM_ID:-}}"
    local pending=()
    local id
    for id in ${ids_raw//;/ }; do
        if [[ "${id}" =~ ^[0-9]{1,20}$ ]]; then pending+=("${id}"); fi
    done
    if [ -z "${WORKSHOP_APP_ID:-}" ] || [ "${#pending[@]}" -eq 0 ]; then
        log "ERROR: WORKSHOP_APP_ID and WORKSHOP_ITEM_IDS are required"
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

    # All items go through ONE steamcmd session (one login) per attempt: a login
    # per item gets throttled by Steam on big collections.
    # steamcmd exits 0 even when a workshop download fails: big items often stop
    # with "ERROR! Download item <id> failed (Timeout)", leaving a partial
    # download behind (it resumes on the next run). So judge each item by its
    # "Success. Downloaded item <id>" line and retry only the ones that failed.
    log "downloading ${#pending[@]} workshop item(s) for app ${WORKSHOP_APP_ID}: ${pending[*]}"
    local max_attempts=6
    local attempt=1
    local out="/tmp/workshop-download.log"
    local failed=0
    local manifest_reset=0
    declare -A reason=()
    declare -A hard_fails=()
    while [ "${#pending[@]}" -gt 0 ] && [ "${attempt}" -le "${max_attempts}" ]; do
        log "steamcmd attempt ${attempt}/${max_attempts} for ${#pending[@]} item(s)"
        local cmd_args=()
        for id in "${pending[@]}"; do
            cmd_args+=("+workshop_download_item" "${WORKSHOP_APP_ID}" "${id}")
        done
        set +e
        "${STEAMCMD_DIR}/steamcmd.sh" "${login_args[@]}" "${cmd_args[@]}" +quit 2>&1 \
            | tee /dev/stderr | sed 's/\x1b\[[0-9;]*[A-Za-z]//g' >"${out}"
        set -e
        local still=()
        for id in "${pending[@]}"; do
            if grep -q "Success. Downloaded item ${id}" "${out}"; then
                install_workshop_item "${id}" || failed=$((failed + 1))
            else
                still+=("${id}")
                # Keep the most specific reason seen across attempts.
                local err
                err="$(grep -o "ERROR! Download item ${id} failed ([^)]*)" "${out}" | tail -n1 || true)"
                if [ -n "${err}" ]; then
                    reason["${id}"]="${err}"
                elif [ -z "${reason[${id}]:-}" ]; then
                    reason["${id}"]="$(grep -o 'ERROR![^.]*\|FAILED.*' "${out}" | tail -n1 || true)"
                fi
                # A Timeout resumes fine; anything else restarts the item clean.
                if [ -n "${err}" ] && [[ "${err}" != *"(Timeout)"* ]]; then
                    hard_fails["${id}"]=$(( ${hard_fails[${id}]:-0} + 1 ))
                    log "item ${id}: ${err#ERROR! } — clearing its cached download"
                    reset_workshop_item "${id}"
                    if [ "${hard_fails[${id}]}" -ge 2 ] && [ "${manifest_reset}" -eq 0 ]; then
                        log "clearing steamcmd's workshop manifest for app ${WORKSHOP_APP_ID}"
                        reset_workshop_manifest
                        manifest_reset=1
                    fi
                fi
            fi
        done
        pending=("${still[@]}")
        attempt=$((attempt + 1))
        if [ "${#pending[@]}" -gt 0 ] && [ "${attempt}" -le "${max_attempts}" ]; then
            log "${#pending[@]} item(s) did not complete; resuming"
            sleep "${WS_RETRY_SLEEP:-5}"
        fi
    done

    for id in "${pending[@]}"; do
        ws_result "${id}" failed "${reason[${id}]:-did not finish downloading after ${max_attempts} attempts}"
        failed=$((failed + 1))
    done
    if [ "${failed}" -gt 0 ]; then
        log "ERROR: ${failed} workshop item(s) failed"
        exit 5
    fi
    log "all workshop items ready"
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
