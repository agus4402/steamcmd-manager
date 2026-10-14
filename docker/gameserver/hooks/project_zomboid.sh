#!/usr/bin/env bash
# Prestart hook for Project Zomboid (template: project_zomboid).
#
# Runs right before the server launches (see PRESTART_HOOK in entrypoint.sh) and
# writes the settings the panel manages into the server's .ini, which PZ only
# reads from that file. Every other key in the .ini is left untouched, so manual
# tweaks survive; the managed keys below are overwritten on every start.
#
# Inputs (env, set by the panel):
#   PUBLIC_NAME SERVER_PASSWORD MAX_PLAYERS PUBLIC PVP RCON_PASSWORD MEMORY
#   PORT_game PORT_rcon          allocated host ports
#   WORKSHOP_ITEMS               ";"-separated workshop item ids
#   WORKSHOP_MOD_IDS WORKSHOP_MAPS  enabled mod ids in load order + their maps
#                                (when unset: auto-detect every mod in the items)
#   STEAM_BRANCH                 "legacy41" => prefer Build 41 mod.info files
set -euo pipefail

DATA_DIR="${INSTALL_DIR:-/data}"
# Must match the template's startup: -cachedir=/data/Zomboid -servername pzserver
INI="${DATA_DIR}/Zomboid/Server/pzserver.ini"
# PZ workshop content (client app 108600), where the panel downloads items.
WORKSHOP_DIR="${DATA_DIR}/steamapps/workshop/content/108600"
JVM_CONFIG="${DATA_DIR}/ProjectZomboid64.json"
DEFAULT_MAP="Muldraugh, KY"

log() { echo "[pz-hook] $*"; }

# Strip CR/LF so a value can never inject extra .ini lines.
clean() { local v="${1//$'\r'/}"; printf '%s' "${v//$'\n'/}"; }

bool() {
    case "${1,,}" in
        1 | true | yes | on) echo true ;;
        *) echo false ;;
    esac
}

# set_ini KEY VALUE — replace the KEY= line or append it. Values go through
# ENVIRON (not the awk program text), so no escaping issues.
set_ini() {
    KEY="$1" VALUE="$(clean "$2")" awk '
        BEGIN { k = ENVIRON["KEY"]; v = ENVIRON["VALUE"]; done = 0 }
        { sub(/\r$/, "") }
        index($0, k "=") == 1 { if (!done) print k "=" v; done = 1; next }
        { print }
        END { if (!done) print k "=" v }
    ' "${INI}" >"${INI}.tmp"
    mv "${INI}.tmp" "${INI}"
}

# append_unique ARRAY_NAME VALUE
append_unique() {
    local -n arr="$1"
    local v
    for v in "${arr[@]}"; do [ "$v" = "$2" ] && return 0; done
    arr+=("$2")
}

mkdir -p "$(dirname "${INI}")"
[ -f "${INI}" ] || { log "creating ${INI}"; : >"${INI}"; }

# -- server identity / access -------------------------------------------------
set_ini PublicName "${PUBLIC_NAME:-My PZ Server}"
set_ini Password "${SERVER_PASSWORD:-}"
set_ini Public "$(bool "${PUBLIC:-true}")"
set_ini PVP "$(bool "${PVP:-true}")"
if [[ "${MAX_PLAYERS:-}" =~ ^[0-9]{1,3}$ ]]; then
    set_ini MaxPlayers "${MAX_PLAYERS}"
fi

# -- ports ------------------------------------------------------------------------
if [[ "${PORT_game:-}" =~ ^[0-9]+$ ]]; then
    set_ini DefaultPort "${PORT_game}"
    set_ini UDPPort "$((PORT_game + 1))"
fi
if [[ "${PORT_rcon:-}" =~ ^[0-9]+$ ]]; then
    set_ini RCONPort "${PORT_rcon}"
    set_ini RCONPassword "${RCON_PASSWORD:-}"
fi

