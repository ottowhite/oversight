-- 2D projections (e.g. PaCMAP, UMAP, t-SNE) of paper embeddings, used by
-- the /atlas page to render a paper-cloud scatter plot.
--
-- The (paper_id, projection) composite PK lets us store multiple
-- projections side-by-side ("pacmap_pl_v1", "pacmap_v1", "umap_v2", ...)
-- without conflict. The index on (projection, x, y) supports viewport
-- range queries (WHERE projection = ... AND x BETWEEN ... AND y BETWEEN ...).
CREATE TABLE IF NOT EXISTS paper_projection_2d (
    paper_id    varchar      NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
    projection  varchar      NOT NULL,
    x           real         NOT NULL,
    y           real         NOT NULL,
    created_at  timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (paper_id, projection)
);

CREATE INDEX IF NOT EXISTS paper_projection_2d_proj_xy_idx
    ON paper_projection_2d (projection, x, y);
