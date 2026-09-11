# ROM Corpus Metadata Baseline

Audited files: 37

## Platform Results

| Platform | Total | Matched | Ambiguous | Low confidence | Unmatched | Network error |
|---|---:|---:|---:|---:|---:|---:|
| genesis | 2 | 1 | 1 | 0 | 0 | 0 |
| nes | 2 | 2 | 0 | 0 | 0 | 0 |
| ps2 | 24 | 23 | 1 | 0 | 0 | 0 |
| switch | 8 | 8 | 0 | 0 | 0 | 0 |
| wii | 1 | 1 | 0 | 0 | 0 | 0 |

## Canonical ID Collisions

- `1701`: 2 files, Dragon Ball Z: Budokai 3; classification `expected-collapse`.
- `5249545`: 3 files, Mario Kart 8 Deluxe; classification `expected-collapse`.

## Unsupported Platform Files

{".": 3, "gb": 3, "gba": 69, "gbc": 5, "nds": 6, "ngc": 4, "ps": 100, "ps3": 113, "snes": 7}

## Representative Items

### matched
- `wii` `Mario Kart Wii (Europe, Australia) (En,Fr,De,Es,It).rvz` -> `Mario Kart Wii` -> `Mario Kart Wii` (36054, confidence 1.0)
- `ps2` `007 - Nightfire (USA).iso` -> `007 - Nightfire` -> `007: Nightfire` (12863, confidence 1.0)
- `ps2` `Athens 2004 (USA).iso` -> `Athens 2004` -> `Athens 2004` (5274456, confidence 1.0)
- `ps2` `Black (USA).iso` -> `Black` -> `Black` (35919, confidence 1.0)
- `ps2` `Burnout 3 - Takedown (USA).iso` -> `Burnout 3 - Takedown` -> `Burnout 3: Takedown` (37348, confidence 1.0)
- `ps2` `Burnout Revenge (USA).iso` -> `Burnout Revenge` -> `Burnout Revenge` (37108, confidence 1.0)
- `ps2` `Crazy Taxi (USA).cue` -> `Crazy Taxi` -> `Crazy Taxi` (21778, confidence 1.0)
- `ps2` `Dragon Ball Z - Budokai (USA).iso` -> `Dragon Ball Z - Budokai` -> `Dragon Ball Z: Budokai` (33990, confidence 1.0)
- `ps2` `Dragon Ball Z - Budokai 2 (USA).iso` -> `Dragon Ball Z - Budokai 2` -> `Dragon Ball Z: Budokai 2` (56, confidence 1.0)
- `ps2` `Dragon Ball Z - Budokai 3 (USA) (Greatest Hits).iso` -> `Dragon Ball Z - Budokai 3` -> `Dragon Ball Z: Budokai 3` (1701, confidence 1.0)
### ambiguous
- `ps2` `Shadow of the Colossus (USA).iso` -> `Shadow of the Colossus` -> `` (, confidence 1.0)
- `genesis` `Sonic the Hedgehog (JUE) [!].bin` -> `Sonic the Hedgehog` -> `` (, confidence 1.0)
### low-confidence
- None
### network-error
- None
### unmatched
- None

## Review Examples

### Normalization Review
- None
### Likely False Positives
- `ps2` `Black (USA).iso` -> `Black` (Black, 35919, confidence 1.0)
### Likely False Negatives
- `ps2` `Shadow of the Colossus (USA).iso` -> `Shadow of the Colossus` (, , confidence 1.0)
- `genesis` `Sonic the Hedgehog (JUE) [!].bin` -> `Sonic the Hedgehog` (, , confidence 1.0)
### Punctuation Review
- `ps2` `Simpsons, The - Hit & Run (USA).iso` -> `Simpsons, The - Hit & Run` (The Simpsons: Hit & Run, 34479, confidence 1.0)
- `ps2` `Tony Hawk's Pro Skater 4 (USA) (v2.01).iso` -> `Tony Hawk's Pro Skater 4` (Tony Hawk's Pro Skater 4, 36189, confidence 1.0)
- `ps2` `Tony Hawk's Underground (USA).iso` -> `Tony Hawk's Underground` (Tony Hawk's Underground, 34677, confidence 1.0)
- `ps2` `Tony Hawk's Underground 2 (USA).iso` -> `Tony Hawk's Underground 2` (Tony Hawk's Underground 2, 34243, confidence 1.0)
- `genesis` `Sonic the Hedgehog (JUE) [!].bin` -> `Sonic the Hedgehog` (, , confidence 1.0)
- `genesis` `Taz-Mania (U) [!].bin` -> `Taz-Mania` (Taz-Mania, 37388, confidence 1.0)
