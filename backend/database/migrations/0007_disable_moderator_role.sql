-- Rola moderatora jest na razie wyłączona: panel admina ma tylko administratora i analityka.
-- Istniejące konta moderatorów stają się kontami analityków, żeby nie straciły dostępu do panelu.
-- Wartość 'moderator' zostaje w typie user_role (usunięcie wartości z ENUM wymaga przebudowy typu),
-- więc rolę można później przywrócić w kodzie (backend/accounts/permissions.py).

UPDATE users SET role = 'analyst', updated_at = now() WHERE role = 'moderator';
