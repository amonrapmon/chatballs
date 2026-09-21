# Chatballs ru-vmmini deployment

This deployment uses the canonical `compose.yaml` plus
`compose.ru-vmmini.yaml`. The canonical upstream manifest is not modified.

Intended host directory:

```text
/home/rapmon/chatballs
```

The deployment uses the existing Traefik `proxy` network and the separate
external `chat_interop` network. `chat_interop` is intentionally not created
by this repository.

## Pre-deploy commands

Run on `ru-vmmini` after copying this repository to `/home/rapmon/chatballs`:

```bash
cd /home/rapmon/chatballs
docker network inspect proxy >/dev/null
docker network inspect chat_interop >/dev/null 2>&1 || \
  docker network create --driver bridge --internal chat_interop
cp deploy/ru-vmmini/.env.example deploy/ru-vmmini/.env
# Edit CHATBALLS_DOMAIN and CHATBALLS_PLATFORM_DOMAIN in deploy/ru-vmmini/.env.
```

The `proxy` network must be owned by the existing Traefik installation. The
`chat_interop` command is documented only; it is not run by this change.

## First start

```bash
docker compose \
  --env-file deploy/ru-vmmini/.env \
  -f compose.yaml \
  -f compose.ru-vmmini.yaml \
  config --quiet

docker compose \
  --env-file deploy/ru-vmmini/.env \
  -f compose.yaml \
  -f compose.ru-vmmini.yaml \
  up -d --build --wait
```

The source checkout is self-contained for this deployment: the override
builds the production backend, PostgreSQL, frontend, and gateway images from
the Dockerfiles in this checkout. `compose.dev.yaml` is not used, and no
manual `docker build` sequence is required.

The gateway is the only Traefik-labelled service. It has no host port
bindings; Traefik reaches its port 80 over `proxy`. `backend-app` is the only
Chatballs service attached to `chat_interop`, with the stable alias
`chatballs-app`.

The deployment override keeps `backend-admin` on its upstream loopback-only
host bind, starts one gunicorn worker and one event worker by default, and does
not start Coturn or the updater. They can be enabled explicitly later with
`--profile calls` or `--profile updater`.
