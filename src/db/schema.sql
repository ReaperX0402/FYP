CREATE SCHEMA IF NOT EXISTS ipds;

-- =========================
-- JOBS 
-- =========================
CREATE TABLE IF NOT EXISTS ipds.jobs (
  job_id      TEXT PRIMARY KEY,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  status      TEXT NOT NULL DEFAULT 'open',
  CONSTRAINT jobs_status_chk CHECK (status IN ('open', 'closed', 'cancelled'))
);

-- =========================
-- OPERATORS 
-- =========================
CREATE TABLE IF NOT EXISTS ipds.operators (
  operator_id  TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  role         TEXT,
  is_active    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================
-- IMPORT_SESSION 
-- =========================
CREATE TABLE IF NOT EXISTS ipds.import_session (
  import_session_id BIGSERIAL PRIMARY KEY,
  operator_id       TEXT NOT NULL REFERENCES ipds.operators(operator_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  job_id            TEXT NOT NULL REFERENCES ipds.jobs(job_id)          ON UPDATE CASCADE ON DELETE RESTRICT,
  started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at          TIMESTAMPTZ,
  status            TEXT NOT NULL DEFAULT 'running',
  uut_serial        TEXT NOT NULL,
  session_purpose   TEXT NOT NULL DEFAULT 'initial',
  CONSTRAINT import_session_status_chk CHECK (status IN ('running', 'completed', 'failed')),
  CONSTRAINT import_session_purpose_chk CHECK (session_purpose IN ('initial', 'retake', 'rework', 'other')),
  CONSTRAINT import_session_time_chk CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_import_session_operator_id ON ipds.import_session(operator_id);
CREATE INDEX IF NOT EXISTS idx_import_session_job_id      ON ipds.import_session(job_id);
CREATE INDEX IF NOT EXISTS idx_import_session_uut_serial  ON ipds.import_session(uut_serial);

-- =========================
-- MEDIA 
-- =========================
CREATE TABLE IF NOT EXISTS ipds.media (
  media_id          BIGSERIAL PRIMARY KEY,
  import_session_id BIGINT NOT NULL REFERENCES ipds.import_session(import_session_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  adapter           TEXT NOT NULL,
  vendor_id         TEXT NOT NULL,
  filename          TEXT,
  size_bytes        BIGINT NOT NULL DEFAULT 0,
  captured_at       TIMESTAMPTZ,
  imported_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  local_path        TEXT NOT NULL,
  CONSTRAINT media_dedupe_uq UNIQUE (adapter, vendor_id)
);

CREATE INDEX IF NOT EXISTS idx_media_import_session_id ON ipds.media(import_session_id);
CREATE INDEX IF NOT EXISTS idx_media_imported_at       ON ipds.media(imported_at);

-- =========================
-- DECISIONS 
-- =========================
CREATE TABLE IF NOT EXISTS ipds.decisions (
  decision_id BIGSERIAL PRIMARY KEY,
  media_id    BIGINT NOT NULL REFERENCES ipds.media(media_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  status      TEXT NOT NULL,
  reason      TEXT,
  decided_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  notes       TEXT,
  CONSTRAINT decisions_one_per_media_uq UNIQUE (media_id),
  CONSTRAINT decisions_status_chk CHECK (status IN ('accepted', 'rejected'))
);

-- =========================
-- EXPORTS 
-- =========================
CREATE TABLE IF NOT EXISTS ipds.exports (
  export_id         BIGSERIAL PRIMARY KEY,
  import_session_id BIGINT NOT NULL REFERENCES ipds.import_session(import_session_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  export_path       TEXT NOT NULL,
  manifest_path     TEXT NOT NULL,
  manifest_hash     TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'created',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT exports_status_chk CHECK (status IN ('created', 'archived', 'ready', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_exports_import_session_id ON ipds.exports(import_session_id);

-- =========================
-- LOCAL_ARCHIVES 
-- =========================
CREATE TABLE IF NOT EXISTS ipds.local_archives (
  archive_id    BIGSERIAL PRIMARY KEY,
  export_id     BIGINT NOT NULL REFERENCES ipds.exports(export_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  archive_path  TEXT NOT NULL,
  verify_status TEXT NOT NULL DEFAULT 'pending',
  last_error    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT local_archives_one_per_export_uq UNIQUE (export_id),
  CONSTRAINT local_archives_verify_status_chk CHECK (verify_status IN ('pending','verified','failed'))
);

-- =========================
-- EXPORT_DELIVERIES
-- =========================
CREATE TABLE IF NOT EXISTS ipds.export_deliveries (
  delivery_id       BIGSERIAL PRIMARY KEY,
  export_id         BIGINT NOT NULL REFERENCES ipds.exports(export_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  delivered_by      TEXT NOT NULL REFERENCES ipds.operators(operator_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  destination_path  TEXT NOT NULL,
  delivered_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  result            TEXT NOT NULL,
  error_message     TEXT,
  CONSTRAINT export_deliveries_result_chk CHECK (result IN ('succeeded','failed'))
);

CREATE INDEX IF NOT EXISTS idx_export_deliveries_export_id    ON ipds.export_deliveries(export_id);
CREATE INDEX IF NOT EXISTS idx_export_deliveries_delivered_by ON ipds.export_deliveries(delivered_by);
CREATE INDEX IF NOT EXISTS idx_export_deliveries_delivered_at ON ipds.export_deliveries(delivered_at);
