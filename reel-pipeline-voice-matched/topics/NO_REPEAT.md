# Topic engine: no-repeat rule

The engine treats one `fact_id + angle_id` as a semantic topic. The style-only hook, analogy and humour IDs are not part of the semantic key. Once the video is successfully rendered and validated, the workflow appends the semantic key to `state/used_topics.jsonl` and commits it before the public YouTube upload step. This ensures a later run cannot choose the same fact-angle just because the wording templates changed.

Failed render/validation does not consume a topic. Public upload failure happens after consumption because the video has already been successfully generated. Add new records only after source review; do not delete history rows.
