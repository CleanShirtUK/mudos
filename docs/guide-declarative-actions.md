# Declarative Guide actions

Guide is composed by `Consoled`, not by QML or the native helper. The
Mudos-owned universal actions live in `config/guide/base.toml`; Mudos-owned
contextual shortcuts live in `config/guide/mudos.toml`; provider-owned actions
live in each `config/providers/<id>/provider.toml` under `[[guide.actions]]`.
The registry normalizes stable IDs, labels, roles, targets, contexts, order,
and confirmation flags. `GetGuideActions` composes provider actions, base
actions, and Mudos actions
matching the authoritative session context (`shell`, `game`, `standalone`, or
a delegated surface such as `store`). A game ID is not required for a
standalone session.

Executable providers must declare exactly one `role = "quit"` action. The
registry rejects duplicate IDs, invalid roles/contexts, missing targets, and
launch-capable providers without a Quit action. Catalogue-only providers may
omit Quit. Provider launch declarations remain separate from Guide actions.
The Mudos Downloads shortcut is not Steam-owned and is available on every
Mudos-owned context.

`mudos-guide` renders normalized objects and submits stable IDs to
`Consoled.ExecuteGuideAction`. Mudos actions cross the session boundary for
compatibility mode, session restart, reboot, and shutdown. Provider targets
are returned by that boundary and executed by generic native primitives
(window close, key delivery, or a structured detached command); no provider
IDs are embedded in Guide.

No Guide action currently needs a helper script. The audit therefore keeps all
actions as direct declarations or generic execution targets. If a future
provider needs sequencing or runtime inspection, its helper belongs under
that provider's `config/` tree rather than a generic Mudos scripts directory.
This means no Bash/Python rewrite was performed in this migration.

The compatibility action is a reusable session/input operation, independent of
Steam or Guide presentation. The existing controller hand-back remains owned
by the session/input boundary.
