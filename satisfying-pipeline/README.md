# Satisfying 3D Shorts

A deterministic 3D Shorts pipeline. Each successful public upload consumes one unique recipe; dry runs never consume a topic.

## Features

- 6,912,000 unique combinations of six scenes, palettes, shapes, materials, BPMs, camera moves, densities, and backgrounds.
- Every title includes a unique level/topic identifier.
- A progress bar and level badge stay on screen. The final 3.6 seconds show a PERFECT FINISH / NEXT LEVEL card.
- Audio is synthesized locally for each topic. Scale, motif, root, timbre, event pitches, and ending chimes are seeded from the topic ID.
- Uploads are Public and submitted with YouTube's self-declared not-made-for-kids flag set to false.
- After a confirmed upload, the MP4 is deleted, the counter advances, and the topic ID is recorded in the append-only history.
- The history is checked before rendering. If the counter ever points at a used topic, the pipeline skips forward.

## Run modes

In GitHub Actions, choose the workflow named 3D Satisfying Video:
- public: render and publish directly as a Public YouTube Short.
- dry: render and quality-check only. It does not upload or consume the topic.

The scheduled run is a public publishing run. Daily Motivator Video is a separate workflow and does not create these 3D topic videos.
