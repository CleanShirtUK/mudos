# Network File Browser

Mudos uses [dufs](https://github.com/sigoden/dufs) v0.46.0 as a small,
single-binary network file browser. It is deliberately not implemented inside
Mudos: dufs owns the HTTP UI and upload/download protocol, while systemd owns
its lifecycle.

## Served roots

The `lulu-file-browser.service` mount namespace exposes exactly these existing
Mudos roots:

- `/home/lulu/Games` as `/Games`
- `/home/lulu/Recordings` as `/Recordings`
- `/home/lulu/Replays` as `/Replays`
- `/home/lulu/Screenshots` as `/Screenshots`

The dufs root is `/srv`; it has no bind mount for the rest of the host or for
the parent `/home/lulu` directory. Symlink serving is disabled. Upload,
directory creation, editing, deletion, search, and archive downloads are
enabled; command execution is not.

## Configuration and lifecycle

The installer creates `/etc/lulu/file-browser.env` with a random credential when
one does not already exist, and enforces mode `0600`. Install and enable
`lulu-file-browser.service` with the other units; `lulu.target` starts it.
When UFW is active, provisioning allows TCP port 8080 only from the detected
LAN subnet and on the selected LAN interface.

The Settings Network category reports `active`/`inactive` status and the URL
formed from the first address returned by `hostname -I` and port 8080. This is
an informational connection address, not a control or authentication channel.

## Research assumption

The selected upstream was checked on 2026-09-12. dufs v0.46.0 documents
upload, archive download, basic authentication, health checks, and disabled
symlink traversal. The previously common `filebrowser/filebrowser` project is
archived and explicitly unmaintained, so it is not suitable for a new Mudos
service.
