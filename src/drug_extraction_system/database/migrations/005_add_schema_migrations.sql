-- Migration: Add schema_migrations table for tracking applied migrations
-- Date: 2024-12-22

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE schema_migrations IS 'Tracks applied database migrations';

