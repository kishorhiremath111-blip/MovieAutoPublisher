# AI Updates Video Publisher

This is a separate workflow. It does not modify the existing MovieAutoPublisher daily workflow, its schedule, or its secrets.

## What it does
- Checks official OpenAI, Google DeepMind, and Google AI RSS feeds.
- Selects an unseen official update, writes a short narration from the source headline/summary, and creates a vertical video with original graphics and local English text-to-speech.
- Includes the primary source link in the description.
- Stops rather than re-uploading a source link already recorded in the deduplication state.
- Scheduled runs upload the result publicly to YouTube using the existing `YOUTUBE_CLIENT_SECRET_B64` and `YOUTUBE_TOKEN_B64` GitHub Actions secrets.
- Manual runs default to draft-only. Set the `publish` input to true to upload manually triggered runs.

## Important limitations
This is a lightweight news-explainer video with original graphics and synthetic narration, not a fully generative 3D animation. It uses official RSS headlines and summaries; the narration is not produced by a paid LLM. Free RSS/TTS/rendering do not guarantee unlimited service or YouTube monetization. Review the first artifact and channel policy before enabling scheduled public uploads.

## Workflow
GitHub Actions → AI Updates Video Publisher. The schedule is separate from the existing movie workflow. The existing MovieAutoPublisher workflow remains unchanged.
