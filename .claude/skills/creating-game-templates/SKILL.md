---
name: creating-game-templates
description: Use when adding or editing a game server template ("egg") YAML in backend/app/templates — defining a new SteamCMD game's app_id, ports, startup command, and variables, or fixing a template that fails to load.
---

# Creating Game Templates

## Overview

A template is one YAML file in `backend/app/templates/<id>.yaml` that tells the panel
how to install and launch a Steam dedicated server. The loader
([template_loader.py](../../../backend/app/services/template_loader.py)) reads every
`*.yaml` on startup and validates it against the `GameTemplate` pydantic model in
[template.py](../../../backend/app/schemas/template.py). **The pydantic model is the
source of truth** — read it if anything here is ambiguous.

**Core safety rule:** the `startup` command is never shell-eval'd against arbitrary
input. Every `{{TOKEN}}` in `startup` MUST resolve to a declared port (`PORT_<name>`)
or a declared variable key, or the template is rejected at load time. This whitelist is
the injection guard — do not work around it.

## Workflow

1. **Research the game** — find the dedicated-server Steam **App ID** (e.g. via
   SteamDB), whether it allows anonymous download (`anonymous_login`), the **ports** it
   binds and their protocols, and the **startup command/flags** for the Linux server
   binary. Note any required static env vars (e.g. Valheim needs `SteamAppId`).
   Valve's [Dedicated Servers List](https://developer.valvesoftware.com/wiki/Dedicated_Servers_List)
   is the canonical starting point for App IDs, ports, and anonymous-login status; cross-check
   exact depot details on [SteamDB](https://steamdb.info/).
2. **Confirm it's actually self-hostable** — before writing a working template, verify
   the dedicated server (a) ships a **Linux** binary and (b) is **actually downloadable**
   via SteamCMD. Some Steam server apps exist but ship no files to the public (the depot
   is a tiny placeholder), or are Windows-only. If it fails either test, mark it
   unsupported instead — see [Unsupported games](#unsupported-games).
3. **Copy an existing template** as a starting point: `valheim.yaml` (account-aware,
   multi-port, env var) or `cs2.yaml` (simple). Name the file `<id>.yaml`.
4. **Fill in fields** per the reference below. Keep `id` == filename stem.
5. **Wire placeholders**: every `{{...}}` in `startup` must be either `PORT_<portname>`
   (from a `ports` entry) or a `variables[].key`. Declare them.
6. **Validate** (see command below). Fix until it loads.

## Field Reference

Top-level (`GameTemplate`):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `id` | str | — | `[A-Za-z0-9_]+`, unique across all templates. Match the filename. |
| `name` | str | — | Human-readable display name. |
| `app_id` | int ≥1 | — | Steam App ID of the **dedicated server** (not the game client). |
| `anonymous_login` | bool | `true` | `false` ⇒ panel prompts for Steam account + Steam Guard at install. |
| `install_dir` | str | `/data` | Container path SteamCMD installs into. Rarely change. |
| `ports` | list | `[]` | See PortSpec. |
| `startup` | str | — | **Required.** Launch command; uses `{{PLACEHOLDER}}` tokens. |
| `variables` | list | `[]` | User-editable values. See VarSpec. |
| `env` | map | `{}` | Static env vars injected into the container. Keys `[A-Za-z0-9_]+`. **Not** placeholders — trusted, operator-defined. |
| `update_on_start` | bool | `true` | Re-run SteamCMD validate before each start. Set `false` if not needed. |
| `supported` | bool | `true` | `false` ⇒ template stays in the catalog but the panel **blocks creating a server** from it. Use for games that can't be self-hosted. |
| `unsupported_reason` | str\|null | `null` | Shown to the user when `supported: false`. Explain *why* (e.g. no public server files, Windows-only). |
| `workshop` | map\|null | `null` | Steam Workshop support. Presence marks the game as workshop-capable (the UI shows the **Workshop** tab only then). See WorkshopSpec + [Steam Workshop](#steam-workshop). |

PortSpec (each `ports` entry):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `name` | str | — | `[A-Za-z0-9_]+`. Exposed to startup as `{{PORT_<name>}}`. |
| `protocol` | `tcp`\|`udp`\|`both` | — | — |
| `default` | int 1–65535 | — | Default base port. |
| `count` | int 1–8 | `1` | Reserves a contiguous block (e.g. Valheim port + query port). Only the base port is exposed as `{{PORT_<name>}}`. |

VarSpec (each `variables` entry):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `key` | str | — | `[A-Za-z0-9_]+`. Referenced in startup as `{{key}}`. |
| `default` | str | `""` | Empty `RCON_PASSWORD`/`SERVER_PASSWORD` ⇒ panel auto-generates a strong value. |

WorkshopSpec (the optional `workshop` map):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `app_id` | int ≥1 | — | Steam app whose **workshop content** is downloaded. Often the **client** game App ID, which differs from the dedicated-server `app_id` (e.g. Project Zomboid: server `380870`, workshop `108600`). |
| `install_path` | str | `steamapps/workshop` | Where items land inside the data dir, as `install_path/<item_id>`. Must be a **safe relative path** (no leading `/`, no `..`). |

## Placeholder rules

- Tokens look like `{{NAME}}` (whitespace inside braces is allowed).
- Allowed names = `PORT_<name>` for every port + every variable `key`. Nothing else.
- Use `>` (YAML folded scalar) for multi-line `startup`, as in the existing templates.
- `env` values are injected directly and are **not** referenced via `{{...}}`.

## Validate

Run from `backend/`. This loads and validates **all** templates (uncached), so a bad
new file fails loudly:

```bash
cd backend && python -c "from app.services.template_loader import _load_all; print('OK', list(_load_all()))"
```

Errors come back as `invalid template <file>: ...` (e.g. unknown placeholder, bad port
range, duplicate id). Fix and re-run until you see `OK [...]` including your new id.

## Steam Workshop

Add a `workshop` block **only** if the game actually distributes server mods through
the Steam Workshop. Its mere presence is what makes the panel show the **Workshop** tab
for servers created from this template — so omit it entirely for games without workshop
mods (the tab then stays hidden).

How it works:
- At create time the template's `workshop.app_id` is copied onto the server
  (`servers.workshop_app_id`); `NULL` means "no workshop" and the UI hides the tab.
- Adding a mod runs SteamCMD `+workshop_download_item <app_id> <item_id>` in a one-shot
  container (the gameserver image's entrypoint handles `WORKSHOP_DOWNLOAD`), then copies
  the item into the data volume at `INSTALL_DIR/<install_path>/<item_id>`.
- The panel only **downloads** items into place. **Wiring them into the game is
  game-specific** and not automatic — document in a comment how the server loads them
  (e.g. Project Zomboid's `.ini` `WorkshopItems=`/`Mods=`, a `-mod` launch flag, etc.).

Pick the right `app_id`: it's usually the **client** game's App ID (where the workshop
lives), not the dedicated-server App ID. Verify on the item's Steam Workshop page / SteamDB.

Example (Project Zomboid):

```yaml
# Workshop content lives under the CLIENT app 108600 (server app is 380870).
workshop:
  app_id: 108600
  install_path: "steamapps/workshop/content/108600"
```

> Changing the gameserver **entrypoint** (workshop mode) requires rebuilding the
> `steamcmd-manager/gameserver` image — it is not rebuilt by `docker compose build`.

## Unsupported games

Not every game with a Steam "dedicated server" app can actually be self-hosted here.
Two failure modes recur — and a *plausible-looking* template will install "successfully"
and then crash-loop, which is worse than a template that's honestly marked off-limits:

- **No public server files.** The server app exists on Steam but the publisher doesn't
  hand out the binaries (official hosting only). SteamCMD reports success, but the depot
  downloads as a tiny placeholder (a few bytes) with no executable — the container then
  dies with `./<binary>: No such file or directory` and restarts forever.
- **Windows-only server.** No native Linux binary, so there's nothing the container's
  Linux entrypoint can exec.

How to catch it *before* shipping a broken template:
- Check SteamDB for the depot's real size. A dedicated-server depot of a few bytes ⇒ no
  files are actually distributed.
- Search whether self-hosting is even offered, or only third-party rental (e.g. G-PORTAL).
- If unsure, you can install once and inspect `/data` (and `steamapps/appmanifest_*.acf`,
  field `SizeOnDisk`) — a near-zero size confirms it.

When a game fails either check, **don't invent a startup command**. Mark it unsupported
so it's documented and visibly blocked rather than silently broken:

```yaml
supported: false
unsupported_reason: >
  <one or two sentences: why it can't be self-hosted via SteamCMD>
```

Keep the real `app_id`/`ports` you researched (useful reference) and leave a comment
explaining the evidence. `deadside.yaml` is the canonical example: App 1275530's depot
ships ~6 bytes, so it's marked `supported: false`. The panel keeps it in the catalog but
rejects server creation (`create_server` raises) and the UI shows a "Not supported" badge.

## Common Mistakes

- **Undeclared placeholder** — `{{FOO}}` in startup with no matching port/variable ⇒
  load error. Declare it or remove it.
- **Using the client App ID** instead of the dedicated-server App ID.
- **`id` ≠ filename** or non-token chars in `id`/`name`-keys ⇒ validation error.
- **Referencing `env` keys as `{{...}}`** — env vars are not placeholders; reference the
  game's expected env name in `env:` only.
- **Forgetting `count`** for games that need consecutive ports (query/Steam port).
- **Hardcoding secrets** in `startup` instead of declaring a variable with empty default
  so the panel generates one.
- **Shipping a template for a game that has no public server files / no Linux binary** —
  it installs "OK" then crash-loops. Mark it `supported: false` instead (see
  [Unsupported games](#unsupported-games)).
- **Adding a `workshop` block for a game that has no Steam Workshop mods** — this only
  clutters the UI with a Workshop tab that downloads nothing useful. Omit it.
- **Using the dedicated-server `app_id` as `workshop.app_id`** — workshop content almost
  always lives under the *client* game's App ID. Wrong id ⇒ downloads find nothing.
