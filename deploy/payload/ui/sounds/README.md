# Mudos UI Sounds

The UI audio engine loads these user-replaceable files by their canonical names:

- `ui-navigate.wav`
- `ui-confirm.wav`
- `ui-back.wav`
- `ui-error.wav`

The four zero-byte WAV files in this baseline are placeholders. Missing or
invalid files are ignored by `UiAudioEngine.qml`; replacing a file does not
require a source-code change. Keep files mono or stereo and preferably sampled
at 48 kHz.
