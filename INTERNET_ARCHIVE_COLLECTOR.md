# MovieAutoPublisher: rights-cleared movies, series, anime and Shorts

This workflow supports both edited Shorts/clips and longer movies or episodes. **Editing does not remove copyright**, and a short duration is not permission. It never downloads or publishes from an arbitrary streaming/piracy site. Use only content you created or have permission/licensing to download, edit, and upload to YouTube, or a specific edition whose public-domain status and soundtrack rights have been checked for the intended territory.

## Fail-closed upload gate

Before any media is selected for processing or upload, the publisher requires all of these metadata fields:

- `licensed: true`
- `rights_review_status: "approved"` after a human rights review
- `upload_approved: true` after a separate, explicit human decision to publish
- `rights_basis`: one of `public_domain`, `written_permission`, `license`, or `original_content`
- `rights_verification_url`: HTTPS link to evidence, licence terms, permission, or an official source relevant to this exact content
- `rights_verification_note`: at least 30 characters describing what rights are covered, including editing and YouTube distribution where applicable
- `audio_language` set to `hi` or `en`, and `audio_language_verified: true` after checking the actual audio track

If any requirement is missing, the item is skipped or processing stops before upload. Never mark a source approved merely because a website offers it, because the clip is short, or because it was cropped, subtitled, filtered, dubbed, or otherwise edited. Fair use/fair dealing can be context-specific and is not an automatic guarantee.

## Internet Archive discovery

1. Run `python internet_archive_collector.py --discover` or use Actions → Internet Archive Candidate Scan → Run workflow. This only creates `output/internet_archive_candidates.json`; it does not publish.
2. Independently verify the exact edition, publication/copyright history, soundtrack, restoration/version rights, and rights for use in India. Internet Archive metadata/uploader claims are leads, not proof.
3. Add only verified items to `config/internet_archive_public_domain.json`:
   ```json
   {
     "items": [
       {
         "identifier": "EXACT_ARCHIVE_ITEM_ID",
         "verified_public_domain": true,
         "verification_url": "https://independent.example.org/rights-evidence",
         "verification_note": "Describe evidence for this exact edition, India rights, soundtrack and intended YouTube use.",
         "upload_approved": false,
         "audio_language": "en",
         "audio_language_verified": true
       }
     ]
   }
   ```
4. The collector downloads only allowlisted entries with valid review evidence. The downloaded metadata remains blocked from publication unless `upload_approved` is explicitly set to `true` in that allowlist after you have decided to publish.
5. By default, at most one approved film is downloaded per run. The daily workflow keeps the existing schedule, YouTube secrets, and publisher command; the new rights gate runs before processing/upload.

## Anime, series, full episodes and clips

The existing media metadata supports `type: "anime"`, `type: "series"`, and `type: "movie"`. A licensed full episode does not automatically grant rights to make derivative clips; confirm the permission covers both the full upload and edited clips/Shorts. Store each source file and thumbnail locally under the expected input folders and give each item a unique `id` and `topic_id`.

For content added directly to `metadata.json`, use the same rights-gate fields listed above. Example (replace all sample values with real evidence):

```json
{
  "id": "creator-authorized-anime-clip-001",
  "topic_id": "creator-authorized-anime-clip-001",
  "type": "anime",
  "source": "input/videos/authorized_clip.mp4",
  "thumbnail": "input/thumbnails/authorized_clip.jpg",
  "title": "Authorized anime clip",
  "licensed": true,
  "license": "Written permission allows editing and YouTube Shorts distribution; see evidence link.",
  "rights_basis": "written_permission",
  "rights_review_status": "approved",
  "upload_approved": false,
  "rights_verification_url": "https://example.org/permission-or-license",
  "rights_verification_note": "Written permission from the rights holder covers this exact clip, editing, and YouTube Shorts distribution.",
  "audio_language": "en",
  "audio_language_verified": true
}
```

Keep `upload_approved: false` until you have checked the evidence and are ready to publish. The link and note are human attestations; code cannot determine copyright status automatically. Do not store tokens, API keys, or OAuth credentials in metadata or allowlists.
