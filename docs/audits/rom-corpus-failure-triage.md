# ROM Corpus Failure Triage

Baseline: 37 supported ROMs, committed in `rom-corpus-baseline.json`. This analysis uses the existing per-file results and cached SGDB candidates only. No thresholds, normalization, aliases, provider behavior, or schema were changed.

## Summary

| Category | Count | Interpretation |
|---|---:|---|
| A | 13 | Top candidate is clearly correct; current matcher is conservative |
| B | 3 | Correct candidate is present but not ranked first |
| C | 10 | Filename normalization/query noise materially hurts the search |
| D | 1 | Correct game is not present in the returned candidate set |
| E | 1 | Candidate identity cannot be disambiguated with available platform/release data |
| F | 0 | Genuinely ambiguous from filename alone |

The 16 ambiguous cases are mostly recoverable margin cases: 13/16 (81.25%) have the clearly correct candidate ranked first. One has the correct candidate second, one has duplicate-title candidates with no platform data, and one appears to lack the correct game in the returned set.

All candidate platform metadata was empty (`[]`) in the baseline cache, for both the top and second candidates. Therefore no SGDB platform evidence was available for any classification below.

## By Platform

| Platform | A | B | C | D | E | F | Total non-matched |
|---|---:|---:|---:|---:|---:|---:|---:|
| genesis | 1 | 0 | 0 | 1 | 0 | 0 | 2 |
| nes | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| ps2 | 10 | 1 | 3 | 0 | 1 | 0 | 15 |
| switch | 0 | 1 | 7 | 0 | 0 | 0 | 8 |
| wii | 0 | 1 | 0 | 0 | 0 | 0 | 1 |
| **Total** | **13** | **3** | **10** | **1** | **1** | **0** | **28** |

## Per-ROM Triage

Platform metadata notation: `none` means SGDB returned no platform metadata for that candidate.

