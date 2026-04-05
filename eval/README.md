# x-news Eval Infrastructure

Eval harness for x-news skills, providing reproducible quality assessment.

## CLI Entry Point

```bash
python3 eval/cli.py <command> [options]
# or
python3 -m eval.cli <command> [options]
```

## Commands

### Diagnostic (when something goes wrong)

| Command | Description |
|---------|-------------|
| `eval diagnose --date 2026-04-01` | Diagnose quality issues for a given date's artifacts |
| `eval compare <run-a> <run-b>` | Compare artifacts from two runs |

### Rerun (after fixing issues)

| Command | Description |
|---------|-------------|
| `eval run --date 2026-04-01 --with-fixtures` | Run eval with fixture data (fixture_copy mode) |
| `eval run --date 2026-04-01 --with-fixtures --runs 8` | Run with 8 iterations for stability check |
| `eval suite --suite suite-2026-04-01` | Run full pipeline suite |

### Statistical Analysis

| Command | Description |
|---------|-------------|
| `eval benchmark --date 2026-04-01` | Run multiple iterations and show aggregate metrics |
| `eval history` | View historical eval run pass rates |

### Case Management

| Command | Description |
|---------|-------------|
| `eval cases list` | List all cases and fixtures |
| `eval cases list --skill x-news-editorial` | List cases for a specific skill |

## Case Structure

```
eval/
├── cases/
│   ├── suites/
│   │   ├── suite-2026-04-01.json
│   │   └── suite-2026-04-02.json
│   ├── x-news-data-pipeline/
│   │   ├── case-2026-04-01.json
│   │   └── case-2026-04-02.json
│   ├── x-news-editorial/
│   │   └── case-2026-04-01.json
│   └── x-news-to-daily-post/
│       └── case-2026-04-01.json
├── fixtures/
│   ├── 2026-04-01/
│   │   ├── filtered.json
│   │   ├── companion.json
│   │   └── post.md
│   └── 2026-04-02/
└── runs/
    └── <date>/
        └── <timestamp>-<mode>-<id>/
            ├── request/
            │   └── case.json
            ├── results/
            │   ├── artifacts/
            │   ├── run-001/
            │   │   ├── metrics.json
            │   │   └── judge.json
            │   ├── benchmark.json
            │   └── analysis.md
            └── summary/
```

## Case Schema

```json
{
  "id": "case-2026-04-01",
  "skill": "x-news-editorial",
  "report_date": "2026-04-01",
  "execution_mode": "fixture_copy",
  "runs": 8,
  "inputs": {
    "report_boundary": "2026-04-01T06:00:00+08:00",
    "report_time": "2026-04-01"
  },
  "artifacts": {
    "filtered.json": "eval/fixtures/2026-04-01/filtered.json",
    "companion.json": "eval/fixtures/2026-04-01/companion.json"
  },
  "expected": {
    "selected_count_min": 8,
    "selected_count_max": 12,
    "allowed_categories": ["模型发布", "开发生态", "技术洞察", "产品动态", "安全事件", "行业观点"]
  }
}
```

## Assertions

### Programmatic Checks

- `companion.json stats.selected == len(items)`
- `post.json item count == companion.json item count`
- JSON schema validation passes
- No information loss across stages
- Selected canonical_ids in expected range

### Multi-run Variance Checks

- Jaccard similarity >= 0.75 across runs (runs>=8)
- Below threshold = FAIL, record unstable case

### Editorial Review Dimensions

- Summary quality (CJK, detail density, redundancy)
- Topic focus (AI relevance)
- Coverage match
