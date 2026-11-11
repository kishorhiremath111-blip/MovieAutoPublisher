# Reel Pipeline - Voice Matched

A separate MovieAutoPublisher workflow for the exact voice-matched pipeline ZIP. It preserves the bundled script, scene renderer, fonts, demo, and reference audio.

## Only two run choices

Open **Actions -> Reel Pipeline - Voice Matched -> Run workflow**:

- **public** (default, preselected): render the complete 1080x1920 video with the bundled Chatterbox Hindi speaker reference, validate it, then upload directly to YouTube with `privacyStatus=public`. The run prints the Shorts URL and also retains the MP4 as a downloadable artifact.
- **download**: render the same complete MP4 and make it available in the GitHub Actions artifact. It deliberately skips YouTube upload.

There are no preview-duration, quality, or music controls in the form. Settings are fixed in the workflow: 1080x1920, 30 fps, Chatterbox V3, Hindi, the bundled voice reference, and music gain 0.20.

## Required exact ZIP

Upload the supplied archive without extracting, renaming, or recompressing it to:

`reel-pipeline-voice-matched/Reel-Pipeline-Voice-Matched.zip`

The workflow checks its SHA-256 before extraction:

`f2c1026d31b6f7b6c9bd9188794b7103154d8ee6c46f2010fbfc499bd55fd618`

If it is missing or changed, the workflow stops before rendering.

## YouTube connection

The public option reuses the repository's existing GitHub Actions secrets:

- `YOUTUBE_CLIENT_SECRET_B64`
- `YOUTUBE_TOKEN_B64`

The token must contain a valid refresh token authorized for the `youtube.upload` scope. The uploader explicitly sets YouTube privacy to `public`. It does not use the Edge TTS voice or a different fallback speaker.

## Automatic runs

The workflow is manual-only until a schedule is explicitly added. If a schedule trigger is added later, the workflow's delivery-mode expression defaults that event to **public**. No new posting schedule is enabled here, so this change will not create unrequested automatic uploads.

## Output

Every successful render is saved as the `reel-pipeline-voice-matched-N` artifact for 14 days. In public mode, the artifact contains the MP4 and YouTube upload result; in download mode, it contains the MP4 and render log.
