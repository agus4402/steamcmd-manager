# SteamCMD Server Manager

Panel web autohosteado y dockerizado para gestionar **cualquier** game server basado en SteamCMD.
Instalás un servidor dedicado de Steam indicando su **App ID**, lo gestionás (instalar / arrancar /
parar / reiniciar / actualizar), ves la **consola en vivo** y los **puertos se asignan y exponen
automáticamente** — todo sin tocar código ni recompilar.

Single-tenant (un operador / equipo chico). Pensado para correr en un NAS Linux con Docker.

---

## Arquitectura

```
┌──────────────┐  REST+WS   ┌──────────────────┐  HTTP+token   ┌──────────────────┐
│  Next.js UI  │ ─────────► │  FastAPI (panel) │ ────────────► │  agent (Wings)   │
└──────────────┘            │  SIN docker.sock │  red interna  │  ÚNICO con sock  │
   red: panel               └──────────────────┘  internal:true└────────┬─────────┘
                                                                         │ /var/run/docker.sock
                                                                         ▼
                                                       ┌───────────────────────────────┐
                                                       │  Docker daemon del host        │
                                                       │  gs-<id>  gs-<id>  …            │  ← 1 container/server
                                                       └───────────────────────────────┘
                                                  volúmenes: steamcmd-cache · gsdata-<id>
```

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind, consola con xterm.js, dark mode.
- **Backend (panel):** FastAPI (Python 3.12, `uv`), SQLAlchemy 2.x async, Pydantic v2, Alembic, Postgres.
  **No tiene acceso a Docker.**
- **Agent:** servicio FastAPI mínimo y auditable; **único con el socket Docker**. Crea **un container por
  game server** en el daemon del host. El backend lo maneja por una API angosta con token (ver Seguridad).
- **Orquestación:** toda la lógica docker-py vive en
  [`agent/app/orchestrator.py`](agent/app/orchestrator.py); el backend la consume vía cliente HTTP en
  [`backend/app/services/docker_orchestrator.py`](backend/app/services/docker_orchestrator.py) (misma
  interfaz, ahora sobre HTTP).

### Componentes

| Módulo | Rol |
|---|---|
| `agent/app/orchestrator.py` | Único punto que habla con docker-py (dentro del agente). Hardening de workers. |
| `agent/app/main.py` | API angosta del agente + auth por token + validación de inputs. |
| `backend/.../docker_orchestrator.py` | Cliente HTTP al agente (misma interfaz que antes). |
| `backend/.../server_service.py` | Lifecycle: create, install/start/stop/restart/update, reconcile. |
| `backend/.../port_manager.py` | Asignación de puertos del pool con advisory lock de Postgres. |
| `backend/.../template_loader.py` | Carga y valida los templates YAML. |
| `backend/.../crypto.py` · `auth.py` | Fernet de credenciales Steam · password hash + JWT. |
| `backend/app/templates/*.yaml` | Templates de juego ("eggs"). |

---

## Quick start

```bash
cp .env.example .env        # ajustá secrets (ADMIN_PASSWORD, JWT_SECRET, PANEL_SECRET)
docker compose up --build   # levanta db + backend + frontend

# La primera vez, aplicá las migraciones y construí la imagen base de game server:
docker compose exec backend alembic upgrade head
docker build -t steamcmd-manager/gameserver:latest ./docker/gameserver
```

- **Panel:** http://localhost:3000 (login con `ADMIN_USER` / `ADMIN_PASSWORD`)
- **API:** http://localhost:8080 — health: `/health`, health completo (DB + agente): `/api/health/full`

> El puerto del backend en host es **8080** (mapea al `:8000` interno) para no chocar con otros stacks.
> Cambialo en `docker-compose.yml` y en `NEXT_PUBLIC_API_URL` si hace falta.

### Variables de entorno

Ver [`.env.example`](.env.example). Las clave:

| Var | Descripción |
|---|---|
| `ADMIN_USER` / `ADMIN_PASSWORD` | Credenciales del único usuario del panel (se siembra al boot). |
| `JWT_SECRET` | Firma de los tokens JWT. Cambialo en prod. |
| `PANEL_SECRET` | Deriva la clave Fernet para cifrar credenciales Steam. **≥ 32 bytes.** |
| `PORT_POOL_START` / `PORT_POOL_END` | Rango de puertos host asignables (default 27015–27200). |
| `GAMESERVER_IMAGE` | Tag de la imagen base de game server. |
| `AGENT_TOKEN` | Secreto compartido backend↔agente. Cambialo en prod. |

---

## Seguridad — modelo Panel / Agente (estilo Pterodactyl)

El componente expuesto y grande (FastAPI) **no toca Docker**. El acceso a `/var/run/docker.sock` está
aislado en un **agente mínimo y auditable** ([`agent/`](agent/)), inspirado en *Wings* de Pterodactyl.

Por qué esto importa: un bug en el backend (bypass de auth, SSRF, RCE) **ya no equivale a root del
host**, porque el backend no tiene el socket. Lo único que puede hacer un backend comprometido es invocar
la **API angosta del agente**, que por diseño **no puede expresar un escape**:

