import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import './styles/landing.css';
import './styles/dashboard.css';

// Automatically normalize 127.0.0.1 to localhost in local dev
// to guarantee Firebase Auth compatibility without "auth/unauthorized-domain" errors.
if (
  typeof window !== 'undefined' &&
  window.location.hostname === '127.0.0.1'
) {
  const target = window.location.href.replace('//127.0.0.1', '//localhost');
  window.location.replace(target);
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);

