import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import WhatsAppSimulator from './WhatsAppSimulator.tsx';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <WhatsAppSimulator />
  </StrictMode>,
);
