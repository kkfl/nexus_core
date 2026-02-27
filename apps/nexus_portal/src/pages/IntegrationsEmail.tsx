import { Table, Button, Modal, Form, Input, Typography, Space, Tag, Card, message, Tooltip, Row, Col, Statistic, Progress } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { emailClient } from '../api/emailClient';
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    MailOutlined,
    PlusOutlined,
    LockOutlined,
    StopOutlined,
    LinkOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
    ReloadOutlined,
    InboxOutlined,
    WarningOutlined,
    CloudServerOutlined,
    SyncOutlined,
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
    const { data: mailboxes, isLoading, refetch: refetchMailboxes } = useQuery<Mailbox[]>({
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
        onError: () => message.error('Stats refresh failed'),
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

    const mergedMailboxes: MailboxWithStats[] = useMemo(() => {
        if (!mailboxes) return [];
        return mailboxes.map(m => {
            const s = statsMap[m.email];
            return {
                ...m,
                used_mb: s?.used_mb,
                used_pct: s?.used_pct,
                free_pct: s?.free_pct,
                unread_count: s?.unread_count,
                total_count: s?.total_count,
                last_received_at: s?.last_received_at,
                readable: s?.readable ?? true,
            };
        });
    }, [mailboxes, statsMap]);

    // Mutations
    const createMutation = useMutation({
        mutationFn: async (values: { email: string; password: string }) =>
            (await emailClient.post('/email/admin/mailbox/create', values)).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Mailbox ${data.email} ${data.action}`);
                queryClient.invalidateQueries({ queryKey: ['email_mailboxes'] });
                setCreateOpen(false);
                createForm.resetFields();
            } else {
                message.error(data.error || 'Creation failed');
            }
        },
        onError: () => message.error('Request failed'),
    });

    const passwordMutation = useMutation({
        mutationFn: async (values: { email: string; password: string }) =>
            (await emailClient.post('/email/admin/mailbox/password', values)).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Password updated for ${data.email}`);
                setPasswordOpen(false);
                passwordForm.resetFields();
            } else {
                message.error(data.error || 'Password update failed');
            }
        },
        onError: () => message.error('Request failed'),
    });

    const disableMutation = useMutation({
        mutationFn: async (em: string) =>
            (await emailClient.post('/email/admin/mailbox/disable', { email: em })).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Mailbox ${data.email} ${data.action}`);
                queryClient.invalidateQueries({ queryKey: ['email_mailboxes'] });
            } else {
                message.error(data.error || 'Disable failed');
            }
        },
        onError: () => message.error('Request failed'),
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
                message.error(data.error || 'Alias creation failed');
            }
        },
        onError: () => message.error('Request failed'),
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

    const statusIcon = (status: string) =>
        status === 'ok'
            ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
            : <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;

    const columns = [
        {
            title: 'Email',
            dataIndex: 'email',
            key: 'email',
            sorter: (a: MailboxWithStats, b: MailboxWithStats) => a.email.localeCompare(b.email),
            render: (em: string, record: MailboxWithStats) => (
                <Space>
                    <Text strong><MailOutlined style={{ marginRight: 6 }} />{em}</Text>
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
                <Tag color={active === 1 ? 'green' : 'red'}>
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
                if (record.used_pct === undefined) return <Text type="secondary">—</Text>;
                const pct = record.used_pct;
                const color = pct > 90 ? '#ff4d4f' : pct > 70 ? '#faad14' : '#52c41a';
                return record.quota > 0 ? (
                    <Tooltip title={`${record.used_mb ?? 0} MB / ${record.quota} MB`}>
                        <Progress percent={pct} size="small" strokeColor={color} format={() => `${record.used_mb ?? 0} MB`} />
                    </Tooltip>
                ) : <Text type="secondary">—</Text>;
            },
        },
        {
            title: 'Unread',
            key: 'unread',
            width: 80,
            sorter: (a: MailboxWithStats, b: MailboxWithStats) => (a.unread_count ?? 0) - (b.unread_count ?? 0),
            render: (_: any, record: MailboxWithStats) => {
                if (record.unread_count === undefined) return <Text type="secondary">—</Text>;
                const count = record.unread_count;
                return count > 0 ? <Text strong style={{ color: '#1677ff' }}>{count}</Text> : <Text type="secondary">0</Text>;
            },
        },
        {
            title: 'Last Received',
            key: 'last_received',
            width: 150,
            render: (_: any, record: MailboxWithStats) =>
                record.last_received_at ? (
                    <Text type="secondary" style={{ fontSize: 12 }}>{record.last_received_at}</Text>
                ) : <Text type="secondary">—</Text>,
        },
        {
            title: 'Created',
            dataIndex: 'created',
            key: 'created',
            width: 110,
            render: (date: string) => date ? <Text type="secondary" style={{ fontSize: 12 }}>{new Date(date).toLocaleDateString()}</Text> : '—',
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 180,
            render: (_: any, record: MailboxWithStats) => (
                <Space size={4}>
                    {record.readable && (
                        <Tooltip title="Open Inbox">
                            <Button
                                size="small"
                                type="primary"
                                ghost
                                icon={<InboxOutlined />}
                                onClick={() => navigate(`/integrations/email/mailbox/${encodeURIComponent(record.email)}`)}
                            />
                        </Tooltip>
                    )}
                    <Tooltip title="Reset Password">
                        <Button
                            size="small"
                            icon={<LockOutlined />}
                            onClick={() => { setSelectedEmail(record.email); passwordForm.setFieldsValue({ email: record.email }); setPasswordOpen(true); }}
                        />
                    </Tooltip>
                    {record.active === 1 && (
                        <Tooltip title="Disable">
                            <Button
                                size="small"
                                danger
                                icon={<StopOutlined />}
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

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <Title level={3} style={{ margin: 0 }}>Email Administration</Title>
                <Space>
                    <Tooltip title={`Stats: ${statsAgeLabel}${bulkStats?.refreshing ? ' (refreshing…)' : ''}`}>
                        <Button
                            icon={bulkStats?.refreshing ? <SyncOutlined spin /> : <ReloadOutlined />}
                            onClick={() => refreshMutation.mutate()}
                            loading={refreshMutation.isPending}
                        >
                            Refresh Stats
                        </Button>
                    </Tooltip>
                    <Button icon={<ReloadOutlined />} onClick={() => { refetchMailboxes(); refetchHealth(); refetchStats(); }}>Refresh All</Button>
                    <Button icon={<LinkOutlined />} onClick={() => setAliasOpen(true)}>Add Alias</Button>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>Create Mailbox</Button>
                </Space>
            </div>

            {/* Server Stats + Health */}
            <Row gutter={16} style={{ marginBottom: 20 }}>
                <Col span={4}>
                    <Card size="small">
                        <Statistic title="Total Mailboxes" value={mergedMailboxes.length} prefix={<MailOutlined />} />
                    </Card>
                </Col>
                <Col span={3}>
                    <Card size="small">
                        <Statistic title="Active" value={activeCount} valueStyle={{ color: '#3f8600' }} />
                    </Card>
                </Col>
                <Col span={3}>
                    <Card size="small">
                        <Statistic title="Disabled" value={disabledCount} valueStyle={{ color: disabledCount > 0 ? '#cf1322' : undefined }} />
                    </Card>
                </Col>
                <Col span={3}>
                    <Card size="small">
                        <Statistic title="Total Unread" value={totalUnread} prefix={<InboxOutlined />} valueStyle={{ color: totalUnread > 0 ? '#1677ff' : undefined }} />
                    </Card>
                </Col>
                <Col span={3}>
                    <Card size="small">
                        <Statistic
                            title="Mail Queue"
                            value={serverStats?.queue_total ?? '—'}
                            prefix={<CloudServerOutlined />}
                            valueStyle={{ color: (serverStats?.queue_total ?? 0) > 10 ? '#faad14' : undefined }}
                        />
                    </Card>
                </Col>
                <Col span={3}>
                    <Card size="small">
                        <Statistic
                            title="Deferred"
                            value={serverStats?.deferred ?? '—'}
                            prefix={<WarningOutlined />}
                            valueStyle={{ color: (serverStats?.deferred ?? 0) > 0 ? '#cf1322' : undefined }}
                        />
                    </Card>
                </Col>
                <Col span={5}>
                    <Card size="small" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                        <Space direction="vertical" size={2}>
                            <Space>{statusIcon(health?.smtp || 'error')} <Text>SMTP</Text></Space>
                            <Space>{statusIcon(health?.imap || 'error')} <Text>IMAP</Text></Space>
                            <Space>{statusIcon(health?.ssh_bridge || 'error')} <Text>SSH Bridge</Text></Space>
                        </Space>
                        <Button type="link" size="small" icon={<ReloadOutlined />} onClick={() => refetchHealth()} loading={healthLoading} style={{ padding: 0, marginTop: 4 }}>
                            Refresh
                        </Button>
                    </Card>
                </Col>
            </Row>

            {/* Stats freshness */}
            {bulkStats && (
                <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                        Stats last updated: {statsAgeLabel}
                        {bulkStats.stale && ' (stale — refreshing in background)'}
                        {bulkStats.refreshing && <SyncOutlined spin style={{ marginLeft: 6 }} />}
                    </Text>
                </div>
            )}

            {/* Mailbox Table */}
            <Table
                dataSource={mergedMailboxes}
                columns={columns}
                rowKey="email"
                loading={isLoading}
                size="middle"
                pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `${total} mailboxes` }}
            />

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
        </div>
    );
}
