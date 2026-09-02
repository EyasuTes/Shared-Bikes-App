CREATE TABLE IF NOT EXISTS messages (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  content VARCHAR(200) NOT NULL CHECK (char_length(trim(content)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO messages (content)
VALUES ('This example message was loaded from PostgreSQL.');
