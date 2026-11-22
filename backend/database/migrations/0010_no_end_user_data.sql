-- Bez danych o użytkownikach aplikacji (strona, WhatsApp): nie przechowujemy numerów telefonów,
-- adresów IP ani wyliczonych z nich pseudonimów i końcówek. Ta migracja usuwa to, co zapisano
-- wcześniej. Konta panelu admina (users, auth_access_tokens, activity_logs) zostają bez zmian,
-- poza wpisami o blokadach użytkowników aplikacji.

-- Dziennik zapytań: jeden wspólny, nieidentyfikujący znacznik zamiast pseudonimów.
UPDATE user_queries SET user_key = 'anonim' WHERE user_key <> 'anonim';
UPDATE user_queries SET user_label = NULL WHERE user_label IS NOT NULL;
UPDATE query_claims SET user_key = 'anonim' WHERE user_key <> 'anonim';

-- Alerty przypisane do osób: „niebezpieczny użytkownik” znika, prompt injection jest zbiorczy.
DELETE FROM monitor_alerts WHERE type = 'niebezpieczny_uzytkownik';
UPDATE monitor_alerts SET subject = 'wszystkie' WHERE type = 'prompt_injection';

-- Alerty-zdarzenia (SQL injection, EUvsDisinfo): lista źródeł (pseudonimy) i źródło
-- (końcówka adresu IP) w każdym wystąpieniu.
UPDATE monitor_alerts SET details = details - 'zrodla' WHERE details ? 'zrodla';
UPDATE monitor_alerts
SET details = jsonb_set(
    details,
    '{wystapienia}',
    (SELECT coalesce(jsonb_agg(w - 'zrodlo'), '[]'::jsonb)
     FROM jsonb_array_elements(details -> 'wystapienia') AS w)
)
WHERE jsonb_typeof(details -> 'wystapienia') = 'array';

-- Dziennik działań panelu: blokady użytkowników aplikacji (subject_id = pseudonim).
DELETE FROM activity_logs WHERE action IN ('enduser.blocked', 'enduser.unblocked');

-- Rejestr użytkowników aplikacji (pseudonim, końcówka numeru, liczniki, blokady).
DROP TABLE IF EXISTS end_users;
