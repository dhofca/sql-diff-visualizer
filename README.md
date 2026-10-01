# SQL Schema Diff

A local tool for comparing MySQL database structure between environments.
Upload two `.sql` structure dumps: **PROD** (baseline) and **PREPROD** (new version).
You get a tree with the differences highlighted, exportable to SVG. "Added" = present in preprod, missing
in prod; "removed" = present in prod, missing in preprod.

Runs entirely locally: the server listens on `127.0.0.1` only, files are processed in memory and are never
stored or logged, and the frontend loads nothing from the internet.

## Running

```bash
./run.sh            # first run creates .venv and installs dependencies
# → http://127.0.0.1:8765
```

## Exporting the structure

```bash
mysqldump --no-data --routines --triggers --events -u USER -p DB > release_X.sql
```

## What is compared

| Element | Attributes |
|---|---|
| Tables | engine, charset, collate, row_format, comment, CHECK |
| Columns | type, NULL/NOT NULL, default, AUTO_INCREMENT, ON UPDATE, generated, charset, collation, comment |
| Indexes | kind (PRIMARY/UNIQUE/INDEX/FULLTEXT/SPATIAL), columns |
| Foreign keys | columns, references, ON DELETE / ON UPDATE |
| Views, triggers, procedures, functions, events | normalized definition text |

Normalization (ignored to avoid false positives): the `AUTO_INCREMENT=` counter, `DEFINER`,
`ALGORITHM`, `SQL SECURITY`, integer display width (`int(11)` = `int`, except `tinyint(1)`),
whitespace, comments, column order.

## Layout

```
backend/parser.py   dump → model (sqlglot + custom statement / DELIMITER splitter)
backend/diff.py     prod vs preprod model → tree with added/removed/modified/unchanged statuses
backend/main.py     FastAPI: POST /api/diff + serves the frontend
frontend/           D3 (vendored), filters, details panel, SVG export
```

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
python scripts/generate_fixtures.py /tmp   # synthetic pair of ~110-table dumps
```
