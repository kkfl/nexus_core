import { create } from 'zustand';
import { jwtDecode } from 'jwt-decode';

interface User {
    id: number;
    email: string;
    role: string;
}

interface AuthState {
    accessToken: string | null;
    user: User | null;
    setToken: (token: string) => void;
    logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
    accessToken: localStorage.getItem('nexus_access_token') || null,
    user: localStorage.getItem('nexus_access_token')
        ? (jwtDecode(localStorage.getItem('nexus_access_token')!) as User)
        : null,
    setToken: (token: string) => {
        localStorage.setItem('nexus_access_token', token);
        set({
            accessToken: token,
            user: jwtDecode(token) as User,
        });
    },
    logout: () => {
        localStorage.removeItem('nexus_access_token');
        set({ accessToken: null, user: null });
    },
}));
