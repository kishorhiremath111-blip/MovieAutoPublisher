# Hinglish Everyday Mystery Topic Expansion Prompt

Use this prompt only to add NEW records to `topics/fact_seeds.json`. Do not rewrite or delete existing IDs.

## Editorial goal

Create friendly, short, accurate Hinglish explainers about things people see, use, eat, hear or experience but may not know the exact mechanism behind. The voice should feel like a smart, funny human friend—not a lecturer, fake guru or clickbait channel.

## Coverage

Rotate across: Physics, Chemistry, Biology, Human Body, Psychology, Space/Astronomy, Animals, Nature/Ecology, Weather/Earth, Technology, Engineering, Food Science, Language/Linguistics, History/Culture, Money/Economics, Geography/Oceans and surprising everyday mysteries.

## Every candidate needs

- One precise, single-question topic (avoid broad vague topics).
- A short, evidence-aligned answer.
- One concise explanation of the actual mechanism.
- A common misconception only when that misconception is genuinely common.
- A simple analogy that does not change the science.
- One light, kind joke; never mock a person or group.
- One useful bonus fact.
- A source URL to a government, university, museum, scientific society, standards body, or peer-reviewed/primary source.
- Stable unique ID and searchable category/subcategory.

## Quality gates

1. Never invent a statistic, quote, historical anecdote or causal explanation.
2. Distinguish established facts from hypotheses and open research questions.
3. No medical diagnosis, treatment instructions, financial advice or conspiracy claims.
4. Reject a candidate if it is a wording-only variation of an existing question.
5. Keep the spoken script under about 60 seconds, with short conversational sentences.
6. Avoid repeating recent category clusters; rotate topics.
7. Check every claim against the linked source before merging.

## Scale model

The current catalogue is a curated starter bank. Its structured prompt-composition pool is:

`fact cards × hook templates × editorial angles × analogy frames × humour frames`.

Template combinations are prompt candidates, not independently researched scientific facts. The semantic-key guard prevents the same fact-angle from being selected again after a successful video.
