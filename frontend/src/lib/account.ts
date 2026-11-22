import { createContext, useContext } from 'react';
import type { Account } from '../api/client.ts';

export type AccountStatus = 'loading' | 'signed_out' | 'signed_in';

export interface AccountState {
  status: AccountStatus;
  user: Account | null;
  signIn(email: string, password: string): Promise<void>;
  signUp(name: string, email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  /** Zmiana hasła kończy wszystkie sesje: po niej trzeba zalogować się ponownie. */
  changePassword(current: string, next: string): Promise<void>;
}

const signedOut: AccountState = {
  status: 'signed_out',
  user: null,
  signIn: () => Promise.reject(new Error('Konta są niedostępne.')),
  signUp: () => Promise.reject(new Error('Konta są niedostępne.')),
  signOut: () => Promise.resolve(),
  changePassword: () => Promise.reject(new Error('Konta są niedostępne.')),
};

export const AccountContext = createContext<AccountState>(signedOut);

export function useAccount(): AccountState {
  return useContext(AccountContext);
}

/** „Anna Kowalska” → „Anna” (do przycisku w nagłówku). */
export function firstName(user: Account): string {
  return user.name.trim().split(/\s+/)[0] || user.email;
}
