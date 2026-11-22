-- Zgłoszenia błędów w wynikach (POST /api/check/{id}/report) widoczne w dzienniku zapytań
-- panelu admina: powód, opcjonalny komentarz i czas. Flaga ``zgloszenie:<powód>`` w ``flags``.

ALTER TABLE user_queries ADD COLUMN IF NOT EXISTS report jsonb;
