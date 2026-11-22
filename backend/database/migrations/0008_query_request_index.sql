-- Raport zagrożeń z logów (GET /api/admin/threats) łączy zdarzenia z wpisami dziennika
-- zapytań po request_id.

CREATE INDEX IF NOT EXISTS user_queries_request ON user_queries (request_id);
