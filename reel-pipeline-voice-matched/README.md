# Reel Pipeline - Voice Matched

This is a separate, manually triggered workflow for the supplied voice-matched Reel Pipeline. It does not modify or call the repository's existing daily, 3D, luxury, or voice-test workflows.

## Required ZIP location

Upload the exact supplied archive to this path without extracting, renaming, or recompressing it:

`reel-pipeline-voice-matched/Reel-Pipeline-Voice-Matched.zip`

The workflow verifies the archive's SHA-256 before extracting it. Expected SHA-256:

`f2c1026d31b6f7b6c9bd9188794b7103154d8ee6c46f2010fbfc499bd55fd618`

Until that binary ZIP is present at the path above, the workflow stops with a clear missing-archive error.

## Run

Open **Actions -> Reel Pipeline - Voice Matched -> Run workflow**. Choose `preview` for a short test or `full` for the complete bundled Aasman Neela demo. The workflow uses the bundled `voice/voice_reference.wav` with Chatterbox Multilingual V3, Hindi (`hi`), and CPU inference. It never selects Edge TTS or another fallback voice.

Generated MP4 and render logs are uploaded as a workflow artifact. This workflow is manual-only and does not upload to YouTube.

Use the reference voice only with the speaker's permission.