# ROM Corpus Recovery Comparison

Compared against the committed 37-file baseline using the exact same manifest. The rerun reused cached SGDB responses and made no threshold variant run.

## Before / After

| Status | Before | After |
|---|---:|---:|
| matched | 9 | 35 |
| ambiguous | 16 | 2 |
| low-confidence | 12 | 0 |
| unmatched | 0 | 0 |
| network-error | 0 | 0 |

## Platform Results

| Platform | Before matched | After matched | Before ambiguous | After ambiguous | Before low-confidence | After low-confidence |
|---|---:|---:|---:|---:|---:|---:|
| genesis | 0 | 1 | 2 | 1 | 0 | 0 |
| nes | 0 | 2 | 2 | 0 | 0 | 0 |
| ps2 | 9 | 23 | 12 | 1 | 3 | 0 |
| switch | 0 | 8 | 0 | 0 | 8 | 0 |
| wii | 0 | 1 | 0 | 0 | 1 | 0 |

## Remaining Ambiguities

- `ps2/Shadow of the Colossus (USA).iso`: `Shadow of the Colossus` IDs `5414306` and `86`, both score 1.0; SGDB supplied no platform metadata.
- `genesis/Sonic the Hedgehog (JUE) [!].bin`: `Sonic the Hedgehog` IDs `35571` and `5249681`, both score 1.0; SGDB supplied no platform metadata.

## Newly Matched Items

| Platform | Filename | Normalized query | Selected SGDB title | ID | Confidence | Previous | Reason accepted |
|---|---|---|---|---|---:|---|---|
| genesis | `Taz-Mania (U) [!].bin` | `Taz-Mania` | Taz-Mania | `37388` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| nes | `Super Mario Bros (E).nes` | `Super Mario Bros` | Super Mario Bros. | `37382` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| nes | `Super Mario Bros 3 (PC10).nes` | `Super Mario Bros 3` | Super Mario Bros. 3 | `36658` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| ps2 | `Crazy Taxi (USA).cue` | `Crazy Taxi` | Crazy Taxi | `21778` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| ps2 | `Dragon Ball Z - Budokai (USA).iso` | `Dragon Ball Z - Budokai` | Dragon Ball Z: Budokai | `33990` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| ps2 | `Dragon Ball Z - Budokai 2 (USA).iso` | `Dragon Ball Z - Budokai 2` | Dragon Ball Z: Budokai 2 | `56` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| ps2 | `Dragon Ball Z - Budokai 3 (USA) (Greatest Hits).iso` | `Dragon Ball Z - Budokai 3` | Dragon Ball Z: Budokai 3 | `1701` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| ps2 | `Dragon Ball Z - Budokai 3 (USA).iso` | `Dragon Ball Z - Budokai 3` | Dragon Ball Z: Budokai 3 | `1701` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| ps2 | `Dragon Ball Z - Budokai Tenkaichi 3 (USA) (En,Ja).iso` | `Dragon Ball Z - Budokai Tenkaichi 3` | Dragon Ball Z: Budokai Tenkaichi 3 | `33972` | 1.0 | ambiguous / close-results | systematic ROM decoration removed from query |
| ps2 | `Grand Theft Auto - San Andreas (USA) (v3.00).iso` | `Grand Theft Auto - San Andreas` | Grand Theft Auto: San Andreas | `1352` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |
| ps2 | `Grand Theft Auto - Vice City (USA) (v4.00).iso` | `Grand Theft Auto - Vice City` | Grand Theft Auto: Vice City | `1351` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |
| ps2 | `Need for Speed - Underground (USA).iso` | `Need for Speed - Underground` | Need for Speed: Underground | `34529` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| ps2 | `Need for Speed - Underground 2 (USA).iso` | `Need for Speed - Underground 2` | Need for Speed: Underground 2 | `29882` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| ps2 | `Simpsons, The - Hit & Run (USA).iso` | `Simpsons, The - Hit & Run` | The Simpsons: Hit & Run | `34479` | 1.0 | unmatched / low-confidence | token-equivalent title score became credible |
| ps2 | `Tony Hawk's Pro Skater 4 (USA) (v2.01).iso` | `Tony Hawk's Pro Skater 4` | Tony Hawk's Pro Skater 4 | `36189` | 1.0 | ambiguous / close-results | systematic ROM decoration removed from query |
| ps2 | `Tony Hawk's Underground (USA).iso` | `Tony Hawk's Underground` | Tony Hawk's Underground | `34677` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| ps2 | `Tony Hawk's Underground 2 (USA).iso` | `Tony Hawk's Underground 2` | Tony Hawk's Underground 2 | `34243` | 1.0 | ambiguous / close-results | strongest credible candidate accepted despite close second |
| switch | `Crash Team Racing Nitro-Fueled (NSP)(Base Game).nsp` | `Crash Team Racing Nitro-Fueled` | CTR: Crash Team Racing - Nitro-Fueled | `5246172` | 0.9375 | unmatched / low-confidence | systematic ROM decoration removed from query |
| switch | `Mario Kart 8 Deluxe [0100152000022000][v0].nsp` | `Mario Kart 8 Deluxe` | Mario Kart 8 Deluxe | `5249545` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |
| switch | `Mario Kart 8 Deluxe [0100152000022800][v1245184][US].nsp` | `Mario Kart 8 Deluxe` | Mario Kart 8 Deluxe | `5249545` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |
| switch | `Mario.Kart.8.Deluxe.DLC.Booster.Course.Pass.0100152000023001.v65536.nsp` | `Mario Kart 8 Deluxe` | Mario Kart 8 Deluxe | `5249545` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |
| switch | `New Super Mario Bros U Deluxe [0100EA80032EA000][v0].nsp` | `New Super Mario Bros U Deluxe` | New Super Mario Bros. U Deluxe | `5258717` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |
| switch | `Super Mario 3D All-Stars[010049900F546000][US][v0].nsp` | `Super Mario 3D All-Stars` | Super Mario 3D All-Stars | `5266417` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |
| switch | `Super Mario Bros. Wonder[010015100B514000][1.0.0][0][16.0.3].nsp` | `Super Mario Bros Wonder` | Super Mario Bros. Wonder | `5409928` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |
| switch | `Super Mario Odyssey [0100000000010000][v0].nsp` | `Super Mario Odyssey` | Super Mario Odyssey | `5245268` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |
| wii | `Mario Kart Wii (Europe, Australia) (En,Fr,De,Es,It).rvz` | `Mario Kart Wii` | Mario Kart Wii | `36054` | 1.0 | unmatched / low-confidence | systematic ROM decoration removed from query |

## False-Positive Review

The two remaining ambiguous cases were intentionally not auto-selected because each has two equal-title SGDB identities and no provider platform metadata. No newly matched item showed a sequel, remake, or unrelated title selected over a stronger exact/title-equivalent candidate in this corpus. The existing `Black` match remains the only short-title item requiring human awareness of possible title collisions.

## Notes

- Candidate platform metadata was empty for all retained SGDB candidates, so platform compatibility could not be used to break the two residual equal-title ties.
- Expected canonical-ID collapses: two `Dragon Ball Z: Budokai 3` files and three Mario Kart 8 Deluxe files.
- No ScreenScraper or other provider was added.
