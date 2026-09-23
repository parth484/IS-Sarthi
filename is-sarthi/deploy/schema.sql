-- IS Sarthi -- PostgreSQL schema
-- System of record plus the audit substrate that makes recommendations
-- defensible in a procurement dispute.

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fuzzy title lookup
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------- standards

CREATE TABLE IF NOT EXISTS is_standards (
    is_number            TEXT PRIMARY KEY,          -- canonical: "IS 1554-1"
    raw_designation      TEXT,                      -- as printed on the source
    title                TEXT,
    year                 INTEGER,
    status               TEXT NOT NULL DEFAULT 'current'
                         CHECK (status IN ('current','withdrawn','superseded','under_revision')),
    division             TEXT,
    scope                TEXT,
    amendments           JSONB NOT NULL DEFAULT '[]',
    normative_references JSONB NOT NULL DEFAULT '[]',
    certification        JSONB NOT NULL DEFAULT '{}',
    supersedes           TEXT,
    superseded_by        TEXT,

    -- change detection
    content_hash         TEXT,
    scope_hash           TEXT,
    extraction_quality   REAL DEFAULT 0,

    -- provenance
    source_url           TEXT,
    sources              TEXT[] NOT NULL DEFAULT '{}',
    first_seen           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_changed         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    corpus_version       INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_std_status       ON is_standards(status);
CREATE INDEX IF NOT EXISTS idx_std_division     ON is_standards(division);
CREATE INDEX IF NOT EXISTS idx_std_year         ON is_standards(year);
CREATE INDEX IF NOT EXISTS idx_std_last_changed ON is_standards(last_changed DESC);
CREATE INDEX IF NOT EXISTS idx_std_title_trgm   ON is_standards USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_std_refs         ON is_standards USING gin (normative_references);
CREATE INDEX IF NOT EXISTS idx_std_cert         ON is_standards USING gin (certification);
-- Partial index: the hot path always filters to current standards.
CREATE INDEX IF NOT EXISTS idx_std_current      ON is_standards(division, year)
    WHERE status = 'current';

-- -------------------------------------------------------------------- audit

CREATE TABLE IF NOT EXISTS is_standards_audit (
    id           BIGSERIAL PRIMARY KEY,
    is_number    TEXT NOT NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    change_type  TEXT NOT NULL,
    changed_fields TEXT[],
    old_values   JSONB,
    new_values   JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_is_number  ON is_standards_audit(is_number);
CREATE INDEX IF NOT EXISTS idx_audit_changed_at ON is_standards_audit(changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_type       ON is_standards_audit(change_type);

CREATE OR REPLACE FUNCTION log_is_change() RETURNS TRIGGER AS $$
DECLARE
    change_kind TEXT;
BEGIN
    IF OLD.content_hash IS DISTINCT FROM NEW.content_hash
       OR OLD.scope_hash IS DISTINCT FROM NEW.scope_hash THEN

        -- Classify so the changelog is queryable by consequence, not just by
        -- timestamp. Withdrawal outranks everything: it is the change a
        -- procurement official most needs to be told about.
        IF NEW.status IN ('withdrawn','superseded')
           AND OLD.status NOT IN ('withdrawn','superseded') THEN
            change_kind := 'withdrawn';
        ELSIF OLD.certification IS DISTINCT FROM NEW.certification THEN
            change_kind := 'certification';
        ELSIF OLD.scope_hash IS DISTINCT FROM NEW.scope_hash THEN
            change_kind := 'scope';
        ELSIF OLD.normative_references IS DISTINCT FROM NEW.normative_references THEN
            change_kind := 'references';
        ELSIF jsonb_array_length(NEW.amendments) > jsonb_array_length(OLD.amendments) THEN
            change_kind := 'amendment';
        ELSE
            change_kind := 'metadata';
        END IF;

        INSERT INTO is_standards_audit (is_number, change_type, old_values, new_values)
        VALUES (
            NEW.is_number,
            change_kind,
            jsonb_build_object('title', OLD.title, 'year', OLD.year,
                               'status', OLD.status, 'amendments', OLD.amendments,
                               'certification', OLD.certification),
            jsonb_build_object('title', NEW.title, 'year', NEW.year,
                               'status', NEW.status, 'amendments', NEW.amendments,
                               'certification', NEW.certification)
        );

        NEW.last_changed := NOW();
        NEW.corpus_version := OLD.corpus_version + 1;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS is_standards_audit_trigger ON is_standards;
CREATE TRIGGER is_standards_audit_trigger
BEFORE UPDATE ON is_standards
FOR EACH ROW EXECUTE FUNCTION log_is_change();

-- ------------------------------------------------------- certification rules

CREATE TABLE IF NOT EXISTS certification_rules (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    is_number         TEXT NOT NULL,
    scheme            TEXT NOT NULL
                      CHECK (scheme IN ('ISI','CRS','Hallmarking','Other')),
    scheme_label      TEXT,
    product_category  TEXT,
    mandatory         BOOLEAN NOT NULL DEFAULT TRUE,
    gazette_url       TEXT,
    gazette_title     TEXT,
    effective_date    DATE,
    recorded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (is_number, scheme)
);

CREATE INDEX IF NOT EXISTS idx_cert_is_number ON certification_rules(is_number);

-- ------------------------------------------------- recommendation audit trail

CREATE TABLE IF NOT EXISTS recommendation_log (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_text       TEXT NOT NULL,
    query_language   TEXT DEFAULT 'en',
    recommended      JSONB NOT NULL,       -- full served payload
    confidence_top   REAL,
    corpus_snapshot  JSONB,                -- corpus_version of each standard served
    retrieval_ms     INTEGER,
    total_ms         INTEGER,
    user_ref         TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reclog_created ON recommendation_log(created_at DESC);
-- Queries that returned nothing confident are the most valuable operational
-- signal in the system: they show BIS where the catalog is undiscoverable.
CREATE INDEX IF NOT EXISTS idx_reclog_lowconf ON recommendation_log(created_at DESC)
    WHERE confidence_top < 0.35;

CREATE TABLE IF NOT EXISTS feedback (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recommendation_id UUID REFERENCES recommendation_log(id) ON DELETE CASCADE,
    is_number         TEXT NOT NULL,
    verdict           TEXT NOT NULL CHECK (verdict IN ('accept','reject')),
    comment           TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_verdict ON feedback(verdict, is_number);

-- ------------------------------------------------------------ pipeline health

CREATE TABLE IF NOT EXISTS sync_runs (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mode             TEXT NOT NULL,        -- full | delta | gazette | crs
    source           TEXT NOT NULL,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at      TIMESTAMPTZ,
    pages_fetched    INTEGER DEFAULT 0,
    records_found    INTEGER DEFAULT 0,
    records_changed  INTEGER DEFAULT 0,
    selector_misses  JSONB DEFAULT '{}',
    errors           JSONB DEFAULT '[]',
    healthy          BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_sync_started ON sync_runs(started_at DESC);

-- ----------------------------------------------------------------- views

-- Operational view: corpus coverage, surfaced in the admin screen and used to
-- set honest expectations in the UI's coverage badge.
CREATE OR REPLACE VIEW v_corpus_coverage AS
SELECT
    division,
    COUNT(*)                                            AS total,
    COUNT(*) FILTER (WHERE status = 'current')          AS current_count,
    COUNT(*) FILTER (WHERE scope IS NOT NULL)           AS with_scope,
    COUNT(*) FILTER (WHERE jsonb_array_length(normative_references) > 0) AS with_refs,
    COUNT(*) FILTER (WHERE certification != '{}')       AS with_certification,
    ROUND(AVG(extraction_quality)::numeric, 3)          AS avg_quality,
    MAX(last_seen)                                      AS last_synced
FROM is_standards
GROUP BY division
ORDER BY total DESC;

CREATE OR REPLACE VIEW v_recent_changes AS
SELECT a.is_number, s.title, a.change_type, a.changed_at,
       a.old_values, a.new_values
FROM is_standards_audit a
LEFT JOIN is_standards s ON s.is_number = a.is_number
ORDER BY a.changed_at DESC;
