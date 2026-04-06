# x-news Eval Infrastructure

Eval harness for x-news skills, providing reproducible quality assessment.

## CLI

```bash
PYTHONPATH=src python3 eval/cli.py <command> [options]
```

## Commands

| Command | Description |
|---------|-------------|
| `eval diagnose --date 2026-04-01` | Diagnose quality issues for a date |
| `eval run --date 2026-04-01 --with-fixtures` | Run eval with fixture data |
| `eval benchmark --date 2026-04-01 --runs 8` | Multi-run aggregate metrics |
| `eval suite --suite suite-2026-04-01` | Run full pipeline suite |
| `eval compare <run-a> <run-b>` | Compare two runs |
| `eval history` | Historical eval pass rates |
| `eval cases list` | List all cases |

## Structure

```
eval/
├── cases/
│   ├── suites/
│   │   └── suite-2026-04-0X.json
│   ├── x-news-fetch/
│   │   └── case-2026-04-0X.json
│   └── x-news-digest/
│       └── case-2026-04-0X.json
├── fixtures/
│   ├── 2026-04-01/
│   │   ├── filtered.json
│   │   ├── post.json
│   │   └── post.md
│   └── 2026-04-02/
└── runs/              # eval output (gitignored)
```

## Quality Checks

### x-news-fetch
- filtered.json has required structure (stats, strong, medium, backfill)
- Candidate count within expected range

### x-news-digest
- post.json has valid frontmatter fields
- Categories from allowed set
- Item titles are Chinese, not direct copies
- Item bodies are Chinese, minimum length
- No placeholder text
- Item count in 8-12 range

### Multi-run Stability
- Jaccard similarity >= 0.75 across runs (candidate/selected IDs)