# -- workshop mods ----------------------------------------------------------------
# For every downloaded item: its mod ids (from mod.info) go to Mods=, and any map
# folders to Map= (custom maps first, the vanilla map last).
items=()
mods=()
maps=()
IFS=';' read -ra wanted <<<"${WORKSHOP_ITEMS:-}"
for item in "${wanted[@]}"; do
    [[ "${item}" =~ ^[0-9]+$ ]] || continue
    dir="${WORKSHOP_DIR}/${item}"
    if [ ! -d "${dir}/mods" ]; then
        log "workshop item ${item} not downloaded yet; skipping"
        continue
    fi
    items+=("${item}")
    for moddir in "${dir}"/mods/*/; do
        [ -d "${moddir}" ] || continue
        # Build 42 layout: mods/<Mod>/<version>/mod.info, where <version> is a
        # folder like 42, 42.0 or 42.12 (+ common/); Build 41: mods/<Mod>/mod.info.
        # Prefer the newest version folder, fall back to the B41 root file.
        # (Quoted glob prefix: mod folder names can contain [ ] and spaces.)
        info=""
        if [ "${STEAM_BRANCH:-}" = "legacy41" ] && [ -f "${moddir}mod.info" ]; then
            info="${moddir}mod.info"
        fi
        [ -n "${info}" ] || while IFS= read -r version; do
            if [ -f "${moddir}${version}/mod.info" ]; then
                info="${moddir}${version}/mod.info"
                break
            fi
        done < <(for d in "${moddir}"4*/; do [ -d "${d}" ] && basename "${d}"; done | sort -V -r)
        # B42 fallback: version folders present but mod.info only in common/.
        if [ -z "${info}" ] && [ -f "${moddir}common/mod.info" ]; then
            info="${moddir}common/mod.info"
        fi
        if [ -z "${info}" ] && [ -f "${moddir}mod.info" ]; then
            info="${moddir}mod.info"
        fi
        if [ -n "${info}" ]; then
            id="$(grep -m1 -i '^[[:space:]]*id[[:space:]]*=' "${info}" | cut -d= -f2- | tr -d '\r' \
                | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')" || true
            [ -z "${id}" ] || append_unique mods "${id}"
        else
            log "workshop item ${item}: no mod.info in ${moddir}"
        fi
        # Map folders: <mod>/[<version>|common/]media/maps/<MapName>/
        while IFS= read -r mapdir; do
            map="$(basename "${mapdir}")"
            [ "${map}" = "${DEFAULT_MAP}" ] || append_unique maps "${map}"
        done < <(find "${moddir}" -mindepth 3 -maxdepth 4 -type d -iregex '.*/media/maps/[^/]+' | sort)
    done
done

# The panel sends the user's choice (enabled mod ids in load order + their maps)
# once it has inspected the items; the auto-detection above is the fallback.
if [ -n "${WORKSHOP_MOD_IDS+x}" ]; then
    mods=()
    maps=()
    IFS=';' read -ra chosen <<<"$(clean "${WORKSHOP_MOD_IDS}")"
    for id in "${chosen[@]}"; do [ -z "${id}" ] || append_unique mods "${id}"; done
    IFS=';' read -ra chosen <<<"$(clean "${WORKSHOP_MAPS:-}")"
    for map in "${chosen[@]}"; do
        [ -z "${map}" ] || [ "${map}" = "${DEFAULT_MAP}" ] || append_unique maps "${map}"
    done
fi
maps+=("${DEFAULT_MAP}")

join() { local IFS=';'; echo "$*"; }
set_ini WorkshopItems "$(join "${items[@]}")"
set_ini Mods "$(join "${mods[@]}")"
set_ini Map "$(join "${maps[@]}")"
log "workshop: ${#items[@]} item(s), ${#mods[@]} mod(s), map=$(join "${maps[@]}")"

# -- JVM heap -----------------------------------------------------------------------
# Re-applied every start because a steamcmd validate restores the stock file.
if [ -n "${MEMORY:-}" ]; then
    if [[ ! "${MEMORY}" =~ ^[0-9]+[mMgG]$ ]]; then
        log "ignoring invalid MEMORY='${MEMORY}' (use e.g. 3g or 3072m)"
    elif [ -f "${JVM_CONFIG}" ]; then
        sed -i -E "s/\"-Xmx[0-9]+[kKmMgG]?\"/\"-Xmx${MEMORY}\"/" "${JVM_CONFIG}"
        log "JVM heap set to ${MEMORY}"
    fi
fi
