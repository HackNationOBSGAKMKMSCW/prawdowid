import { useEffect, useState } from 'react';
import { api } from '../api.ts';

export default function Home() {
  const [status, setStatus] = useState('checking...');

  useEffect(() => {
    api
      .health()
      .then((r) => setStatus(r.status))
      .catch(() => setStatus('unreachable'));
  }, []);

  return (
    <>
      <h1>Prawdowid</h1>
      <p>React + FastAPI starter.</p>
      <p>
        API status: <strong>{status}</strong>
      </p>
    </>
  );
}
