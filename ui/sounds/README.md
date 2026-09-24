# Mudos UI Sounds

The shared UI audio engine loads these replaceable files through SDL's
audio-only playback path:

- `ui-navigate.wav`
- `ui-confirm.wav`
- `ui-back.wav`
- `ui-error.wav`

The shipped effects are mono, 16-bit PCM WAV files:

| File | Sample rate | Duration | Event |
| --- | ---: | ---: | --- |
| `ui-navigate.wav` | 22,050 Hz | 0.080 s | Accepted navigation action |
| `ui-confirm.wav` | 22,050 Hz | 0.785 s | Confirm/options action |
| `ui-back.wav` | 24,750 Hz | 0.804 s | Back action |
| `ui-error.wav` | 9,270 Hz | 1.867 s | User-visible request failure |

The native shell resolves them beneath the `sounds` directory beside the QML
file it loaded, including the development runtime. SDL converts them to the
default playback device format; missing or invalid files are reported and
ignored. Keep files mono or stereo PCM WAV.

Current event mapping: accepted controller direction/shoulder action →
`ui-navigate.wav`; confirm/options → `ui-confirm.wav`; back → `ui-back.wav`;
user-visible request failure → `ui-error.wav`. SDL opens the system default
playback device only on the first sound request and streams to that device;
new cues replace buffered audio so rapid input cannot build a delayed queue.
The native playback boundary applies a conservative fixed gain of 0.35.
