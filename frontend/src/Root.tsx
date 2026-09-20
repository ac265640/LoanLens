import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import Home from './pages/Home';
import App from './App'; // your existing dashboard, untouched
import './pages/Home.css';

type Theme = 'light' | 'dark';
const STORAGE_KEY = 'loanlens-theme';

// Saved choice wins; otherwise follow the OS setting.
function getInitialTheme(): Theme {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved === 'light' || saved === 'dark') return saved;
    } catch {
        /* storage blocked: fall through */
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

const Moon = () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
);

const Sun = () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
);

const LensIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <line x1="14.31" y1="8" x2="20.05" y2="17.94" />
        <line x1="9.69" y1="8" x2="21.17" y2="8" />
        <line x1="7.38" y1="12" x2="13.12" y2="2.06" />
        <line x1="9.69" y1="16" x2="3.95" y2="6.06" />
        <line x1="14.31" y1="16" x2="2.83" y2="16" />
        <line x1="16.62" y1="12" x2="10.88" y2="21.94" />
    </svg>
);

export default function Root() {
    const [theme, setTheme] = useState<Theme>(getInitialTheme);

    // Also expose the theme on <html> so other parts of the app (the dashboard) can key off it.
    useEffect(() => {
        document.documentElement.dataset.theme = theme;
    }, [theme]);

    const toggle = () => {
        const next: Theme = theme === 'dark' ? 'light' : 'dark';
        setTheme(next);
        try {
            localStorage.setItem(STORAGE_KEY, next);
        } catch {
            /* ignore */
        }
    };

    return (
        <BrowserRouter>
            <div className="ll-shell" data-theme={theme}>
                <header className="ll-nav-wrapper">
                    <div className="ll-nav-pill">
                        <NavLink to="/" className="ll-nav-logo" aria-label="LoanLens Home" title="LoanLens Home" end>
                            <LensIcon />
                        </NavLink>

                        <nav className="ll-nav-links" aria-label="Main">
                            <NavLink to="/" end className={({ isActive }) => `ll-nav-link ${isActive ? 'active' : ''}`}>
                                Home
                            </NavLink>
                            <NavLink to="/dashboard" className={({ isActive }) => `ll-nav-link ${isActive ? 'active' : ''}`}>
                                Live Platform
                            </NavLink>
                        </nav>

                        <button
                            type="button"
                            className="ll-nav-cta"
                            onClick={toggle}
                            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
                            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
                        >
                            {theme === 'dark' ? <Sun /> : <Moon />}
                            <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>
                        </button>
                    </div>
                </header>

                <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/dashboard" element={<App />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
            </div>
        </BrowserRouter>
    );
}