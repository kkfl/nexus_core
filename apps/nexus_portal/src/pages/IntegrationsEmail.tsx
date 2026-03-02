import { Table, Button, Modal, Form, Input, Typography, Space, Tag, Card, message, Tooltip, Row, Col, Progress, Drawer, Empty } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { emailClient } from '../api/emailClient';
import { apiClient } from '../api/client';
import { useState, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    MailOutlined,
    PlusOutlined,
    LockOutlined,
    StopOutlined,
    LinkOutlined,
    CheckCircleOutlined,
    ReloadOutlined,
    InboxOutlined,
    WarningOutlined,
    CloudServerOutlined,
    SyncOutlined,
    SendOutlined,
    GlobalOutlined,
    ArrowRightOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;

interface Mailbox {
    email: string;
    domain: string;
    active: number;
    quota: number;
    created: string;
}

interface MailboxWithStats extends Mailbox {
    used_mb?: number;
    used_pct?: number;
    free_pct?: number;
    unread_count?: number;
    total_count?: number;
    last_received_at?: string;
    readable?: boolean;
    sent_total?: number;
    delivered?: number;
    bounced?: number;
    delivery_rate?: number;
}

interface HealthStatus {
    smtp: string;
    imap: string;
    ssh_bridge: string;
    smtp_detail: string | null;
    imap_detail: string | null;
    ssh_detail: string | null;
}

interface ServerStats {
    queue_total: number;
    deferred: number;
    active: number;
    hold: number;
    corrupt: number;
}

interface BulkStatsResponse {
    stats: Array<{
        email: string;
        domain?: string;
        quota_mb?: number;
        used_mb?: number;
        used_pct?: number;
        free_mb?: number;
        free_pct?: number;
        unread_count?: number;
        total_count?: number;
        last_received_at?: string;
        collected_at?: string;
        readable?: boolean;
    }>;
    collected_at: string | null;
    stale: boolean;
    refreshing: boolean;
    count: number;
}

interface SentStatsResponse {
    stats: Array<{
        sender: string;
        sent_total?: number;
        delivered?: number;
        bounced?: number;
        deferred?: number;
        delivery_rate?: number;
        last_sent_at?: string;
        period?: string;
        collected_at?: string;
    }>;
    collected_at: string | null;
    stale: boolean;
    refreshing: boolean;
    count: number;
    totals: {
        sent: number;
        delivered: number;
        bounced: number;
        deferred: number;
        delivery_rate: number;
    };
}

export default function IntegrationsEmail() {
    const queryClient = useQueryClient();
    const navigate = useNavigate();
    const [createOpen, setCreateOpen] = useState(false);
    const [passwordOpen, setPasswordOpen] = useState(false);
    const [aliasOpen, setAliasOpen] = useState(false);
    const [selectedEmail, setSelectedEmail] = useState('');
    const [createForm] = Form.useForm();
    const [passwordForm] = Form.useForm();
    const [aliasForm] = Form.useForm();

    // Domain drawers
    const [domainListOpen, setDomainListOpen] = useState(false);
    const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
    const [addDomainOpen, setAddDomainOpen] = useState(false);
    const [addDomainForm] = Form.useForm();

    // Health
    const { data: health, isLoading: healthLoading, refetch: refetchHealth } = useQuery<HealthStatus>({
        queryKey: ['email_health'],
        queryFn: async () => (await emailClient.get('/email/health')).data,
        refetchInterval: 30000,
    });

    // Server stats
    const { data: serverStats } = useQuery<ServerStats>({
        queryKey: ['email_server_stats'],
        queryFn: async () => (await emailClient.get('/email/admin/server/stats')).data,
        refetchInterval: 60000,
    });

    // Mailbox list (fast — no stats)
    const { data: mailboxes, isLoading, isError, error } = useQuery<Mailbox[]>({
        queryKey: ['email_mailboxes'],
        queryFn: async () => (await emailClient.get('/email/admin/mailbox/list')).data,
        refetchInterval: 60000,
    });

    // Bulk stats (separate query, from DB cache)
    const { data: bulkStats, refetch: refetchStats } = useQuery<BulkStatsResponse>({
        queryKey: ['email_bulk_stats'],
        queryFn: async () => (await emailClient.get('/email/admin/mailbox/stats/bulk')).data,
        refetchInterval: 30000,
    });

    // Force refresh mutation
    const refreshMutation = useMutation({
        mutationFn: async () => (await emailClient.post('/email/admin/mailbox/stats/refresh')).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Stats refreshed: ${data.count} mailboxes`);
                queryClient.invalidateQueries({ queryKey: ['email_bulk_stats'] });
            }
        },
        onError: () => message.error('Stats refresh failed', 8),
    });

    // Sent stats (separate query)
    const { data: sentStats } = useQuery<SentStatsResponse>({
        queryKey: ['email_sent_stats'],
        queryFn: async () => (await emailClient.get('/email/admin/mailbox/stats/sent/bulk')).data,
        refetchInterval: 60000,
    });

    // Sent stats refresh mutation
    const sentRefreshMutation = useMutation({
        mutationFn: async () => (await emailClient.post('/email/admin/mailbox/stats/sent/refresh')).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Sent stats refreshed: ${data.count} senders`);
                queryClient.invalidateQueries({ queryKey: ['email_sent_stats'] });
            }
        },
        onError: () => message.error('Sent stats refresh failed', 8),
    });

    // Merge mailboxes + stats
    const statsMap = useMemo(() => {
        const map: Record<string, BulkStatsResponse['stats'][0]> = {};
        if (bulkStats?.stats) {
            for (const s of bulkStats.stats) {
                map[s.email] = s;
            }
        }
        return map;
    }, [bulkStats]);

    const sentMap = useMemo(() => {
        const map: Record<string, SentStatsResponse['stats'][0]> = {};
        if (sentStats?.stats) {
            for (const s of sentStats.stats) {
                map[s.sender] = s;
            }
        }
        return map;
    }, [sentStats]);

    const mergedMailboxes: MailboxWithStats[] = useMemo(() => {
        if (!mailboxes) return [];
        return mailboxes.map(m => {
            const s = statsMap[m.email];
            const sent = sentMap[m.email];
            return {
                ...m,
                used_mb: s?.used_mb,
                used_pct: s?.used_pct,
                free_pct: s?.free_pct,
                unread_count: s?.unread_count,
                total_count: s?.total_count,
                last_received_at: s?.last_received_at,
                readable: s?.readable ?? true,
                sent_total: sent?.sent_total,
                delivered: sent?.delivered,
                bounced: sent?.bounced,
                delivery_rate: sent?.delivery_rate,
            };
        });
    }, [mailboxes, statsMap, sentMap]);

    // Mutations
    const createMutation = useMutation({
        mutationFn: async (values: { email: string; password: string }) =>
            (await apiClient.post('/brain/credentials/email/mailbox', { email: values.email, password: values.password, action: 'create' })).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Mailbox ${data.email} created`);
                queryClient.invalidateQueries({ queryKey: ['email_mailboxes'] });
                setCreateOpen(false);
                createForm.resetFields();
            } else {
                message.error(data.error || 'Creation failed', 8);
            }
        },
        onError: () => message.error('Request failed', 8),
    });

    const passwordMutation = useMutation({
        mutationFn: async (values: { email: string; password: string }) =>
            (await apiClient.post('/brain/credentials/email/mailbox', { email: values.email, password: values.password, action: 'reset_password' })).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Password updated for ${data.email}`);
                setPasswordOpen(false);
                passwordForm.resetFields();
            } else {
                message.error(data.error || 'Password update failed', 8);
            }
        },
        onError: () => message.error('Request failed', 8),
    });

    const disableMutation = useMutation({
        mutationFn: async (em: string) =>
            (await emailClient.post('/email/admin/mailbox/disable', { email: em })).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Mailbox ${data.email} ${data.action}`);
                queryClient.invalidateQueries({ queryKey: ['email_mailboxes'] });
            } else {
                message.error(data.error || 'Disable failed', 8);
            }
        },
        onError: () => message.error('Request failed', 8),
    });

    const aliasMutation = useMutation({
        mutationFn: async (values: { alias: string; destination: string }) =>
            (await emailClient.post('/email/admin/alias/add', values)).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Alias ${data.alias} → ${data.destination} ${data.action}`);
                setAliasOpen(false);
                aliasForm.resetFields();
            } else {
                message.error(data.error || 'Alias creation failed', 8);
            }
        },
        onError: () => message.error('Request failed', 8),
    });

    // Stats
    const activeCount = mergedMailboxes.filter(m => m.active === 1).length;
    const disabledCount = mergedMailboxes.filter(m => m.active === 0).length;
    const totalUnread = mergedMailboxes.reduce((sum, m) => sum + (m.unread_count || 0), 0);
    const domains = [...new Set(mergedMailboxes.map(m => m.domain))];

    // Stale indicator
    const statsAge = bulkStats?.collected_at
        ? Math.round((Date.now() - new Date(bulkStats.collected_at).getTime()) / 1000)
        : null;
    const statsAgeLabel = statsAge !== null
        ? statsAge < 60 ? `${statsAge}s ago` : `${Math.round(statsAge / 60)}m ago`
        : 'never';



    const columns = [
        {
            title: 'Email',
            dataIndex: 'email',
            key: 'email',
            sorter: (a: MailboxWithStats, b: MailboxWithStats) => a.email.localeCompare(b.email),
            render: (em: string, record: MailboxWithStats) => (
                <Space>
                    <Text strong style={{ color: '#e2e8f0' }}><MailOutlined style={{ marginRight: 6, color: '#64748b' }} />{em}</Text>
                    {(record.unread_count ?? 0) > 0 && (
                        <Tag color="blue" style={{ borderRadius: 10, fontSize: 11 }}>{record.unread_count}</Tag>
                    )}
                </Space>
            ),
        },
        {
            title: 'Domain',
            dataIndex: 'domain',
            key: 'domain',
            filters: domains.map(d => ({ text: d, value: d })),
            onFilter: (value: any, record: MailboxWithStats) => record.domain === value,
        },
        {
            title: 'Status',
            dataIndex: 'active',
            key: 'active',
            width: 90,
            render: (active: number) => (
                <Tag
                    style={{
                        background: active === 1 ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                        color: active === 1 ? '#4ade80' : '#f87171',
                        border: `1px solid ${active === 1 ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                        borderRadius: 4,
                    }}
                >
                    {active === 1 ? 'Active' : 'Disabled'}
                </Tag>
            ),
            filters: [{ text: 'Active', value: 1 }, { text: 'Disabled', value: 0 }],
            onFilter: (value: any, record: MailboxWithStats) => record.active === value,
        },
        {
            title: 'Used',
            key: 'used',
            width: 120,
            sorter: (a: MailboxWithStats, b: MailboxWithStats) => (a.used_pct ?? 0) - (b.used_pct ?? 0),
            render: (_: any, record: MailboxWithStats) => {
                if (record.used_pct === undefined) return <Text style={{ color: '#475569' }}>—</Text>;
                const pct = record.used_pct;
                const color = pct > 90 ? '#ef4444' : pct > 70 ? '#f59e0b' : '#22c55e';
                return record.quota > 0 ? (
                    <Tooltip title={`${record.used_mb ?? 0} MB / ${record.quota} MB`}>
                        <Progress percent={pct} size="small" strokeColor={color} trailColor="#1e293b" format={() => <span style={{ color: '#94a3b8', fontSize: 11 }}>{record.used_mb ?? 0} MB</span>} />
                    </Tooltip>
                ) : <Text style={{ color: '#475569' }}>—</Text>;
            },
        },
        {
            title: 'Unread',
            key: 'unread',
            width: 80,
            sorter: (a: MailboxWithStats, b: MailboxWithStats) => (a.unread_count ?? 0) - (b.unread_count ?? 0),
            render: (_: any, record: MailboxWithStats) => {
                if (record.unread_count === undefined) return <Text style={{ color: '#475569' }}>—</Text>;
                const count = record.unread_count;
                return count > 0 ? <Text strong style={{ color: '#60a5fa' }}>{count}</Text> : <Text style={{ color: '#475569' }}>0</Text>;
            },
        },
        {
            title: 'Last Received',
            key: 'last_received',
            width: 150,
            render: (_: any, record: MailboxWithStats) =>
                record.last_received_at ? (
                    <Text style={{ fontSize: 12, color: '#94a3b8' }}>{record.last_received_at}</Text>
                ) : <Text style={{ color: '#475569' }}>—</Text>,
        },
        {
            title: 'Sent (24h)',
            key: 'sent_total',
            width: 100,
            sorter: (a: MailboxWithStats, b: MailboxWithStats) => (a.sent_total ?? 0) - (b.sent_total ?? 0),
            render: (_: any, record: MailboxWithStats) => {
                if (record.sent_total === undefined) return <Text style={{ color: '#475569' }}>—</Text>;
                const total = record.sent_total;
                const rate = record.delivery_rate ?? 0;
                const color = rate >= 95 ? '#4ade80' : rate >= 80 ? '#fbbf24' : total > 0 ? '#f87171' : undefined;
                return total > 0 ? (
                    <Tooltip title={`Delivered: ${record.delivered ?? 0} | Bounced: ${record.bounced ?? 0} | Rate: ${rate}%`}>
                        <Space size={4}>
                            <SendOutlined style={{ color, fontSize: 12 }} />
                            <Text strong style={{ color }}>{total}</Text>
                        </Space>
                    </Tooltip>
                ) : <Text style={{ color: '#475569' }}>0</Text>;
            },
        },
        {
            title: 'Created',
            dataIndex: 'created',
            key: 'created',
            width: 110,
            render: (date: string) => date ? <Text style={{ fontSize: 12, color: '#94a3b8' }}>{new Date(date).toLocaleDateString()}</Text> : <Text style={{ color: '#475569' }}>—</Text>,
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 200,
            render: (_: any, record: MailboxWithStats) => (
                <Space size={4}>
                    {record.readable && (
                        <Tooltip title="Open Inbox">
                            <Button
                                size="small"
                                icon={<InboxOutlined />}
                                style={{ background: 'rgba(59,130,246,0.15)', borderColor: 'rgba(59,130,246,0.3)', color: '#60a5fa' }}
                                onClick={() => navigate(`/integrations/email/mailbox/${encodeURIComponent(record.email)}`)}
                            />
                        </Tooltip>
                    )}
                    <Tooltip title="Sent / Outbox">
                        <Button
                            size="small"
                            style={{ background: 'rgba(168,85,247,0.15)', borderColor: 'rgba(168,85,247,0.3)', color: '#a78bfa' }}
                            icon={<SendOutlined />}
                            onClick={() => navigate(`/integrations/email/mailbox/${encodeURIComponent(record.email)}?tab=sent`)}
                        />
                    </Tooltip>
                    <Tooltip title="Reset Password">
                        <Button
                            size="small"
                            icon={<LockOutlined />}
                            style={{ background: 'rgba(148,163,184,0.1)', borderColor: 'rgba(148,163,184,0.2)', color: '#94a3b8' }}
                            onClick={() => { setSelectedEmail(record.email); passwordForm.setFieldsValue({ email: record.email }); setPasswordOpen(true); }}
                        />
                    </Tooltip>
                    {record.active === 1 && (
                        <Tooltip title="Disable">
                            <Button
                                size="small"
                                icon={<StopOutlined />}
                                style={{ background: 'rgba(239,68,68,0.12)', borderColor: 'rgba(239,68,68,0.25)', color: '#f87171' }}
                                onClick={() => Modal.confirm({
                                    title: `Disable ${record.email}?`,
                                    content: 'This will prevent the mailbox from receiving new mail.',
                                    okText: 'Disable',
                                    okType: 'danger',
                                    onOk: () => disableMutation.mutate(record.email),
                                })}
                            />
                        </Tooltip>
                    )}
                </Space>
            ),
        },
    ];

    const tableRef = useRef<HTMLDivElement>(null);
    const scrollToTable = () => tableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Dashboard panel styles — Midnight Mode
    const panelCard: React.CSSProperties = {
        borderRadius: 14,
        border: '1px solid #1e293b',
        background: 'linear-gradient(145deg, #161d2e 0%, #111827 100%)',
        boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
        transition: 'transform 0.2s, box-shadow 0.2s, border-color 0.3s',
        height: '100%',
    };
    const panelCardHover = 'panel-card-hover';

    // Outbound totals
    const sentTotal = sentStats?.totals?.sent ?? 0;
    const deliveredTotal = sentStats?.totals?.delivered ?? 0;
    const bouncedTotal = sentStats?.totals?.bounced ?? 0;
    const deferredTotal = sentStats?.totals?.deferred ?? 0;
    const deliveryRate = sentStats?.totals?.delivery_rate ?? 0;

    // Outbound SVG mini bar chart data
    const outboundBars = [
        { label: 'Sent', value: sentTotal, color: '#3b82f6' },
        { label: 'Del', value: deliveredTotal, color: '#22c55e' },
        { label: 'Bnc', value: bouncedTotal, color: '#ef4444' },
        { label: 'Def', value: deferredTotal, color: '#f59e0b' },
    ];
    const maxBar = Math.max(...outboundBars.map(b => b.value), 1);

    return (
        <div style={{ background: '#0f1623', margin: -24, padding: 24, minHeight: 'calc(100vh - 64px)' }}>
            <style>{`
                .${panelCardHover}:hover {
                    transform: translateY(-3px);
                    box-shadow: 0 8px 28px rgba(0,0,0,0.4) !important;
                    border-color: #334155 !important;
                }
                .panel-clickable { cursor: pointer; }
                .panel-clickable:hover { transform: translateY(-4px); box-shadow: 0 10px 32px rgba(0,0,0,0.5) !important; border-color: #52c41a44 !important; }
                .health-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 8px; }
                .health-dot-ok { background: #22c55e; box-shadow: 0 0 10px rgba(34,197,94,0.6); }
                .health-dot-err { background: #ef4444; box-shadow: 0 0 10px rgba(239,68,68,0.6); }
                .stat-mini { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
                .stat-mini-value { font-size: 18px; font-weight: 700; line-height: 1.2; }
                .stat-mini-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
                .panel-title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; }
                .panel-title .ant-btn { color: #64748b !important; }
                .panel-title .ant-btn:hover { color: #94a3b8 !important; }
                /* ===== Midnight table overrides ===== */
                .midnight-table .ant-table { background: transparent !important; color: #cbd5e1 !important; }
                .midnight-table .ant-table-container { border: none !important; }
                .midnight-table .ant-table-content { background: transparent !important; }
                /* Header */
                .midnight-table .ant-table-thead > tr > th,
                .midnight-table .ant-table-thead > tr > td { background: #1a2235 !important; color: #94a3b8 !important; border-bottom: 1px solid #1e293b !important; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
                .midnight-table .ant-table-thead > tr > th::before { background: #1e293b !important; }
                /* Body cells — force ALL text light */
                .midnight-table .ant-table-tbody > tr > td { border-bottom: 1px solid #1e293b !important; color: #cbd5e1 !important; background: transparent !important; }
                .midnight-table .ant-table-tbody > tr > td * { color: inherit; }
                .midnight-table .ant-table-tbody > tr:hover > td { background: #1a2640 !important; }
                .midnight-table .ant-table-tbody > tr.ant-table-row:hover > td { background: #1a2640 !important; }
                /* Typography inside table */
                .midnight-table .ant-typography { color: #cbd5e1 !important; }
                .midnight-table .ant-typography.ant-typography-secondary { color: #64748b !important; }
                .midnight-table .ant-typography strong { color: #e2e8f0 !important; }
                /* Progress bar text */
                .midnight-table .ant-progress-text { color: #94a3b8 !important; }
                .midnight-table .ant-progress-inner { background: #1e293b !important; }
                /* Tags — make Ant Design color prop transparent and use custom dark style */
                .midnight-table .ant-tag-green { background: rgba(34,197,94,0.15) !important; color: #4ade80 !important; border-color: rgba(34,197,94,0.3) !important; }
                .midnight-table .ant-tag-red { background: rgba(239,68,68,0.15) !important; color: #f87171 !important; border-color: rgba(239,68,68,0.3) !important; }
                .midnight-table .ant-tag-blue { background: rgba(59,130,246,0.2) !important; color: #60a5fa !important; border-color: rgba(59,130,246,0.3) !important; }
                .midnight-table .ant-tag { border-radius: 4px; }
                /* Buttons inside table */
                .midnight-table .ant-btn { border-color: #334155 !important; }
                .midnight-table .ant-btn:hover { border-color: #475569 !important; opacity: 0.9; }
                .midnight-table .ant-btn-primary { background: rgba(59,130,246,0.15) !important; border-color: rgba(59,130,246,0.3) !important; color: #60a5fa !important; }
                .midnight-table .ant-btn-dangerous { background: rgba(239,68,68,0.12) !important; border-color: rgba(239,68,68,0.25) !important; color: #f87171 !important; }
                /* Pagination */
                .midnight-table .ant-pagination { color: #94a3b8; }
                .midnight-table .ant-pagination .ant-pagination-item { background: #161d2e; border-color: #1e293b; }
                .midnight-table .ant-pagination .ant-pagination-item a { color: #94a3b8; }
                .midnight-table .ant-pagination .ant-pagination-item-active { border-color: #3b82f6; }
                .midnight-table .ant-pagination .ant-pagination-item-active a { color: #3b82f6; }
                .midnight-table .ant-pagination .ant-pagination-prev .ant-pagination-item-link,
                .midnight-table .ant-pagination .ant-pagination-next .ant-pagination-item-link { color: #64748b; background: #161d2e; border-color: #1e293b; }
                .midnight-table .ant-pagination .ant-pagination-total-text { color: #64748b; }
                .midnight-table .ant-select-selector { background: #161d2e !important; border-color: #1e293b !important; color: #94a3b8 !important; }
                .midnight-table .ant-select-arrow { color: #475569 !important; }
                /* Sorter and filter icons */
                .midnight-table .ant-table-column-sorter { color: #475569 !important; }
                .midnight-table .ant-table-filter-trigger { color: #475569 !important; }
                .midnight-table .ant-empty-description { color: #475569 !important; }
                .midnight-table .ant-table-cell { transition: background 0.2s; }
                .midnight-table .ant-spin-dot-item { background-color: #3b82f6 !important; }
                /* Drawer close button visibility */
                .ant-drawer .ant-drawer-close { color: #94a3b8 !important; }
                .ant-drawer .ant-drawer-close:hover { color: #e2e8f0 !important; }
                /* Midnight button overrides */
                .midnight-header .ant-btn-default { background: #161d2e; border-color: #1e293b; color: #94a3b8; }
                .midnight-header .ant-btn-default:hover { border-color: #334155; color: #e2e8f0; background: #1a2235; }
                .midnight-header .ant-btn-primary { background: linear-gradient(135deg, #3b82f6, #2563eb); border: none; }
                .midnight-header .ant-btn-primary:hover { background: linear-gradient(135deg, #60a5fa, #3b82f6); }
                /* Outbound bar glow */
                .bar-glow { filter: drop-shadow(0 0 4px currentColor); }
            `}</style>

            <div className="midnight-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <Title level={3} style={{ margin: 0, color: '#e2e8f0' }}>Email Administration</Title>
                <Space>
                    <Button icon={<LinkOutlined />} onClick={() => setAliasOpen(true)}>Add Alias</Button>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>Create Mailbox</Button>
                </Space>
            </div>

            {/* ── Graphical Dashboard ── */}
            <Row gutter={[20, 20]} style={{ marginBottom: 28 }}>
                {/* Panel 1: Mailboxes (Donut) */}
                <Col xs={24} sm={12} lg={6}>
                    <Card
                        size="small"
                        className={`${panelCardHover} panel-clickable`}
                        style={panelCard}
                        onClick={scrollToTable}
                    >
                        <div className="panel-title">
                            <span><MailOutlined style={{ marginRight: 6 }} />Mailboxes</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                            <Progress
                                type="circle"
                                percent={mergedMailboxes.length > 0 ? Math.round((activeCount / mergedMailboxes.length) * 100) : 0}
                                size={90}
                                strokeColor={{ '0%': '#22c55e', '100%': '#14b8a6' }}
                                trailColor="#1e293b"
                                format={() => (
                                    <div style={{ textAlign: 'center' }}>
                                        <div style={{ fontSize: 28, fontWeight: 800, color: '#e2e8f0', lineHeight: 1 }}>{mergedMailboxes.length}</div>
                                        <div style={{ fontSize: 10, color: '#64748b' }}>Total</div>
                                    </div>
                                )}
                            />
                            <div>
                                <div className="stat-mini">
                                    <CheckCircleOutlined style={{ color: '#22c55e', fontSize: 14 }} />
                                    <span className="stat-mini-value" style={{ color: '#22c55e' }}>{activeCount}</span>
                                    <span className="stat-mini-label">Active</span>
                                </div>
                                <div className="stat-mini">
                                    <StopOutlined style={{ color: disabledCount > 0 ? '#ef4444' : '#334155', fontSize: 14 }} />
                                    <span className="stat-mini-value" style={{ color: disabledCount > 0 ? '#ef4444' : '#475569' }}>{disabledCount}</span>
                                    <span className="stat-mini-label">Disabled</span>
                                </div>
                                <div style={{ fontSize: 10, color: '#475569', marginTop: 6 }}>Click to view list ↓</div>
                            </div>
                        </div>
                    </Card>
                </Col>

                {/* Panel 2: Inbound */}
                <Col xs={24} sm={12} lg={6}>
                    <Card size="small" className={panelCardHover} style={panelCard}>
                        <div className="panel-title">
                            <span><InboxOutlined style={{ marginRight: 6 }} />Inbound</span>
                            <Tooltip title="Refresh all stats">
                                <Button
                                    type="text" size="small"
                                    icon={bulkStats?.refreshing ? <SyncOutlined spin /> : <ReloadOutlined />}
                                    onClick={() => { refreshMutation.mutate(); refetchStats(); }}
                                    loading={refreshMutation.isPending}
                                    style={{ fontSize: 12 }}
                                />
                            </Tooltip>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                            <div style={{
                                width: 90, height: 90, borderRadius: '50%',
                                background: totalUnread > 0
                                    ? 'linear-gradient(135deg, #1e40af33, #3b82f644)'
                                    : 'linear-gradient(135deg, #1e293b, #0f172a)',
                                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                                border: `3px solid ${totalUnread > 0 ? '#3b82f6' : '#1e293b'}`,
                                boxShadow: totalUnread > 0 ? '0 0 16px rgba(59,130,246,0.3)' : 'none',
                            }}>
                                <div style={{ fontSize: 26, fontWeight: 800, color: totalUnread > 0 ? '#60a5fa' : '#475569', lineHeight: 1 }}>{totalUnread}</div>
                                <div style={{ fontSize: 10, color: '#64748b' }}>Unread</div>
                            </div>
                            <div>
                                <div className="stat-mini">
                                    <CloudServerOutlined style={{ color: (serverStats?.queue_total ?? 0) > 10 ? '#f59e0b' : '#22c55e', fontSize: 14 }} />
                                    <span className="stat-mini-value">{serverStats?.queue_total ?? 0}</span>
                                    <span className="stat-mini-label">Queue</span>
                                </div>
                                <div className="stat-mini">
                                    <WarningOutlined style={{ color: (serverStats?.deferred ?? 0) > 0 ? '#ef4444' : '#334155', fontSize: 14 }} />
                                    <span className="stat-mini-value" style={{ color: (serverStats?.deferred ?? 0) > 0 ? '#ef4444' : '#475569' }}>{serverStats?.deferred ?? 0}</span>
                                    <span className="stat-mini-label">Deferred</span>
                                </div>
                                <div style={{ fontSize: 10, color: '#475569', marginTop: 6 }}>
                                    Updated: {statsAgeLabel}
                                    {bulkStats?.refreshing && <SyncOutlined spin style={{ marginLeft: 4, fontSize: 10 }} />}
                                </div>
                            </div>
                        </div>
                    </Card>
                </Col>

                {/* Panel 3: Outbound */}
                <Col xs={24} sm={12} lg={6}>
                    <Card size="small" className={panelCardHover} style={panelCard}>
                        <div className="panel-title">
                            <span><SendOutlined style={{ marginRight: 6 }} />Outbound (24h)</span>
                            <Tooltip title="Refresh sent stats">
                                <Button
                                    type="text" size="small"
                                    icon={sentStats?.refreshing ? <SyncOutlined spin /> : <ReloadOutlined />}
                                    onClick={() => sentRefreshMutation.mutate()}
                                    loading={sentRefreshMutation.isPending}
                                    style={{ fontSize: 12 }}
                                />
                            </Tooltip>
                        </div>
                        <div style={{ marginBottom: 8 }}>
                            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                                <span style={{ fontSize: 30, fontWeight: 800, color: '#e2e8f0' }}>{sentTotal.toLocaleString()}</span>
                                <span style={{ fontSize: 13, color: '#64748b' }}>Sent</span>
                            </div>
                        </div>
                        {/* Mini SVG bar chart */}
                        <div style={{ marginBottom: 10 }}>
                            <svg width="100%" height="50" viewBox="0 0 200 50" preserveAspectRatio="none">
                                {outboundBars.map((bar, i) => {
                                    const barHeight = maxBar > 0 ? (bar.value / maxBar) * 40 : 0;
                                    const x = i * 50 + 10;
                                    return (
                                        <g key={bar.label}>
                                            <rect x={x} y={45 - barHeight} width={28} height={barHeight} rx={3}
                                                fill={bar.color} opacity={0.85} className="bar-glow" style={{ color: bar.color }} />
                                            <text x={x + 14} y={48} textAnchor="middle" fill="#64748b" fontSize="7" fontWeight="500">{bar.label}</text>
                                        </g>
                                    );
                                })}
                            </svg>
                        </div>
                        <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <span style={{ fontSize: 11, color: '#64748b' }}>Delivery Rate</span>
                                <span style={{ fontSize: 13, fontWeight: 700, color: deliveryRate >= 95 ? '#22c55e' : '#f59e0b' }}>{deliveryRate}%</span>
                            </div>
                            <Progress
                                percent={deliveryRate}
                                showInfo={false}
                                size="small"
                                strokeColor={deliveryRate >= 95 ? { '0%': '#22c55e', '100%': '#14b8a6' } : { '0%': '#f59e0b', '100%': '#f97316' }}
                                trailColor="#1e293b"
                            />
                        </div>
                    </Card>
                </Col>

                {/* Panel 4: Server Health */}
                <Col xs={24} sm={12} lg={6}>
                    <Card size="small" className={panelCardHover} style={panelCard}>
                        <div className="panel-title">
                            <span><CloudServerOutlined style={{ marginRight: 6 }} />Server Health</span>
                            <Tooltip title="Refresh health">
                                <Button
                                    type="text" size="small"
                                    icon={<ReloadOutlined />}
                                    onClick={() => refetchHealth()}
                                    loading={healthLoading}
                                    style={{ fontSize: 12 }}
                                />
                            </Tooltip>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 4 }}>
                            {[
                                { label: 'SMTP', status: health?.smtp, detail: health?.smtp_detail },
                                { label: 'IMAP', status: health?.imap, detail: health?.imap_detail },
                                { label: 'SSH Bridge', status: health?.ssh_bridge, detail: health?.ssh_detail },
                            ].map(svc => (
                                <Tooltip key={svc.label} title={svc.detail || svc.status}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>
                                            <span className={`health-dot ${svc.status === 'ok' ? 'health-dot-ok' : 'health-dot-err'}`} />
                                            <Text style={{ fontSize: 13, color: '#cbd5e1' }}>{svc.label}</Text>
                                        </div>
                                        <Tag style={{
                                            margin: 0, fontSize: 11,
                                            background: svc.status === 'ok' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                                            color: svc.status === 'ok' ? '#4ade80' : '#f87171',
                                            border: `1px solid ${svc.status === 'ok' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                                            borderRadius: 4,
                                        }}>
                                            {svc.status === 'ok' ? 'Online' : 'Down'}
                                        </Tag>
                                    </div>
                                </Tooltip>
                            ))}
                        </div>
                        <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid #1e293b', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Text
                                className="stat-mini-label"
                                style={{ cursor: 'pointer', textDecoration: 'underline', textDecorationColor: '#334155' }}
                                onClick={() => setDomainListOpen(true)}
                            >
                                <GlobalOutlined style={{ marginRight: 4 }} />
                                {domains.length} domain{domains.length !== 1 ? 's' : ''}
                            </Text>
                            <Text className="stat-mini-label">Queue: {serverStats?.queue_total ?? 0}</Text>
                        </div>
                    </Card>
                </Col>
            </Row>

            {/* ── Mailbox Table ── */}
            <div ref={tableRef} />
            <div className="midnight-table">
                <Table
                    dataSource={mergedMailboxes}
                    columns={columns}
                    rowKey="email"
                    loading={isLoading}
                    size="middle"
                    pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `${total} mailboxes` }}
                    locale={{
                        emptyText: isError ? (
                            <div style={{ padding: '40px 0', color: '#ef4444' }}>
                                <WarningOutlined style={{ fontSize: 32, marginBottom: 12 }} />
                                <div style={{ fontSize: 16, fontWeight: 600 }}>Connection to mail system failed</div>
                                <div style={{ fontSize: 13, marginTop: 8, color: '#f87171' }}>
                                    {String((error as any)?.response?.data?.detail || (error as any)?.message || 'Check SSH Bridge credentials')}
                                </div>
                            </div>
                        ) : undefined
                    }}
                />
            </div>

            {/* Create Mailbox Modal */}
            <Modal
                title="Create Mailbox"
                open={createOpen}
                onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
                onOk={() => createForm.submit()}
                confirmLoading={createMutation.isPending}
            >
                <Form form={createForm} layout="vertical" onFinish={(values) => createMutation.mutate(values)}>
                    <Form.Item name="email" label="Email Address" rules={[{ required: true, type: 'email' }]}>
                        <Input placeholder="user@gsmcall.com" prefix={<MailOutlined />} />
                    </Form.Item>
                    <Form.Item name="password" label="Password" rules={[{ required: true, min: 8 }]}>
                        <Input.Password placeholder="Minimum 8 characters" prefix={<LockOutlined />} />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Reset Password Modal */}
            <Modal
                title={`Reset Password: ${selectedEmail}`}
                open={passwordOpen}
                onCancel={() => { setPasswordOpen(false); passwordForm.resetFields(); }}
                onOk={() => passwordForm.submit()}
                confirmLoading={passwordMutation.isPending}
            >
                <Form form={passwordForm} layout="vertical" onFinish={(values) => passwordMutation.mutate(values)}>
                    <Form.Item name="email" hidden><Input /></Form.Item>
                    <Form.Item name="password" label="New Password" rules={[{ required: true, min: 8 }]}>
                        <Input.Password placeholder="New password" prefix={<LockOutlined />} />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Add Alias Modal */}
            <Modal
                title="Add Mail Alias"
                open={aliasOpen}
                onCancel={() => { setAliasOpen(false); aliasForm.resetFields(); }}
                onOk={() => aliasForm.submit()}
                confirmLoading={aliasMutation.isPending}
            >
                <Form form={aliasForm} layout="vertical" onFinish={(values) => aliasMutation.mutate(values)}>
                    <Form.Item name="alias" label="Alias Address" rules={[{ required: true, type: 'email' }]}>
                        <Input placeholder="alias@gsmcall.com" prefix={<MailOutlined />} />
                    </Form.Item>
                    <Form.Item name="destination" label="Destination Address" rules={[{ required: true, type: 'email' }]}>
                        <Input placeholder="real@gsmcall.com" prefix={<MailOutlined />} />
                    </Form.Item>
                </Form>
            </Modal>

            {/* ══════ Domain List Drawer ══════ */}
            <Drawer
                title={<span style={{ color: '#e2e8f0' }}><GlobalOutlined style={{ marginRight: 8 }} />Domains ({domains.length})</span>}
                open={domainListOpen}
                onClose={() => setDomainListOpen(false)}
                width={520}
                styles={{
                    header: { background: '#0f1623', borderBottom: '1px solid #1e293b' },
                    body: { background: '#0f1623', padding: 20 },
                    wrapper: {},
                }}
                extra={
                    <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        size="small"
                        style={{ background: 'linear-gradient(135deg, #3b82f6, #2563eb)', border: 'none' }}
                        onClick={() => setAddDomainOpen(true)}
                    >
                        Add Domain
                    </Button>
                }
            >
                {domains.length === 0 ? (
                    <Empty description={<span style={{ color: '#475569' }}>No domains found</span>} />
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        {domains.sort().map(d => {
                            const domMailboxes = mergedMailboxes.filter(m => m.domain === d);
                            const domActive = domMailboxes.filter(m => m.active === 1).length;
                            const domUnread = domMailboxes.reduce((sum, m) => sum + (m.unread_count || 0), 0);
                            const domSent = domMailboxes.reduce((sum, m) => sum + (m.sent_total || 0), 0);
                            return (
                                <div
                                    key={d}
                                    onClick={() => setSelectedDomain(d)}
                                    style={{
                                        background: 'linear-gradient(145deg, #161d2e, #111827)',
                                        border: '1px solid #1e293b',
                                        borderRadius: 12,
                                        padding: '16px 20px',
                                        cursor: 'pointer',
                                        transition: 'border-color 0.2s, transform 0.2s',
                                    }}
                                    onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.borderColor = '#334155'; (e.currentTarget as HTMLDivElement).style.transform = 'translateX(4px)'; }}
                                    onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.borderColor = '#1e293b'; (e.currentTarget as HTMLDivElement).style.transform = 'none'; }}
                                >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                                        <Text strong style={{ color: '#e2e8f0', fontSize: 15 }}>
                                            <GlobalOutlined style={{ marginRight: 8, color: '#3b82f6' }} />{d}
                                        </Text>
                                        <ArrowRightOutlined style={{ color: '#475569', fontSize: 12 }} />
                                    </div>
                                    <div style={{ display: 'flex', gap: 20 }}>
                                        <div>
                                            <div style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0' }}>{domMailboxes.length}</div>
                                            <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>Mailboxes</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: 16, fontWeight: 700, color: '#22c55e' }}>{domActive}</div>
                                            <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>Active</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: 16, fontWeight: 700, color: domUnread > 0 ? '#60a5fa' : '#475569' }}>{domUnread}</div>
                                            <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>Unread</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: 16, fontWeight: 700, color: domSent > 0 ? '#a78bfa' : '#475569' }}>{domSent}</div>
                                            <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>Sent 24h</div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </Drawer>

            {/* ══════ Per-Domain Detail Drawer ══════ */}
            <Drawer
                title={
                    <span style={{ color: '#e2e8f0' }}>
                        <GlobalOutlined style={{ marginRight: 8, color: '#3b82f6' }} />
                        {selectedDomain}
                    </span>
                }
                open={!!selectedDomain}
                onClose={() => setSelectedDomain(null)}
                width={Math.min(1100, window.innerWidth - 40)}
                styles={{
                    header: { background: '#0f1623', borderBottom: '1px solid #1e293b' },
                    body: { background: '#0f1623', padding: 20 },
                }}
                extra={
                    <Button
                        size="small"
                        onClick={() => setSelectedDomain(null)}
                        style={{ background: '#161d2e', borderColor: '#334155', color: '#94a3b8' }}
                    >
                        ← Back to Domains
                    </Button>
                }
            >
                {selectedDomain && (() => {
                    const dm = mergedMailboxes.filter(m => m.domain === selectedDomain);
                    const dActive = dm.filter(m => m.active === 1).length;
                    const dDisabled = dm.filter(m => m.active === 0).length;
                    const dUnread = dm.reduce((s, m) => s + (m.unread_count || 0), 0);
                    const dSent = dm.reduce((s, m) => s + (m.sent_total || 0), 0);
                    const dDelivered = dm.reduce((s, m) => s + (m.delivered || 0), 0);
                    const dBounced = dm.reduce((s, m) => s + (m.bounced || 0), 0);
                    const dRate = dSent > 0 ? Math.round((dDelivered / dSent) * 100) : 0;
                    return (
                        <>
                            {/* Mini Dashboard Row */}
                            <Row gutter={[14, 14]} style={{ marginBottom: 24 }}>
                                <Col xs={12} lg={6}>
                                    <div style={{ background: 'linear-gradient(145deg, #161d2e, #111827)', border: '1px solid #1e293b', borderRadius: 12, padding: 16, height: '100%' }}>
                                        <div className="panel-title" style={{ marginBottom: 10 }}>
                                            <span><MailOutlined style={{ marginRight: 6 }} />Mailboxes</span>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                                            <Progress
                                                type="circle"
                                                percent={dm.length > 0 ? Math.round((dActive / dm.length) * 100) : 0}
                                                size={64}
                                                strokeColor={{ '0%': '#22c55e', '100%': '#14b8a6' }}
                                                trailColor="#1e293b"
                                                format={() => (
                                                    <div style={{ textAlign: 'center' }}>
                                                        <div style={{ fontSize: 20, fontWeight: 800, color: '#e2e8f0', lineHeight: 1 }}>{dm.length}</div>
                                                    </div>
                                                )}
                                            />
                                            <div>
                                                <div style={{ fontSize: 13, color: '#22c55e' }}><CheckCircleOutlined style={{ marginRight: 4 }} />{dActive} active</div>
                                                <div style={{ fontSize: 13, color: dDisabled > 0 ? '#ef4444' : '#475569' }}><StopOutlined style={{ marginRight: 4 }} />{dDisabled} disabled</div>
                                            </div>
                                        </div>
                                    </div>
                                </Col>
                                <Col xs={12} lg={6}>
                                    <div style={{ background: 'linear-gradient(145deg, #161d2e, #111827)', border: '1px solid #1e293b', borderRadius: 12, padding: 16, height: '100%' }}>
                                        <div className="panel-title" style={{ marginBottom: 10 }}>
                                            <span><InboxOutlined style={{ marginRight: 6 }} />Inbound</span>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                                            <div style={{
                                                width: 64, height: 64, borderRadius: '50%',
                                                background: dUnread > 0 ? 'linear-gradient(135deg, #1e40af33, #3b82f644)' : 'linear-gradient(135deg, #1e293b, #0f172a)',
                                                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                                                border: `3px solid ${dUnread > 0 ? '#3b82f6' : '#1e293b'}`,
                                            }}>
                                                <div style={{ fontSize: 20, fontWeight: 800, color: dUnread > 0 ? '#60a5fa' : '#475569', lineHeight: 1 }}>{dUnread}</div>
                                                <div style={{ fontSize: 8, color: '#64748b' }}>Unread</div>
                                            </div>
                                            <div style={{ fontSize: 12, color: '#64748b' }}>
                                                {dm.filter(m => (m.unread_count ?? 0) > 0).length} mailbox{dm.filter(m => (m.unread_count ?? 0) > 0).length !== 1 ? 'es' : ''} with unread
                                            </div>
                                        </div>
                                    </div>
                                </Col>
                                <Col xs={12} lg={6}>
                                    <div style={{ background: 'linear-gradient(145deg, #161d2e, #111827)', border: '1px solid #1e293b', borderRadius: 12, padding: 16, height: '100%' }}>
                                        <div className="panel-title" style={{ marginBottom: 10 }}>
                                            <span><SendOutlined style={{ marginRight: 6 }} />Outbound</span>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 6 }}>
                                            <span style={{ fontSize: 22, fontWeight: 800, color: '#e2e8f0' }}>{dSent.toLocaleString()}</span>
                                            <span style={{ fontSize: 11, color: '#64748b' }}>Sent</span>
                                        </div>
                                        <div style={{ display: 'flex', gap: 14, marginBottom: 8 }}>
                                            <div><span style={{ fontSize: 13, fontWeight: 700, color: '#4ade80' }}>{dDelivered}</span> <span style={{ fontSize: 10, color: '#64748b' }}>del</span></div>
                                            <div><span style={{ fontSize: 13, fontWeight: 700, color: dBounced > 0 ? '#f87171' : '#475569' }}>{dBounced}</span> <span style={{ fontSize: 10, color: '#64748b' }}>bnc</span></div>
                                        </div>
                                        <Progress percent={dRate} showInfo={false} size="small" strokeColor={dRate >= 95 ? { '0%': '#22c55e', '100%': '#14b8a6' } : { '0%': '#f59e0b', '100%': '#f97316' }} trailColor="#1e293b" />
                                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                                            <span style={{ fontSize: 11, fontWeight: 700, color: dRate >= 95 ? '#22c55e' : '#f59e0b' }}>{dRate}%</span>
                                        </div>
                                    </div>
                                </Col>
                                <Col xs={12} lg={6}>
                                    <div style={{ background: 'linear-gradient(145deg, #161d2e, #111827)', border: '1px solid #1e293b', borderRadius: 12, padding: 16, height: '100%' }}>
                                        <div className="panel-title" style={{ marginBottom: 10 }}>
                                            <span><CloudServerOutlined style={{ marginRight: 6 }} />Health</span>
                                        </div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                            {[
                                                { label: 'SMTP', status: health?.smtp },
                                                { label: 'IMAP', status: health?.imap },
                                                { label: 'SSH', status: health?.ssh_bridge },
                                            ].map(svc => (
                                                <div key={svc.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                                    <div style={{ display: 'flex', alignItems: 'center' }}>
                                                        <span className={`health-dot ${svc.status === 'ok' ? 'health-dot-ok' : 'health-dot-err'}`} />
                                                        <Text style={{ fontSize: 12, color: '#cbd5e1' }}>{svc.label}</Text>
                                                    </div>
                                                    <Tag color={svc.status === 'ok' ? 'green' : 'red'} style={{ margin: 0, fontSize: 10, background: svc.status === 'ok' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', color: svc.status === 'ok' ? '#4ade80' : '#f87171', borderColor: svc.status === 'ok' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)' }}>
                                                        {svc.status === 'ok' ? 'Online' : 'Down'}
                                                    </Tag>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </Col>
                            </Row>

                            {/* Filtered Mailbox Table */}
                            <div className="midnight-table">
                                <Table
                                    dataSource={dm}
                                    columns={columns}
                                    rowKey="email"
                                    size="middle"
                                    pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (total) => `${total} mailboxes` }}
                                />
                            </div>
                        </>
                    );
                })()}
            </Drawer>

            {/* ══════ Add Domain Modal ══════ */}
            <Modal
                title="Add Domain"
                open={addDomainOpen}
                onCancel={() => { setAddDomainOpen(false); addDomainForm.resetFields(); }}
                onOk={() => addDomainForm.submit()}
                confirmLoading={createMutation.isPending}
            >
                <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                    Creates a <code>postmaster@domain</code> mailbox to register the new domain.
                </Text>
                <Form
                    form={addDomainForm}
                    layout="vertical"
                    onFinish={(values) => {
                        const email = `postmaster@${values.domain}`;
                        createMutation.mutate({ email, password: values.password });
                        setAddDomainOpen(false);
                        addDomainForm.resetFields();
                    }}
                >
                    <Form.Item name="domain" label="Domain Name" rules={[{ required: true, message: 'Enter a domain' }]}>
                        <Input placeholder="example.com" prefix={<GlobalOutlined />} />
                    </Form.Item>
                    <Form.Item name="password" label="Postmaster Password" rules={[{ required: true, min: 8 }]}>
                        <Input.Password placeholder="Minimum 8 characters" prefix={<LockOutlined />} />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
