import './index.css'; // ⬅️ MUY IMPORTANTE (al tope)

import React from 'react';
import { createRoot } from 'react-dom/client';
import DashboardAgricola from './DashboardAgricola.jsx';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <DashboardAgricola />
  </React.StrictMode>
);