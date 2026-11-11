# Evergreen Topics System

- `taxonomy.json`: hierarchical editorial taxonomy.
- `fact_seeds.json`: curated starter bank; each fact includes a source anchor.
- `template_library.json`: Hinglish hooks, angles, analogy frames and humour frames.
- `../topic_engine.py`: selects one unused fact-angle pair and emits renderer-compatible JSON.
- `../state/used_topics.jsonl`: durable no-repeat history, committed after successful public upload or successful download render.

Current catalogue: 158 curated starter fact cards, 16 high-level categories, 40 hooks, 25 editorial angles, 40 analogy frames and 40 humour frames. This creates 252,800,000 candidate prompt compositions. That number describes combinations, not 252.8M individually researched facts.

A semantic key is derived from fact ID + editorial angle. Once consumed, all wording-only alternatives for that same fact-angle are blocked. Add new source-checked fact cards to expand the actual knowledge bank.