| Platform | Source filename | Normalized query | Top candidate | Score | Second candidate | Score | Platform metadata | Status/method | Class |
|---|---|---|---|---:|---|---:|---|---|---|
| wii | `Mario Kart Wii (Europe, Australia) (En,Fr,De,Es,It).rvz` | `Mario Kart Wii (En,Fr,De,Es,It)` | Mario Kart Wii Deluxe (5323566) | 0.6923 | Mario Kart Wii (36054) | 0.6222 | none / none | unmatched / low-confidence | B |
| ps2 | `Crazy Taxi (USA).cue` | `Crazy Taxi` | Crazy Taxi (21778) | 1.0000 | Crazy Taxi 2 (35507) | 0.9091 | none / none | ambiguous / close-results | A |
| ps2 | `Dragon Ball Z - Budokai (USA).iso` | `Dragon Ball Z - Budokai` | Dragon Ball Z: Budokai (33990) | 0.9333 | Dragon Ball Z: Budokai 3 (1701) | 0.8936 | none / none | ambiguous / close-results | A |
| ps2 | `Dragon Ball Z - Budokai 2 (USA).iso` | `Dragon Ball Z - Budokai 2` | Dragon Ball Z: Budokai 2 (56) | 0.9388 | Dragon Ball Z: Budokai 3 (1701) | 0.8980 | none / none | ambiguous / close-results | A |
| ps2 | `Dragon Ball Z - Budokai 3 (USA) (Greatest Hits).iso` | `Dragon Ball Z - Budokai 3` | Dragon Ball Z: Budokai 3 (1701) | 0.9388 | Dragon Ball Z: Budokai 2 (56) | 0.8980 | none / none | ambiguous / close-results | A |
| ps2 | `Dragon Ball Z - Budokai 3 (USA).iso` | `Dragon Ball Z - Budokai 3` | Dragon Ball Z: Budokai 3 (1701) | 0.9388 | Dragon Ball Z: Budokai 2 (56) | 0.8980 | none / none | ambiguous / close-results | A |
| ps2 | `Dragon Ball Z - Budokai Tenkaichi 3 (USA) (En,Ja).iso` | `Dragon Ball Z - Budokai Tenkaichi 3 (En,Ja)` | Dragon Ball Z: Budokai Tenkaichi 3 (33972) | 0.8571 | Dragon Ball Z: Budokai Tenkaichi 2 (38271) | 0.8312 | none / none | ambiguous / close-results | A |
| ps2 | `Grand Theft Auto - San Andreas (USA) (v3.00).iso` | `Grand Theft Auto - San Andreas (v3.00)` | Grand Theft Auto: San Andreas (1352) | 0.8358 | Grand Theft Auto: San Andreas Misterix Mod (5464348) | 0.7250 | none / none | unmatched / low-confidence | C |
| ps2 | `Grand Theft Auto - Vice City (USA) (v4.00).iso` | `Grand Theft Auto - Vice City (v4.00)` | Grand Theft Auto: Vice City (1351) | 0.8254 | Grand Theft Auto: Vice City Stories (34363) | 0.7606 | none / none | unmatched / low-confidence | C |
| ps2 | `Need for Speed - Underground (USA).iso` | `Need for Speed - Underground` | Need for Speed: Underground (34529) | 0.9455 | Need for Speed: Underground 2 (29882) | 0.9123 | none / none | ambiguous / close-results | A |
| ps2 | `Need for Speed - Underground 2 (USA).iso` | `Need for Speed - Underground 2` | Need for Speed: Underground 2 (29882) | 0.9492 | Need for Speed: Underground J (5498969) | 0.9153 | none / none | ambiguous / close-results | A |
| ps2 | `Shadow of the Colossus (USA).iso` | `Shadow of the Colossus` | Shadow of the Colossus (5414306) | 1.0000 | Shadow of the Colossus (86) | 1.0000 | none / none | ambiguous / close-results | E |
| ps2 | `Simpsons, The - Hit & Run (USA).iso` | `Simpsons, The - Hit & Run` | The Simpsons: Hit & Run (34479) | 0.7500 | The Simpsons Wrestling (38458) | 0.5106 | none / none | unmatched / low-confidence | C |
| ps2 | `Tony Hawk's Pro Skater 4 (USA) (v2.01).iso` | `Tony Hawk's Pro Skater 4 (v2.01)` | Tony Hawk's Pro Skater 2 (35898) | 0.8571 | Tony Hawk's Pro Skater 4 (36189) | 0.8571 | none / none | ambiguous / close-results | B |
| ps2 | `Tony Hawk's Underground (USA).iso` | `Tony Hawk's Underground` | Tony Hawk's Underground (34677) | 1.0000 | Tony Hawk's Underground 2 (34243) | 0.9583 | none / none | ambiguous / close-results | A |
| ps2 | `Tony Hawk's Underground 2 (USA).iso` | `Tony Hawk's Underground 2` | Tony Hawk's Underground 2 (34243) | 1.0000 | Tony Hawk's Underground (34677) | 0.9583 | none / none | ambiguous / close-results | A |
| switch | `Crash Team Racing Nitro-Fueled (NSP)(Base Game).nsp` | `Crash Team Racing Nitro-Fueled (NSP)` | CTR: Crash Team Racing - Nitro-Fueled (5246172) | 0.8219 | CTR (Crash Team Racing) (36474) | 0.6102 | none / none | unmatched / low-confidence | C |
| switch | `Mario Kart 8 Deluxe [0100152000022000][v0].nsp` | `Mario Kart 8 Deluxe [0100152000022000]` | Mario Kart 8 Deluxe (5249545) | 0.6667 | Mario Kart 8 Deluxe: CTGP Deluxe (5459784) | 0.5714 | none / none | unmatched / low-confidence | C |
| switch | `Mario Kart 8 Deluxe [0100152000022800][v1245184][US].nsp` | `Mario Kart 8 Deluxe [0100152000022800][US]` | Mario Kart 8 Deluxe (5249545) | 0.6230 | Mario Kart 8 Deluxe: CTGP Deluxe (5459784) | 0.5676 | none / none | unmatched / low-confidence | C |
| switch | `Mario.Kart.8.Deluxe.DLC.Booster.Course.Pass.0100152000023001.v65536.nsp` | `Mario Kart.8.Deluxe DLC Booster Course Pass.0100152000023001.v65536` | Mario Kart 8 Deluxe: CTGP Deluxe (5459784) | 0.4242 | Mario Kart 8 Deluxe (5249545) | 0.3953 | none / none | unmatched / low-confidence | B |
| switch | `New Super Mario Bros U Deluxe [0100EA80032EA000][v0].nsp` | `New Super Mario Bros U Deluxe [0100EA80032EA000]` | New Super Mario Bros. U Deluxe (5258717) | 0.7436 | New Super Mario Bros. Deluxe! (5357638) | 0.7013 | none / none | unmatched / low-confidence | C |
| switch | `Super Mario 3D All-Stars[010049900F546000][US][v0].nsp` | `Super Mario 3D All-Stars[010049900F546000][US]` | Super Mario 3D All-Stars (5266417) | 0.6857 | Super Mario 3D World + Bowser's Fury (5266526) | 0.5122 | none / none | unmatched / low-confidence | C |
| switch | `Super Mario Bros. Wonder[010015100B514000][1.0.0][0][16.0.3].nsp` | `Super Mario Bros. Wonder[010015100B514000][1.0.0][0][16.0.3]` | Super Mario Bros. Wonder (5409928) | 0.5542 | Super Mario Bros. 3 (36658) | 0.4615 | none / none | unmatched / low-confidence | C |
| switch | `Super Mario Odyssey [0100000000010000][v0].nsp` | `Super Mario Odyssey [0100000000010000]` | Super Mario Odyssey (5245268) | 0.6667 | Super Mario Odyssey 64 (5355169) | 0.6667 | none / none | unmatched / low-confidence | C |
| genesis | `Sonic the Hedgehog (JUE) [!].bin` | `Sonic the Hedgehog (JUE)` | Sonic the Hedgehog 2 (35189) | 0.8636 | Sonic the Hedgehog 3 (37581) | 0.8636 | none / none | ambiguous / close-results | D |
| genesis | `Taz-Mania (U) [!].bin` | `Taz-Mania` | Taz-Mania (37388) | 1.0000 | Taz-Mania 2 (35595) | 0.9000 | none / none | ambiguous / close-results | A |
| nes | `Super Mario Bros (E).nes` | `Super Mario Bros` | Super Mario Bros. (37382) | 0.9697 | Super Mario Bros. 2 (36626) | 0.9143 | none / none | ambiguous / close-results | A |
| nes | `Super Mario Bros 3 (PC10).nes` | `Super Mario Bros 3` | Super Mario Bros. 3 (36658) | 0.9730 | Super Mario Bros. 35 (5266561) | 0.9474 | none / none | ambiguous / close-results | A |

