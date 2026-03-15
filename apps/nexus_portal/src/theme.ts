import { theme } from 'antd';
import type { ThemeConfig } from 'antd';

type ThemeMode = 'dark' | 'light';

/* ═══════════════════════════════════════════════════
   Design Tokens — the single source of truth
   ═══════════════════════════════════════════════════ */

export interface NexusTokens {
    bg: string;
    card: string;
    cardBg: string;
    border: string;
    text: string;
    textSecondary: string;
    muted: string;
    accent: string;
    green: string;
    red: string;
    orange: string;
    purple: string;
    cyan: string;
    headerBg: string;
    siderBg: string;
    tableHeaderBg: string;
    hoverBg: string;
    inputBg: string;
    tagBg: (color: string) => string;
    tagBorder: (color: string) => string;
    glow: (color: string, intensity?: number) => string;
}

const DARK: NexusTokens = {
    bg: '#0a0e1a',
    card: '#111827',
    cardBg: '#111827',
    border: '#1e293b',
    text: '#e2e8f0',
    textSecondary: '#cbd5e1',
    muted: '#94a3b8',
    accent: '#3b82f6',
    green: '#4ade80',
    red: '#f87171',
    orange: '#fb923c',
    purple: '#a78bfa',
    cyan: '#22d3ee',
    headerBg: '#0f1520',
    siderBg: '#070b14',
    tableHeaderBg: 'rgba(30,41,59,0.6)',
    hoverBg: 'rgba(59,130,246,0.06)',
    inputBg: '#1a2236',
    tagBg: (c: string) => `${c}18`,
    tagBorder: (c: string) => `${c}40`,
    glow: (c: string, i = 10) => `0 0 20px ${c}${i.toString(16).padStart(2, '0')}`,
};

const LIGHT: NexusTokens = {
    bg: '#f8fafc',
    card: '#ffffff',
    cardBg: '#ffffff',
    border: '#e2e8f0',
    text: '#0f172a',
    textSecondary: '#334155',
    muted: '#64748b',
    accent: '#2563eb',
    green: '#16a34a',
    red: '#dc2626',
    orange: '#ea580c',
    purple: '#7c3aed',
    cyan: '#0891b2',
    headerBg: '#ffffff',
    siderBg: '#070b14',          // Keep sidebar dark even in light mode (Apple style)
    tableHeaderBg: '#f1f5f9',
    hoverBg: 'rgba(37,99,235,0.04)',
    inputBg: '#f8fafc',
    tagBg: (c: string) => `${c}12`,
    tagBorder: (c: string) => `${c}30`,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    glow: (_c: string, _i?: number) => '0 1px 3px rgba(0,0,0,0.08)',
};

export function getTokens(mode: ThemeMode): NexusTokens {
    return mode === 'dark' ? DARK : LIGHT;
}

/* ═══════════════════════════════════════════════════
   Ant Design Theme Config
   ═══════════════════════════════════════════════════ */

export function getAntTheme(mode: ThemeMode): ThemeConfig {
    const t = getTokens(mode);
    const isDark = mode === 'dark';

    return {
        algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
            colorPrimary: t.accent,
            borderRadius: 10,
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
            colorBgContainer: t.cardBg,
            colorBgElevated: t.cardBg,
            colorBgLayout: t.bg,
            colorBorder: t.border,
            colorBorderSecondary: t.border,
            colorText: t.text,
            colorTextSecondary: t.muted,
            colorTextTertiary: t.muted,
            ...(isDark ? {
                colorBgBase: t.bg,
            } : {}),
        },
        components: {
            Layout: {
                headerBg: t.headerBg,
                bodyBg: t.bg,
                siderBg: t.siderBg,
                footerBg: 'transparent',
            },
            Menu: {
                darkItemBg: t.siderBg,
                darkSubMenuItemBg: 'rgba(255,255,255,0.02)',
            },
            Table: {
                headerBg: t.tableHeaderBg,
                headerColor: t.muted,
                rowHoverBg: t.hoverBg,
                borderColor: t.border,
                headerBorderRadius: 0,
            },
            Card: {
                colorBgContainer: t.cardBg,
                colorBorderSecondary: t.border,
            },
            Input: {
                colorBgContainer: isDark ? t.inputBg : '#fff',
                activeBg: isDark ? t.inputBg : '#fff',
                hoverBg: isDark ? t.inputBg : '#fff',
                addonBg: isDark ? t.inputBg : '#f5f5f5',
                activeBorderColor: t.accent,
                hoverBorderColor: isDark ? t.accent : t.border,
                colorTextPlaceholder: t.muted,
            },
            InputNumber: {
                colorBgContainer: isDark ? t.inputBg : '#fff',
                activeBg: isDark ? t.inputBg : '#fff',
                hoverBg: isDark ? t.inputBg : '#fff',
                activeBorderColor: t.accent,
            },
            Select: {
                colorBgContainer: isDark ? t.inputBg : '#fff',
                colorBgElevated: isDark ? t.cardBg : '#fff',
                optionActiveBg: isDark ? 'rgba(59,130,246,0.15)' : 'rgba(37,99,235,0.08)',
                optionSelectedBg: isDark ? 'rgba(59,130,246,0.2)' : 'rgba(37,99,235,0.12)',
            },
            Modal: {
                contentBg: t.cardBg,
                headerBg: t.cardBg,
            },
            Drawer: {
                colorBgElevated: t.cardBg,
            },
            Tag: {
                defaultBg: isDark ? 'rgba(59,130,246,0.15)' : 'rgba(37,99,235,0.08)',
                defaultColor: t.accent,
            },
            Button: {
                borderRadius: 8,
            },
            Progress: {
                remainingColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)',
            },
        },
    };
}

/* ═══════════════════════════════════════════════════
   Reusable Style Helpers
   ═══════════════════════════════════════════════════ */

export function cardStyle(t: NexusTokens, glowColor?: string): React.CSSProperties {
    return {
        background: t.cardBg,
        borderRadius: 12,
        border: `1px solid ${t.border}`,
        boxShadow: glowColor ? t.glow(glowColor) : t.glow(t.accent),
        padding: 20,
        height: '100%',
        transition: 'all 0.25s ease',
    };
}

export function pageContainer(t: NexusTokens): React.CSSProperties {
    return {
        background: t.bg,
        minHeight: 'calc(100vh - 64px)',
        padding: 28,
    };
}

/** Standard dark-mode-compatible table CSS overrides (inject via <style>) */
export function tableStyleOverrides(t: NexusTokens, className: string): string {
    return `
        .${className} .ant-table { background: transparent !important; }
        .${className} .ant-table-thead > tr > th {
            background: ${t.tableHeaderBg} !important;
            color: ${t.muted} !important;
            border-bottom: 1px solid ${t.border} !important;
            font-size: 11px !important;
            font-weight: 600 !important;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }
        .${className} .ant-table-tbody > tr > td {
            border-bottom: 1px solid ${t.border} !important;
            background: transparent !important;
        }
        .${className} .ant-table-tbody > tr:hover > td {
            background: ${t.hoverBg} !important;
        }
        .${className} .ant-table-cell { color: ${t.text} !important; }
        .${className} .ant-empty-description { color: ${t.muted} !important; }
        .${className} .ant-table-placeholder { background: transparent !important; }
        .${className} .ant-table-placeholder:hover > td { background: transparent !important; }
        .${className} .ant-pagination .ant-pagination-item a { color: ${t.muted}; }
        .${className} .ant-pagination .ant-pagination-item-active a { color: ${t.accent}; }
    `.trim();
}
