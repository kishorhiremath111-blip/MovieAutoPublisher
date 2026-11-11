# Reel Pipeline - Voice Matched

A separate MovieAutoPublisher workflow for the bundled voice-matched Reel Pipeline. The generated script uses the same Chatterbox Hindi reference voice from `voice/voice_reference.wav`.

## Only two run choices

Open **Actions -> Reel Pipeline - Voice Matched -> Run workflow**:

- **public** (default and preselected): generate the next unused fact-angle, render a full 1080x1920 video, verify the MP4, save the topic as used, then upload directly to YouTube with `privacyStatus=public`. The MP4 remains downloadable as an Actions artifact.
- **download**: generate and render the next unused fact-angle, save it as used after a successful render, and provide the MP4 artifact without uploading to YouTube.

No preview-duration, quality or music controls are exposed. The output settings are fixed: 1080x1920, 30 fps, Chatterbox Multilingual V3, Hindi, bundled voice reference and music gain 0.20.

## Evergreen topic system

The taxonomy and curated starter facts live in `topics/`:

- `taxonomy.json`: 16 high-level areas and their subcategories.
- `fact_seeds.json`: 158 source-anchored starter fact cards across science, human body, psychology, space, animals, nature, technology, engineering, food, language, history, economics, Earth, oceans, geography and everyday mysteries.
- `template_library.json`: 40 hooks, 25 editorial angles, 40 analogy frames and 40 humour frames.
- `topic_engine.py`: emits the pipeline's native JSON scene format using a fact card and selected wording templates.
- `state/used_topics.jsonl`: persistent no-repeat history.

The structured prompt-composition count is **252,800,000 candidates** (158 x 40 x 25 x 40 x 40). This is a count of combinations, not 252.8 million individually researched facts. There are currently 3,950 semantic fact-angle pairs. The semantic key is fact ID + editorial angle, so changing the hook, analogy or joke cannot make an already-used fact-angle eligible again.

A topic is marked used **after the MP4 is successfully rendered and validated**, before any public upload. That means a YouTube upload failure does not cause the same topic to be generated again. DOWNLOAD mode marks the topic used after successful render as well. History is committed to `main` so the next workflow run sees it. Used records remain in the audit history; they are excluded rather than physically deleted.

## Source and accuracy policy

Starter cards include source anchors from government, university, museum, scientific society, standards-body and educational sources. They are curated topic starters, not a claim that every source page has been independently audited line-by-line in this commit. Before adding or materially changing a claim, verify it against a direct source and keep uncertainty visible. Avoid unsupported numbers, health advice, financial advice, conspiracy claims and sensational wording.

Expansion instructions are in `prompts/HINGLISH_TOPIC_EXPANSION.md`.

## Required exact pipeline ZIP

Upload the supplied archive without extracting, renaming or recompressing it to:

`reel-pipeline-voice-matched/Reel-Pipeline-Voice-Matched.zip`

The workflow checks SHA-256 before extraction:

`f2c1026d31b6f7b6c9bd9188794b7103154d8ee6c46f2010fbfc499bd55fd618`

If missing or changed, the run stops before topic generation or video rendering.

## YouTube connection

The public option reuses the repository's existing Actions secrets:

- `YOUTUBE_CLIENT_SECRET_B64`
- `YOUTUBE_TOKEN_B64`

The token must include a refresh token with the `youtube.upload` scope. The uploader explicitly sets privacy to `public`.

## Automatic runs

The workflow remains manual-only; no new daily schedule is enabled. If a schedule is added later, the delivery-mode expression defaults schedule events to **public**. Existing daily, luxury and 3D workflows are not changed.

## Output

Each completed run uploads its MP4, render log and topic metadata as a GitHub Actions artifact for 14 days. Public runs also include the YouTube Shorts URL result.