- **Imagen fija** (no se puede elegir otra), **mounts fijos** (`steamcmd-cache` + `gsdata-<id>`; nunca
  binds arbitrarios ni `/`).
- **Nunca** `privileged`, `cap_add`, `network_mode=host`, `pid=host`, `devices` ni `command` arbitrario.
- `port_bindings` validados dentro del pool; nombres de volumen restringidos al prefijo `gsdata-`.
- El agente exige `AGENT_TOKEN` y vive en una red `internal: true` (sin egress, **no publicado al host**).

**Hardening de los game servers (workers):** cada container corre con `cap_drop: ALL`,
`no-new-privileges`, límites de CPU/RAM/PIDs y usuario no-root.

> **Alcance honesto:** esto **aísla** el privilegio (estándar de la industria: Pterodactyl/AMP hacen lo
> mismo). El agente sigue siendo root-equivalente como *Wings*. Hacer el root del host **imposible** por
> construcción requeriría un motor Docker **rootless anidado** (no incluido en esta versión).

Otras medidas: no exponer el backend a internet sin reverse-proxy + TLS, y rotar `JWT_SECRET` /
`PANEL_SECRET` / `AGENT_TOKEN`.

---

## Cómo agregar un juego nuevo (template / "egg")

Creá un archivo `backend/app/templates/<id>.yaml`. El backend lo valida con un schema Pydantic al cargar.

```yaml
id: cs2                    # [A-Za-z0-9_]+, único
name: "Counter-Strike 2"
app_id: 730                # App ID del dedicated server en Steam
anonymous_login: true      # false => requiere credenciales + Steam Guard
install_dir: /data
ports:
  - name: game             # genera el placeholder {{PORT_game}}
    protocol: both         # tcp | udp | both
    default: 27015
startup: >
  ./game/bin/linuxsteamrt64/cs2 -dedicated +map de_dust2
  -port {{PORT_game}} +rcon_password {{RCON_PASSWORD}} +maxplayers {{MAXPLAYERS}}
variables:
  - key: MAXPLAYERS
    default: "16"
  - key: RCON_PASSWORD
    default: ""             # vacío + key termina en PASSWORD => el panel genera uno fuerte
update_on_start: true      # corre steamcmd app_update antes de arrancar
```

**Reglas de seguridad de los templates:**

- En `startup` **sólo** se interpolan placeholders de la whitelist: `{{PORT_<name>}}` (de `ports`) y
  `{{<KEY>}}` (de `variables`). Cualquier otro placeholder hace fallar la carga del template — nunca hay
  `eval` ni interpolación de texto arbitrario.
- El panel asigna el **puerto host real** del pool y lo inyecta en `{{PORT_<name>}}`. Se usa el **mismo
  número** en host y dentro del container (evita el problema #1 de los servers: NAT de puertos UDP).
- `protocol: both` mapea TCP **y** UDP sobre ese puerto.

Hay 3 templates de ejemplo: `cs2` (730), `valheim` (896660) y `debug` (1007, para probar el pipeline sin
descargar un juego pesado).

### Login Steam y Steam Guard

Para App IDs que requieren cuenta (`anonymous_login: false`), el panel pide usuario + password + código
Steam Guard al instalar. Las credenciales se **cifran en reposo** (Fernet, derivado de `PANEL_SECRET`) y
**nunca se loguean**. El código Steam Guard es de un solo uso y **no se persiste**.

---

## API (resumen)

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/auth/login` | Devuelve un JWT. |
| `GET` | `/api/templates` | Lista templates. |
| `POST` | `/api/servers` | Crea server (asigna puertos + volumen; no arranca). |
| `GET` | `/api/servers` · `/api/servers/{id}` | Estado + puertos (reconciliados con Docker). |
| `POST` | `/api/servers/{id}/install\|start\|stop\|restart\|update` | Lifecycle. |
| `PATCH` | `/api/servers/{id}` | Editar variables / startup. |
| `DELETE` | `/api/servers/{id}` | Borra container + volumen + libera puertos. |
| `WS` | `/api/servers/{id}/console?token=<jwt>` | Logs en vivo + comandos a stdin. |

Todas las rutas (excepto `/health` y `/api/auth/login`) requieren `Authorization: Bearer <jwt>`.

---

## Desarrollo

El backend monta `./backend` con `uvicorn --reload` (hot reload). Para iterar el frontend localmente:

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000 contra el backend en :8080
```

Migraciones nuevas:

```bash
docker compose exec backend alembic revision --autogenerate -m "mensaje"
docker compose exec backend alembic upgrade head
```

Smoke tests manuales: `backend/scripts/test_orchestrator.py` (Docker) y `backend/scripts/test_ws.py` (WS).

---

## Fuera de scope (v1)

Multi-usuario/roles, backups/scheduling, file manager, métricas de CPU/RAM, multi-nodo. Juegos que
requieren puertos **estrictamente consecutivos** (ej. Valheim usa `port`, `port+1`, `port+2`) son una
limitación conocida del pool de puertos actual.
