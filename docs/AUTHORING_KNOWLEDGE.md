# Authoring the knowledge bundle

The assistant answers only from the OKF bundle in `knowledge/`. To adapt this
project to a real organisation:

1. Replace the placeholder concepts under `knowledge/` with your own. Keep one
   directory per topic, each with an `index.md` that links its concepts.
2. Give every concept YAML frontmatter with at least `type`, `title`,
   `description`, and `tags`. Use `status: draft` until a human reviewer has
   verified it, and `status: deprecated` plus `superseded_by:` for retired
   guidance.
3. Reference sources with `sources: [{id, resource: "file:...", title, author}]`;
   the validator checks that referenced files exist.
4. Update `app/sales_agent/calc_tools.py` (discount codes, proration scenarios,
   refund rules) and the system instruction in `app/sales_agent/agent.py` so the
   tools and the prompt describe your real policy.
5. Update the concept-ID mapping in `app/client/js/transcript.js` so tool calls
   produce the right citation chips.
6. Update the expectations in `tests/test_okf_tools.py` and run:

```bash
uv run python tools/okf_build/validate.py knowledge
uv run pytest
```

Do not mark content human-verified until your own review gate has passed.
