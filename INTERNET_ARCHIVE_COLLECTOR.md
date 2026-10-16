# Internet Archive public-domain collector

This collector is intentionally **review-first**. It never treats an Internet Archive search result, uploader statement, age, or a title alone as proof that a film is public domain.

## How it works

1. `python internet_archive_collector.py --discover` searches Internet Archive for movie items whose metadata advertises a public-domain license and writes `output/internet_archive_candidates.json`. This report is for review only. You can also run Actions → Internet Archive Candidate Scan → Run workflow to generate and download this report without running the YouTube publisher.
2. Review the exact edition, publication/copyright history, soundtrack, restoration/version rights, and whether reuse is permitted in India. Use independent evidence such as an official rights record or a reliable public-domain reference.
3. Add only reviewed items to `config/internet_archive_public_domain.json` using the schema below.
4. `python internet_archive_collector.py --download-approved` rechecks Internet Archive metadata, downloads a supported video file plus thumbnail, verifies size/MD5 where available, and merges a licensed item into the local `metadata.json`. By default it downloads one allowlisted film per run and rotates through the list by India-local date to limit bandwidth and disk use. Set `IA_MAX_ITEMS_PER_RUN` to 2–5 only if needed. The source is marked private for first-pass review.
5. The daily GitHub Actions workflow runs discovery and approved downloads before the existing publisher. The schedule, OAuth secrets, and upload commands are not changed. The candidate report is included in the run artifact.

## Allowlist schema

```json
{
  "items": [
    {
      "identifier": "EXACT_ARCHIVE_ITEM_ID",
      "verified_public_domain": true,
      "verification_url": "https://independent.example.org/rights-evidence",
      "verification_note": "Explain the evidence and why this exact edition is public domain in India; include soundtrack/restoration review.",
      "audio_language": "en",
      "audio_language_verified": true
    }
  ]
}
```

Replace the example values with real evidence before adding an item. The external URL and note are a human attestation; the script cannot determine copyright status in every jurisdiction. Do not set `verified_public_domain` or `audio_language_verified` to true unless you have checked them. The existing pipeline accepts only manually verified Hindi (`hi`) or English (`en`) audio.

## Limits and safety

- The allowlist is empty by default, so no movie is automatically downloaded or falsely labeled public domain.
- Only `.mp4`, `.mkv`, `.mov`, and `.webm` files under the size cap are considered. Default cap: 1500 MB; override with `IA_MAX_FILE_MB`.
- Internet Archive metadata is a discovery signal, not a legal guarantee. Confirm the exact film/version and rights for your intended territory and use.
- First publication stays `private` so you can inspect the edit and attribution before deciding whether to publish publicly.
- Do not put API keys, YouTube OAuth tokens, or other secrets in this allowlist.
