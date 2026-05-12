# scripts/

One-off and recurring scripts that don't belong in `src/oversight/`.

## `load_pacmap_coords.py`

Streams a CSV of 2D-projection coordinates into the `paper_projection_2d`
table (created by `db/init/002-paper-atlas.sql`). The CSV must have at
least `paper_id`, `x`, `y` columns; extra columns (`title`, `source`,
`update_date`) are ignored — they're joined from `paper` at query time.

Each `(paper_id, projection)` pair is upserted, so re-running with the
same `--projection` name updates in place. Pass a fresh `--projection`
to store multiple runs side-by-side.

### Run with the 18k PL test CSV

```bash
set -a; . ./.env; set +a
export DATABASE_URL="${DATABASE_URL/@oversight-db:/@localhost:}"
uv run python scripts/load_pacmap_coords.py \
    --csv /tmp/pacmap_pl.csv \
    --projection pacmap_pl_v1
```

### Re-run with the full 940k corpus CSV (when it lands)

```bash
set -a; . ./.env; set +a
export DATABASE_URL="${DATABASE_URL/@oversight-db:/@localhost:}"
uv run python scripts/load_pacmap_coords.py \
    --csv /tmp/pacmap_all.csv \
    --projection pacmap_v1
```

The `--projection` value is what the frontend passes via the
`?projection=` query param on `/api/atlas`; update `frontend/pages/atlas.tsx`
if you want it to default to the new name.
