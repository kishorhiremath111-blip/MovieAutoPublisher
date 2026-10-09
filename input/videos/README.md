# Add authorized source videos for VYROX-2008

The daily workflow is configured for up to **3 Shorts** plus one separate long-form highlight video. It will not download movie/series/anime footage from third-party sites.

## Add your source files

Place four or more distinct, original or properly licensed source videos in `input/videos/` and their matching thumbnails in `input/thumbnails/`.

Supported video extensions: `.mp4`, `.mkv`, `.mov`, `.webm`.

Each source must have:
- Permission/license that allows editing and publishing on your channel.
- A matching thumbnail image.
- A unique `id` and `topic_id`.
- `type`: `movie`, `series`, or `anime`.
- `licensed: true` only when you have verified the rights.
- `audio_language`: `hi` or `en`, and `audio_language_verified: true` only after checking the actual audio.

## Register each file in `metadata.json`

Use paths relative to the repository root, for example:

```json
{
  "items": [
    {
      "id": "licensed-movie-clip-01",
      "topic_id": "licensed-movie-topic-01",
      "title": "Your licensed movie title",
      "type": "movie",
      "source": "input/videos/movie-clip-01.mp4",
      "thumbnail": "input/thumbnails/movie-clip-01.jpg",
      "licensed": true,
      "audio_language": "hi",
      "audio_language_verified": true,
      "description": "Original description and source/license notes.",
      "tags": ["VYROX-2008", "Shorts"],
      "privacy_status": "private"
    }
  ]
}
```

Repeat the object for every distinct source; use the correct type for each source. The example above is a template only—do not use it as a real source entry until you replace the filenames and verify rights/audio.

## Before publishing

- Keep YouTube OAuth Actions secrets configured.
- Run the GitHub Actions workflow manually first and inspect its logs/artifacts.
- Start with `privacy_status: "private"` to review the edits and watermark before changing to public.
- A brand watermark or crop/effects does not grant copyright permission. Only submit footage you own or are authorized to edit and publish.
