import { Table, Typography, Tag, Space } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import {
    DatabaseOutlined, MailOutlined, ApiOutlined, ClockCircleOutlined,
    WarningOutlined, RightOutlined, DashboardOutlined,
    CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;

// ── Midnight palette (consistent with Server Admin / DNS pages) ──
const MN = {
    bg: '#0f1623', card: '#131b2e', border: '#1e293b',
    text: '#e2e8f0', muted: '#94a3b8', accent: '#3b82f6',
    green: '#4ade80', red: '#f87171', orange: '#fb923c', purple: '#a78bfa',
    cyan: '#22d3ee',
};

const cardStyle = (glow = MN.accent): React.CSSProperties => ({
    background: MN.card, borderRadius: 12,
    border: `1px solid ${MN.border}`,
    boxShadow: `0 0 20px ${glow}10`,
    padding: 20, height: '100%',
    transition: 'all 0.2s ease',
});

interface DashboardSummary {
    metrics: {
        agents: { total: number; active: number };
        servers: { total: number; active: number };
        mail: { total_mailboxes: number; inbound_unread: number };
    };
    recent_activity: Array<{ name: string; status: string; last_seen_at: string | null }>;
    recent_transactions: Array<{ timestamp: string; source: string; action: string; severity: string }>;
}

export default function Dashboard() {
    const navigate = useNavigate();
    const { data, isLoading, isError } = useQuery<DashboardSummary>({
        queryKey: ['dashboard-summary'],
        queryFn: async () => (await apiClient.get('/brain/dashboard/summary')).data,
        refetchInterval: 30000,
    });

    const getTransactionStatus = (action: string) => {
        if (!action) return { text: 'Unknown', color: MN.muted, bg: 'rgba(148,163,184,0.15)', border: 'rgba(148,163,184,0.3)' };
        const a = action.toLowerCase();
        if (a.endsWith('.requested')) return { text: 'Requested', color: MN.accent, bg: 'rgba(59,130,246,0.15)', border: 'rgba(59,130,246,0.3)' };
        if (a.endsWith('.started') || a.endsWith('.processing')) return { text: 'In Progress', color: MN.orange, bg: 'rgba(251,146,60,0.15)', border: 'rgba(251,146,60,0.3)' };
        if (a.endsWith('.completed') || a.endsWith('.succeeded') || a.endsWith('.retrieved')) return { text: 'Completed', color: MN.green, bg: 'rgba(34,197,94,0.15)', border: 'rgba(34,197,94,0.3)' };
        if (a.endsWith('.failed') || a.endsWith('.error')) return { text: 'Failed', color: MN.red, bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.3)' };
        if (a.endsWith('.ping')) return { text: 'System', color: MN.purple, bg: 'rgba(167,139,250,0.15)', border: 'rgba(167,139,250,0.3)' };
        return { text: 'Action', color: MN.muted, bg: 'rgba(148,163,184,0.15)', border: 'rgba(148,163,184,0.3)' };
    };

    const transactionColumns = [
        {
            title: 'TIME', dataIndex: 'timestamp', key: 'timestamp', width: 200,
            render: (date: string) => (
                <Space>
                    <ClockCircleOutlined style={{ color: MN.muted }} />
                    <Text style={{ color: MN.muted, fontSize: 12 }}>{new Date(date).toLocaleString()}</Text>
                </Space>
            )
        },
        {
            title: 'SOURCE', dataIndex: 'source', key: 'source', width: 180,
            render: (source: string) => (
                <Text style={{ color: MN.cyan, fontWeight: 600, fontFamily: 'monospace', fontSize: 12 }}>{source}</Text>
            )
        },
        {
            title: 'ACTION', dataIndex: 'action', key: 'action',
            render: (action: string) => (
                <Tag style={{
                    background: 'rgba(59,130,246,0.15)', color: MN.accent,
                    border: '1px solid rgba(59,130,246,0.3)', fontFamily: 'monospace', fontSize: 11
                }}>{action}</Tag>
            )
        },
        {
            title: 'STATUS', key: 'status',
            render: (_: any, record: any) => {
                const s = getTransactionStatus(record.action);
                return (
                    <Tag style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>
                        <span style={{
                            width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
                            background: s.color, boxShadow: `0 0 6px ${s.color}`, marginRight: 6,
                        }} />
                        {s.text}
                    </Tag>
                );
            }
        },
        {
            title: 'SEVERITY', dataIndex: 'severity', key: 'severity', width: 100,
            render: (sev: string) => {
                const map: Record<string, { color: string; bg: string; border: string }> = {
                    info: { color: MN.accent, bg: 'rgba(59,130,246,0.15)', border: 'rgba(59,130,246,0.3)' },
                    warning: { color: MN.orange, bg: 'rgba(251,146,60,0.15)', border: 'rgba(251,146,60,0.3)' },
                    error: { color: MN.red, bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.3)' },
                    critical: { color: MN.red, bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.3)' },
                };
                const s = map[sev] || { color: MN.muted, bg: 'rgba(148,163,184,0.15)', border: 'rgba(148,163,184,0.3)' };
                return <Tag style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}`, fontSize: 10 }}>{sev?.toUpperCase()}</Tag>;
            }
        },
    ];

    const metrics = data?.metrics || {
        agents: { total: 0, active: 0 },
        servers: { total: 0, active: 0 },
        mail: { total_mailboxes: 0, inbound_unread: 0 }
    };

    const summaryCards = [
        {
            label: 'MICRO-AGENTS', icon: <ApiOutlined />, glow: MN.accent,
            value: metrics.agents.total, sub: `${metrics.agents.active} Online`,
            subColor: metrics.agents.active > 0 ? MN.green : MN.muted,
            subIcon: metrics.agents.active > 0 ? <CheckCircleOutlined /> : <CloseCircleOutlined />,
            clickable: true, onClick: () => navigate('/agents'),
        },
        {
            label: 'MANAGED SERVERS', icon: <DatabaseOutlined />, glow: MN.cyan,
            value: metrics.servers.total, sub: `${metrics.servers.active} Running`,
            subColor: metrics.servers.active > 0 ? MN.green : MN.muted,
            subIcon: metrics.servers.active > 0 ? <CheckCircleOutlined /> : <CloseCircleOutlined />,
            clickable: true, onClick: () => navigate('/infrastructure/servers'),
        },
        {
            label: 'MAILBOXES', icon: <MailOutlined />, glow: MN.purple,
            value: metrics.mail.total_mailboxes, sub: `${metrics.mail.inbound_unread} Unread`,
            subColor: metrics.mail.inbound_unread > 0 ? MN.orange : MN.muted,
            subIcon: metrics.mail.inbound_unread > 0 ? <WarningOutlined /> : <CheckCircleOutlined />,
            clickable: false,
        },
    ];

    return (
        <div style={{ background: MN.bg, margin: -32, padding: 32, minHeight: 'calc(100vh - 64px)' }}>
            <style>{`
                .cmd-table .ant-table { background: transparent !important; }
                .cmd-table .ant-table-thead > tr > th { background: rgba(30,41,59,0.6) !important; color: ${MN.muted} !important; border-bottom: 1px solid ${MN.border} !important; font-size: 11px !important; letter-spacing: 0.5px; }
                .cmd-table .ant-table-tbody > tr > td { border-bottom: 1px solid ${MN.border} !important; background: transparent !important; }
                .cmd-table .ant-table-tbody > tr:hover > td { background: rgba(59,130,246,0.05) !important; }
                .cmd-table .ant-table-cell { color: ${MN.text} !important; }
                .cmd-table .ant-empty-description { color: ${MN.muted} !important; }
                .cmd-table .ant-table-placeholder { background: transparent !important; }
                .cmd-table .ant-table-placeholder:hover > td { background: transparent !important; }
            `}</style>

            {/* ═══ Header ═══ */}
            <div style={{ marginBottom: 28 }}>
                <Title level={2} style={{ margin: 0, color: MN.text }}>
                    <DashboardOutlined style={{ marginRight: 10, color: MN.accent }} />
                    Command Center
                </Title>
                <Text style={{ color: MN.muted, marginTop: 4, display: 'block' }}>
                    System overview and micro-agent health
                </Text>
            </div>

            {isError && (
                <div style={{
                    marginBottom: 20, padding: '12px 20px', borderRadius: 10,
                    background: 'rgba(239,68,68,0.1)', border: `1px solid rgba(239,68,68,0.3)`,
                }}>
                    <Text style={{ color: MN.red }}>
                        <WarningOutlined style={{ marginRight: 8 }} />
                        Failed to load dashboard summary. Check API connectivity.
                    </Text>
                </div>
            )}

            {/* ═══ Summary Cards ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 28 }}>
                {summaryCards.map((card) => (
                    <div
                        key={card.label}
                        onClick={card.clickable ? card.onClick : undefined}
                        style={{
                            ...cardStyle(card.glow),
                            cursor: card.clickable ? 'pointer' : 'default',
                            position: 'relative',
                            overflow: 'hidden',
                        }}
                        onMouseEnter={(e) => {
                            if (card.clickable) {
                                (e.currentTarget as HTMLElement).style.borderColor = card.glow;
                                (e.currentTarget as HTMLElement).style.boxShadow = `0 0 30px ${card.glow}25`;
                            }
                        }}
                        onMouseLeave={(e) => {
                            if (card.clickable) {
                                (e.currentTarget as HTMLElement).style.borderColor = MN.border;
                                (e.currentTarget as HTMLElement).style.boxShadow = `0 0 20px ${card.glow}10`;
                            }
                        }}
                    >
                        {/* Glow line at top */}
                        <div style={{
                            position: 'absolute', top: 0, left: 0, right: 0, height: 2,
                            background: `linear-gradient(90deg, transparent, ${card.glow}, transparent)`,
                            opacity: 0.6,
                        }} />

                        <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                            <span style={{ color: card.glow, marginRight: 8 }}>{card.icon}</span>
                            {card.label}
                        </Text>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                            <div>
                                <div style={{ color: '#fff', fontSize: 36, fontWeight: 700, lineHeight: 1 }}>
                                    {isLoading ? '—' : card.value}
                                </div>
                                <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <span style={{
                                        width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
                                        background: card.subColor,
                                        boxShadow: `0 0 6px ${card.subColor}`,
                                    }} />
                                    <Text style={{ color: card.subColor, fontSize: 13 }}>{card.sub}</Text>
                                </div>
                            </div>
                            {card.clickable && (
                                <Text style={{ color: MN.muted, fontSize: 12 }}>
                                    <RightOutlined /> View All
                                </Text>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            {/* ═══ System Activity Log ═══ */}
            <div style={{ ...cardStyle(), padding: 0, overflow: 'hidden' }}>
                <div style={{
                    padding: '14px 20px',
                    borderBottom: `1px solid ${MN.border}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                    <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1 }}>
                        <ClockCircleOutlined style={{ marginRight: 8, color: MN.accent }} />
                        SYSTEM ACTIVITY LOG
                    </Text>
                    <Text style={{ color: MN.muted, fontSize: 11 }}>
                        {data?.recent_transactions?.length || 0} recent events
                    </Text>
                </div>
                <div className="cmd-table">
                    <Table
                        dataSource={data?.recent_transactions || []}
                        columns={transactionColumns}
                        rowKey={(record) => `${record.timestamp}-${record.action}-${record.source}`}
                        loading={isLoading}
                        pagination={false}
                        size="small"
                    />
                </div>
            </div>
        </div>
    );
}
