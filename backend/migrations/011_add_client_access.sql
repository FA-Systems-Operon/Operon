-- Apply after the users and clients tables exist.
CREATE TABLE IF NOT EXISTS client_access (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, client_id)
);

CREATE INDEX IF NOT EXISTS ix_client_access_client_id ON client_access (client_id);
