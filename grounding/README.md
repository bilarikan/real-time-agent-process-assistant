# Grounding sources

Put your original source documents here (price lists, process SOPs, policy PDFs,
spreadsheets, call recordings and transcripts). They are the raw material from
which the OKF bundle in `../knowledge/` is authored.

This repository ships no source documents. **Only commit material you have the
right to publish**; keep proprietary or confidential sources out of any public
repository (add them to `.gitignore` or keep them in a private location).

Concepts in `knowledge/` can point back at a source with a relative file
reference in their frontmatter, which `tools/okf_build/validate.py` checks:

```yaml
sources:
  - id: example-price-list
    resource: "file:../../grounding/example-price-list.pdf"
    title: Example price list
    author: human:your-name
```
