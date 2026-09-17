# Mudos plugins

Mudos plugins are versioned, in-process extensions discovered from
`$LULU_PLUGIN_ROOT`, or `~/.config/lulu/plugins` with the installed
`config/plugins` tree as the fallback. Each plugin is self-contained:

```text
plugins/<id>/
├── plugin.toml
├── plugin.py
├── providers/
└── config/
```

`plugin.toml` declares `id`, `name`, `version`, `api_version = 1`, and boolean
capabilities. `plugin.py` exports `register(context)`. The context exposes
only the manifest, a namespaced logger, and `register(capability, value)`;
provider declarations are then consumed by the existing provider registry.
Plugin initialization is deterministic (path order), and exceptions are
contained: the plugin is marked `degraded` while Mudos and other plugins
continue. Unsupported manifests are `unavailable`; `enabled = false` produces
`disabled` without deleting configuration. Restarting Mudos applies changes;
runtime hot reload is intentionally not supported.

The initial Steam and RomM manifests declare their current provider,
catalogue, metadata, acquisition, authentication, and session capabilities.
Their provider declarations now live under their plugin trees. Acquisitiond
registers acquisition contributions generically, so disabling a plugin removes
its handlers without a core provider branch. The existing normalized catalogue,
Guide, job lifecycle, storage policy, and controller/session boundaries remain
Mudos-owned.

Plugin status is available through Consoled's normalized `GetPluginStatus`
method. Future plugins should contribute normalized records and adapters rather
than importing private application objects. Provider IDs remain stable so
existing catalogue identities are preserved.

For v1, plugins are trusted in-process Python and are not sandboxed. There is
no marketplace, installer, hot reload, or credential migration. Steam and RomM
adapters retain their existing secure secret references and canonical Mudos
storage paths.