## Low-Confidence Findings

- Filename normalization is the dominant low-confidence issue: Switch product IDs, versions, region tags, and `NSP`/DLC decoration remain in the query for all eight Switch cases; Wii language tags remain in the query.
- SGDB title naming differences are secondary: punctuation/word-order differences affect `The Simpsons: Hit & Run`, and dot-separated Switch names are not normalized into a stable title.
- Sequels/remakes/ports are visible in the ranked alternatives: GTA San Andreas versus Misterix, Vice City versus Vice City Stories, and the Tony Hawk / Mario Kart sequel families.
- Platform aliases are not diagnosable from this baseline because SGDB returned no platform metadata for any candidate. The source platform was known locally, but candidate platform matching was `null` for all rows.
- SGDB search quality is implicated by the Sonic query returning Sonic 2 and Sonic 3 without Sonic 1 in the retained candidate set.
- Insufficient metadata is decisive for the duplicate `Shadow of the Colossus` IDs and would also be valuable for release/platform separation generally.

## Recovery Estimate

- Likely recoverable with conservative deterministic matcher work: **23/28** non-matches. This is the 13 clear top-ranked margin cases plus the 10 query-normalization cases where the intended title is already top-ranked or otherwise obvious.
- Correct candidate present but requiring ranking or product/DLC handling: **3/28** category B cases. These should not be auto-accepted solely from this baseline.
- Cases that appear to need ROM-native or stronger release/platform metadata: **2/28 minimum** (Sonic 1 search absence and duplicate Shadow of the Colossus identity). Exact Switch DLC identity may raise the practical requirement to 3/28.
- Projected conservative match rate after fixing the 23 likely recoverable cases: `(9 + 23) / 37 = 86.5%`.

## Recommendation

Tune SteamGridDB integration first, but only after this triage checkpoint: remove proven filename decoration, improve deterministic title/sequel ranking, and separately handle the 0.10-margin cases. Then introduce a ROM-native provider such as ScreenScraper as a fallback for platform/release identity and missing-search cases. The appropriate V1 direction is therefore a **hybrid**, with SteamGridDB as the first-pass authority and ROM-native metadata for the residual identity cases.

No implementation changes were made as part of this analysis.
