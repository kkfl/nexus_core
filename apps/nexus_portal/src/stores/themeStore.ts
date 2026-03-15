import { create } from 'zustand';

type ThemeMode = 'dark' | 'light';

interface ThemeState {
    mode: ThemeMode;
    toggleMode: () => void;
    setMode: (mode: ThemeMode) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
    mode: (localStorage.getItem('nexus_theme') as ThemeMode) || 'dark',
    toggleMode: () =>
        set((state) => {
            const next = state.mode === 'dark' ? 'light' : 'dark';
            localStorage.setItem('nexus_theme', next);
            document.documentElement.setAttribute('data-theme', next);
            return { mode: next };
        }),
    setMode: (mode: ThemeMode) => {
        localStorage.setItem('nexus_theme', mode);
        document.documentElement.setAttribute('data-theme', mode);
        return { mode };
    },
}));
