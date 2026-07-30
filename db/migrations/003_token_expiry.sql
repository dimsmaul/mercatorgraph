-- Token lifecycle: optional expiry + revocation.
ALTER TABLE tokens ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE tokens ADD COLUMN IF NOT EXISTS revoked BOOLEAN NOT NULL DEFAULT false;
