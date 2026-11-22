-- Konta użytkowników i tokeny dostępu (format jak w AdonisJS: oat_<id>.<sekret>).
-- Rola: zwykły użytkownik serwisu albo jedna z ról panelu (admin ma osobny typ konta).

DO $$
BEGIN
    CREATE TYPE user_role AS ENUM ('user', 'moderator', 'analyst', 'admin');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS users (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          varchar(100) NOT NULL,
    email         varchar(255) NOT NULL,
    password_hash varchar(255) NOT NULL,
    role          user_role NOT NULL DEFAULT 'user',
    is_active     boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_email_format CHECK (position('@' in email) > 1)
);

-- Unikalność emaila bez względu na wielkość liter (Jan@x.pl == jan@x.pl).
CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (lower(email));

CREATE TABLE IF NOT EXISTS auth_access_tokens (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tokenable_id integer NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    type         varchar(255) NOT NULL,
    name         varchar(255),
    hash         varchar(255) NOT NULL,
    abilities    text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    expires_at   timestamptz
);

CREATE INDEX IF NOT EXISTS auth_access_tokens_tokenable ON auth_access_tokens (tokenable_id);
CREATE UNIQUE INDEX IF NOT EXISTS auth_access_tokens_hash ON auth_access_tokens (hash);
