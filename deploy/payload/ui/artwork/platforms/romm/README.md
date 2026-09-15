# Vendored RomM platform artwork

These files are curated from RomM's upstream
`frontend/assets/platforms` directory at commit
`03ecdee7ee75555c8d19a53e5dc54296ec4771cb`.

`MudosAssetCatalog.js` maps RomM platform slugs to these filenames. RomM uses
`ngc` for GameCube and `psx` for the original PlayStation; Mudos aliases those
to its existing semantic identifiers `gamecube` and `ps1`. `default.ico` is
the deterministic generic fallback for PC, `all`, and unknown slugs.

`ATTRIBUTIONS` and `ROMM-AGPL-3.0.txt` are preserved from the upstream project.
The attribution file identifies files from other sources; the curated files
used here are not listed in those specific third-party subsets.
