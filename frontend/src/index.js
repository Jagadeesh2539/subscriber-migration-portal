import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { BrowserRouter } from 'react-router-dom';
import { CssBaseline } from '@mui/material';
import './index.css'; // optional, for global styles

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <BrowserRouter>
      <CssBaseline /> {/* ensures consistent styling across browsers */}
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
