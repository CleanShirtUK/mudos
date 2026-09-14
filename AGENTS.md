# Mudos Authority

Canonical host: `lulu`
Canonical checkout: `/home/josh/src/lulu`

All current Mudos development happens in that checkout. Historical clones,
snapshots, payloads, releases, and temporary trees are read-only references.

Promotable releases require a clean committed checkout, the canonical
`scripts/release.py` builder, a new immutable release, checksum verification,
explicit validation, and explicit activation. Build and activation are separate.

Never build or deploy from Phleg, `/tmp`, a recovery or reconstructed tree, a
copied builder, `refresh-payload.sh`, an old installer, or an existing release.
Never copy individual files into `/opt/lulu`; never mutate a release directory.
Recovered code must be integrated here and committed before release construction.
