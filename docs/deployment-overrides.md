# Installing behind existing nginx

If nginx already occupies ports 80 and 443, it can serve the Chatballs HTTPS
domain and forward requests to the installation gateway on a local HTTP port.

Create `compose.override.yaml` next to the release's `compose.yaml`:

```yaml
services:
  gateway:
    ports: !override
      - "127.0.0.1:8443:80"
```

Docker Compose 2.24.4 or later is required. `!override` replaces the entire
port list: the original bindings for 80 and 443 are removed. Here 8443 is an
internal HTTP port, not an external HTTPS port.

Start the installation with both files:

```bash
docker compose -f compose.yaml -f compose.override.yaml up -d --wait
```

The external nginx terminates HTTPS and proxies requests to
`http://127.0.0.1:8443`, preserving `Host`, forwarding `X-Forwarded-Proto`,
and supporting WebSocket. The external nginx handles the certificate and
HTTP → HTTPS redirect. Open the setup wizard on the final HTTPS domain,
without the internal port.

## Updates from the interface

The updater reads the Compose file list from the running container's labels.
It replaces the first file with the new release and preserves additional files
in their original order. This includes the standard `compose.override.yaml`
and custom filenames explicitly passed with `-f`.

Apply the override when starting the installation. A file that merely sits
next to the main file but is not part of the running project's configuration
is not automatically added during an update.

If you change the list or order of `-f` files after starting the installation,
recreate `updater` with the new list so its Compose labels reflect it:

```bash
docker compose -f compose.yaml -f compose.override.yaml up -d --no-deps --force-recreate updater
```

The installation directory and additional files are mounted read-only in the
update helper. This preserves resolution of `.env`, relative `env_file`
entries, and configuration paths. Keep override files accessible at the same
paths. A missing or invalid override stops the update before services are
restarted. The release overwrites only the main `compose.yaml`.
