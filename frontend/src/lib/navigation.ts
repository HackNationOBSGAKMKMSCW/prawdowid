import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useChecker } from './checker.ts';

/** Powrót do pustego formularza na stronie głównej. */
export function useGoHome() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { goStart } = useChecker();
  return useCallback(() => {
    goStart(true);
    if (pathname !== '/') navigate('/');
  }, [goStart, navigate, pathname]);
}
