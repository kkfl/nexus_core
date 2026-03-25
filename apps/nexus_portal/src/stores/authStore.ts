import { create } from 'zustand';
import { jwtDecode } from 'jwt-decode';

interface JwtPayload {
    sub: string;
    role: string;
    mp?: Record<string, string>;
    exp: number;
}

interface User {
    id: number;
    email: string;
    role: string;
    module_permissions: Record<string, string>;
}

function parseUser(token: string): User {
    const payload = jwtDecode<JwtPayload>(token);
    return {
        id: (payload as any).id ?? 0,
        email: payload.sub,
        role: payload.role,
        module_permissions: payload.mp ?? {},
    };
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
        ? parseUser(localStorage.getItem('nexus_access_token')!)
        : null,
    setToken: (token: string) => {
        localStorage.setItem('nexus_access_token', token);
        set({
            accessToken: token,
            user: parseUser(token),
        });
    },
    logout: () => {
        localStorage.removeItem('nexus_access_token');
        set({ accessToken: null, user: null });
    },
}));

/** Check if the current user has at least the given access level for a module. */
export function hasModuleAccess(
    user: User | null,
    module: string,
    minLevel: 'none' | 'read' | 'manage' = 'read'
): boolean {
    if (!user) return false;
    if (user.role === 'admin') return true;
    const levels: Record<string, number> = { none: 0, read: 1, manage: 2 };
    const userLevel = user.module_permissions?.[module] ?? 'none';
    return (levels[userLevel] ?? 0) >= (levels[minLevel] ?? 0);
}

