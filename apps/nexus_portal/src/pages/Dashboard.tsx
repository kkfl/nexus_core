import { Table, Typography, Tag, Space } from 'antd';
import { TiltCard } from '../components/TiltCard';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import {
    DatabaseOutlined, MailOutlined, ApiOutlined, ClockCircleOutlined,
    WarningOutlined, RightOutlined, DashboardOutlined,
    CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, cardStyle, tableStyleOverrides, pageContainer } from '../theme';

const { Title, Text } = Typography;

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
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const { data, isLoading, isError } = useQuery<DashboardSummary>({
        queryKey: ['dashboard-summary'],
        queryFn: async () => (await apiClient.get('/brain/dashboard/summary')).data,
        refetchInterval: 30000,
    });

    const getTransactionStatus = (action: string) => {
        if (!action) return { text: 'Unknown', color: t.muted, bg: `${t.muted}18`, border: `${t.muted}40` };
        const a = action.toLowerCase();
        if (a.endsWith('.requested')) return { text: 'Requested', color: t.accent, bg: `${t.accent}18`, border: `${t.accent}40` };
        if (a.endsWith('.started') || a.endsWith('.processing')) return { text: 'In Progress', color: t.orange, bg: `${t.orange}18`, border: `${t.orange}40` };
        if (a.endsWith('.completed') || a.endsWith('.succeeded') || a.endsWith('.retrieved')) return { text: 'Completed', color: t.green, bg: `${t.green}18`, border: `${t.green}40` };
        if (a.endsWith('.failed') || a.endsWith('.error')) return { text: 'Failed', color: t.red, bg: `${t.red}18`, border: `${t.red}40` };
        if (a.endsWith('.ping')) return { text: 'System', color: t.purple, bg: `${t.purple}18`, border: `${t.purple}40` };
        return { text: 'Action', color: t.muted, bg: `${t.muted}18`, border: `${t.muted}40` };
    };

    const transactionColumns = [
        {
            title: 'TIME', dataIndex: 'timestamp', key: 'timestamp', width: 200,
            render: (date: string) => (
                <Space>
                    <ClockCircleOutlined style={{ color: t.muted }} />
                    <Text style={{ color: t.muted, fontSize: 12 }}>{new Date(date).toLocaleString()}</Text>
                </Space>
            )
        },
        {
            title: 'SOURCE', dataIndex: 'source', key: 'source', width: 180,
            render: (source: string) => (
                <Text style={{ color: t.cyan, fontWeight: 600, fontFamily: 'monospace', fontSize: 12 }}>{source}</Text>
            )
        },
        {
            title: 'ACTION', dataIndex: 'action', key: 'action',
            render: (action: string) => (
                <Tag style={{
                    background: `${t.accent}18`, color: t.accent,
                    border: `1px solid ${t.accent}40`, fontFamily: 'monospace', fontSize: 11
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
                    info: { color: t.accent, bg: `${t.accent}18`, border: `${t.accent}40` },
                    warning: { color: t.orange, bg: `${t.orange}18`, border: `${t.orange}40` },
                    error: { color: t.red, bg: `${t.red}18`, border: `${t.red}40` },
                    critical: { color: t.red, bg: `${t.red}18`, border: `${t.red}40` },
                };
                const s = map[sev] || { color: t.muted, bg: `${t.muted}18`, border: `${t.muted}40` };
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
            label: 'MICRO-AGENTS', icon: <ApiOutlined />, glow: t.accent,
            value: metrics.agents.total, sub: `${metrics.agents.active} Online`,
            subColor: metrics.agents.active > 0 ? t.green : t.muted,
            subIcon: metrics.agents.active > 0 ? <CheckCircleOutlined /> : <CloseCircleOutlined />,
            clickable: true, onClick: () => navigate('/agents'),
        },
        {
            label: 'MANAGED SERVERS', icon: <DatabaseOutlined />, glow: t.cyan,
            value: metrics.servers.total, sub: `${metrics.servers.active} Running`,
            subColor: metrics.servers.active > 0 ? t.green : t.muted,
            subIcon: metrics.servers.active > 0 ? <CheckCircleOutlined /> : <CloseCircleOutlined />,
            clickable: true, onClick: () => navigate('/infrastructure/servers'),
        },
        {
            label: 'MAILBOXES', icon: <MailOutlined />, glow: t.purple,
            value: metrics.mail.total_mailboxes, sub: `${metrics.mail.inbound_unread} Unread`,
            subColor: metrics.mail.inbound_unread > 0 ? t.orange : t.muted,
            subIcon: metrics.mail.inbound_unread > 0 ? <WarningOutlined /> : <CheckCircleOutlined />,
            clickable: false,
        },
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'cmd-table')}</style>

            {/* ═══ Header ═══ */}
            <div style={{ marginBottom: 28 }}>
                <Title level={2} style={{ margin: 0, color: t.text }}>
                    <DashboardOutlined style={{ marginRight: 10, color: t.accent }} />
                    Command Center
                </Title>
                <Text style={{ color: t.muted, marginTop: 4, display: 'block' }}>
                    System overview and micro-agent health
                </Text>
            </div>

            {isError && (
                <div style={{
                    marginBottom: 20, padding: '12px 20px', borderRadius: 10,
                    background: `${t.red}15`, border: `1px solid ${t.red}40`,
                }}>
                    <Text style={{ color: t.red }}>
                        <WarningOutlined style={{ marginRight: 8 }} />
                        Failed to load dashboard summary. Check API connectivity.
                    </Text>
                </div>
            )}

            {/* ═══ Summary Cards ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 28 }}>
                {summaryCards.map((card) => (
                    <TiltCard
                        key={card.label}
                        className={card.clickable ? 'nx-card-hover' : ''}
                        onClick={card.clickable ? card.onClick : undefined}
                        style={{
                            ...cardStyle(t, card.glow),
                            cursor: card.clickable ? 'pointer' : 'default',
                            '--nx-glow': card.glow,
                        } as React.CSSProperties}
                        intensity={10}
                        scale={1.03}
                    >
                        {/* Glow line at top */}
                        <div style={{
                            position: 'absolute', top: 0, left: 0, right: 0, height: 2,
                            background: `linear-gradient(90deg, transparent, ${card.glow}, transparent)`,
                            opacity: 0.6,
                        }} />

                        <Text style={{ color: t.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                            <span style={{ color: card.glow, marginRight: 8 }}>{card.icon}</span>
                            {card.label}
                        </Text>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                            <div>
                                <div style={{ color: t.text, fontSize: 36, fontWeight: 700, lineHeight: 1 }}>
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
                                <Text style={{ color: t.muted, fontSize: 12 }}>
                                    <RightOutlined /> View All
                                </Text>
                            )}
                        </div>
                    </TiltCard>
                ))}
            </div>

            {/* ═══ System Activity Log ═══ */}
            <div style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <div style={{
                    padding: '14px 20px',
                    borderBottom: `1px solid ${t.border}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                    <Text style={{ color: t.muted, fontSize: 11, letterSpacing: 1 }}>
                        <ClockCircleOutlined style={{ marginRight: 8, color: t.accent }} />
                        SYSTEM ACTIVITY LOG
                    </Text>
                    <Text style={{ color: t.muted, fontSize: 11 }}>
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
