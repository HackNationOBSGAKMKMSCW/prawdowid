-- Luki informacyjne liczone po zapytaniach (admin/monitor.py, info_gap_count_by="zapytania"):
-- liczba zapytań bez pokrycia w danych w oknie czasu, obok liczby różnych osób (gap_users).

ALTER TABLE query_topics ADD COLUMN IF NOT EXISTS gap_queries integer NOT NULL DEFAULT 0;
