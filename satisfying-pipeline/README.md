# Premium 3D Satisfying Shorts

Procedural vertical 3D animations rendered at 1080x1920, 30 fps, with a pure black stage, vivid color systems, physically based materials and original sound design.

## Visual system

- 11 purpose-built scene families: liquid ripple, domino chain reaction, sphere cascade, prism tunnel, bubble pop wave, helix orbit, orbital ring machine, crystal assembly, particle vortex, sculpted wave field and golden spiral stack.
- 32 high-saturation palettes, 8 geometry families, 8 material looks, 5 camera paths and 4 density levels.
- Every scene renders against true black. The old gradient background, progress meter, level badge, countdown-style UI and end-card overlay have been removed.
- Each scene has its own procedural motion. A small non-text visual payoff layer appears near the end; it does not display a timer or cover the animation with a message.
- Three.js physical materials, multiple light sources, antialiasing, 1080x1920 capture and H.264 high-profile encoding (CRF 17, slow preset).
- Seeded original audio is generated for each recipe, with event sounds and a closing chime sequence.

## Topic variety

Each successful public upload consumes one unique recipe. The topic engine currently has 2,252,800 unique combinations across scene, palette, shape, material, BPM, camera and density. Topic IDs and the append-only history prevent reuse when the saved counter is behind.

## Quality checks

Before upload, the pipeline checks:
- Both video and audio streams exist.
- Resolution is exactly 1080x1920 (9:16).
- Frame rate is 30 fps.
- Duration is between 15 and 60 seconds.
- H.264 encoding and a minimum file size are present.

A file that fails these checks is not sent to YouTube.

## Run modes

In GitHub Actions, choose **3D Satisfying Video**:
- public: render, validate and publish directly as a Public YouTube Short.
- dry: render and validate only; it does not upload or consume the topic.

Scheduled runs use Public mode. Current schedule is four daily IST slots (09:00, 13:00, 17:00 and 21:00). A successful YouTube API upload is written to state/used_topics.jsonl and state/state.json.
