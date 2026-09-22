# Switch content architecture

Nintendo Switch base content, updates, and DLC are components of one game,
not separate Mudos library games.  `src/lulu/switch_content.py` defines the
provider-neutral `GameContentComponent` boundary.

Each component preserves its source (`romm` or `questarr`), provider/source
ID, parent game identity, role, title ID, version, path, and downloader job
ID.  Questarr's structured game association is authoritative; its observed
`downloadType` is downloader protocol, so it must not be treated as a role.
RomM's file categories are preferred when supplied.  Release-name inference
is deliberately a last-resort fallback, and mixed/composite releases remain
ambiguous until their package contents can be inspected.

Downloads remain individual jobs for progress, retry, and cancellation.  The
catalogue resolver uses the parent/base identity and presents one focal game.
Updates are installed transactionally and must not retire a working version
until the emulator reports the replacement active.  DLC remains additive and
retains distinct component identities.
