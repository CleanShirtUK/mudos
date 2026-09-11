# Game Metadata Identity

Mudos keeps launch identity and presentation identity separate.

## Stored Identity

Each `games` row retains the provider launch identity (`provider`, `provider_id`,
and the local path in `install_dir`) independently from optional canonical
metadata:

- `source_title` is the title discovered from Steam or the original filename.
- `normalized_search_title` is the cleaned query sent to metadata search.
- `metadata_provider` and `metadata_game_id` identify the canonical entry.
- `canonical_title` is the provider title shown when matching succeeds.
- `match_status` is `matched`, `ambiguous`, `unmatched`, or `manual`.
- `match_method` and `match_confidence` explain automatic selection.
- `match_locked` makes a manual selection authoritative across rescans.

The card uses `title`: canonical title for a confirmed match, otherwise the
cleaned local title or native Steam title. A failed metadata request never
removes launchability.

## Matching

ROM extensions, region/revision markers, dump tags, language groups, serial
suffixes, and separator punctuation are removed only for the search query.
Meaningful punctuation remains in the cleaned title. Candidates are ranked by
deterministic title/alias similarity, then platform compatibility. A low score,
platform mismatch, or close top two candidates produces `unmatched` or
`ambiguous` rather than inventing an identity.

SteamGridDB search responses are cached on disk. Game details are fetched only
for the bounded candidate set when platform data is absent, and are cached by
stable provider ID. Normal catalogue rendering reads SQLite and cached artwork;
network access is enrichment, not a launch prerequisite.

## Future Change Match Flow

The backend already supports the future controller flow:

`highlight card -> X -> Game Options -> Change Match -> search/results -> choose game`

`CatalogueStore.set_metadata_match()` changes only metadata identity and clears
artwork for refresh. `clear_metadata_match()` removes the lock and returns the
game to automatic matching without changing its launch identity or path.
