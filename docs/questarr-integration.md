# Questarr integration

## Upstream evidence

The appliance image is pinned to
`ghcr.io/doezer/questarr@sha256:6faaf75f484a20805309315dd9eb9f1550b039a668efb89c13fc028c72b45485`.
The source tag selected for this integration is **Questarr v1.4.2**. Its
download-client behavior was checked in the tagged sources:

- `server/downloaders/transmission.ts`
- `server/downloaders/nzbget.ts`
- `server/downloaders/manager.ts`

The NZBGet client calls `version`, `append`, `listgroups`, `history`, `status`,
and `editqueue` (`GroupPause`, `GroupResume`, `GroupDelete`). The Transmission
client calls `session-get`, `torrent-add`, `torrent-get`, `torrent-stop`,
`torrent-start`, `torrent-remove`, and `free-space`. The Questarr UI/API invokes
the latter status/action methods for client tests, download display, and
download management. No generic external-webhook request path is used.

## Ownership and request flow

Acquisitiond remains the only Mudos acquisition-job authority. The NZBGet
compatibility surface is implemented by `lulu.questarr_gateway` inside the
Acquisitiond process and listens on loopback TCP 5001. For the first transport,
the supported flow is:

```text
Questarr NZBGet client
  -> 127.0.0.1:5001/xmlrpc (host-networked container)
  -> durable Questarr client-ID/fingerprint mapping
  -> Acquisitiond JobManager.submit(provider=usenet, origin=questarr)
  -> existing Mudos NZBGet executor
  -> real NZBGet
```

The gateway stores the NZB in Mudos' mutable Usenet NZB area, keyed by its
content digest. A SQLite mapping preserves Questarr's numeric NZBGet ID,
content fingerprint, and Mudos job ID across gateway/Acquisitiond restarts.
Duplicate submissions resolve to the existing mapping/job. Questarr polling is
projected from the persisted Acquisitiond `DownloadJob`; the gateway does not
create a second progress or execution queue. The Mudos job records
`origin=questarr` and transport/request correlation metadata.

Questarr is configured only with the gateway URL and empty daemon credentials.
The gateway binds to `127.0.0.1`; Questarr's host-networked container can reach
it, but LAN clients cannot. The actual NZBGet endpoint and credentials remain
in Mudos provider configuration and are used only by Acquisitiond. Direct
Mudos NZBGet submissions retain their existing path and semantics.

The current first milestone implements only the NZBGet protocol subset needed
for connection tests, add, list/status/history, free-space, pause/resume, and
remove. Transmission compatibility is not yet enabled; reconciliation must
not configure Questarr with the real Transmission endpoint or credentials.

## Authentication and web topology

Questarr runs as a pinned rootful Podman service with persistent data at
`/var/lib/lulu-questarr/data`. Its own HTTP server binds to `127.0.0.1:5002`.
The LAN-facing Mudos auth proxy listens on port 5000, the existing LAN-only
UFW rule. It forwards normal Questarr requests and handles login specially:

1. Require appliance user `josh`. The unprivileged proxy passes credentials to
   a restricted root-owned Unix-socket helper. The helper accepts only the
   `lulu` service UID, only the configured appliance username, and invokes the
   same system PAM `login` service used by Mudos managed-account auth. It has no
   network listener and returns only a categorized authentication result.
2. Exchange that successful PAM authentication for a Questarr JWT using a
   randomly generated Questarr-internal credential stored only in Mudos
   SecretStore (`web/questarr`).
3. Never store, forward to Questarr, or log the user's PAM password. Public
   first-run setup is disabled; the proxy provisions the Questarr internal user
   automatically when Questarr has no users.
4. Establish an opaque, HttpOnly, same-site proxy session (eight-hour maximum).
   Protected API and Socket.IO polling requests require that PAM-established
   session; a Questarr bearer token by itself is not sufficient at the LAN
   boundary. Proxy restart invalidates these sessions and requires a fresh
   PAM login. The helper's writable surface is limited to its socket directory
   and PAM's `/run/faillock` runtime tally directory so system lockout policy
   remains effective inside systemd's filesystem sandbox.

Both the delegated Mudos browser and LAN browsers reach the same port-5000
proxy and authenticate against the system account. Questarr is not configured
as a trusted-web autofill profile, preventing the PAM password from being
captured into browser credential storage. The proxy applies its own login
rate limit because upstream login is performed with the private internal
credential after PAM succeeds.

## IGDB and indexers

Prowlarr remains an indexer/search source and is synchronized through
Questarr's supported API. It does not select or own download execution.

When Mudos IGDB credentials are configured, the reconciler projects Mudos'
client ID and SecretStore-backed client secret through Questarr's supported
`POST /api/settings/igdb` API. No secret is placed in the release, provider
TOML, logs, or tests. When Mudos IGDB is not configured, metadata readiness is
reported incomplete; this does not invent credentials or block the NZB
gateway's request ownership.

## Readiness

Admin derives Questarr readiness from separate observations: Questarr service
state, public web health, auth-proxy/PAM/internal-identity availability,
metadata configuration, authenticated indexer count, loopback gateway test,
and Acquisitiond service state. Missing IGDB yields `degraded`, not a false
claim of full readiness. Provider/source readiness remains distinct from
service liveness.

## Physical acceptance still required

The source/API and deterministic unit tests establish the implemented
boundary, but the appliance must still prove the end-to-end path with a small,
safe NZB request:

```text
Questarr -> gateway -> stable Acquisitiond job -> Downloads -> real NZBGet
        -> Questarr status projection
```

Cancel the request after ownership/progress is verified and before substantial
transfer. Do not reuse or disturb the already accepted direct NZBGet fixture.
After this milestone is accepted, add and validate the Transmission gateway
using the same ownership and correlation model.
