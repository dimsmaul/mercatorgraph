-- Speed up annotation overlay lookups (get_node / query_graph).
CREATE INDEX IF NOT EXISTS annotations_project_node_idx
    ON annotations (project_slug, node_id);
