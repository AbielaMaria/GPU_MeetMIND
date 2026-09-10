MEETMIND BENCHMARK DATASET
============================

This folder contains metadata.csv and an audio/ directory.

You must record the 25 utterances listed in MeetMind_25_Recording_Content.txt
and save the recordings as the exact filenames below:

tamil_01.wav ... tamil_05.wav
english_01.wav ... english_05.wav
codemix_01.wav ... codemix_10.wav
meeting_01.wav ... meeting_05.wav

Recommended:
- Natural speech
- Quiet room for some recordings
- Some realistic background noise for a few recordings
- 16 kHz mono WAV is ideal, but the benchmark notebook can convert common formats
- For meeting recordings, use 2–3 speakers where possible

IMPORTANT:
metadata.csv already contains the ground-truth transcript. If your actual spoken
recording differs from the provided sentence, edit the corresponding reference
cell in metadata.csv so it exactly matches what was spoken.
