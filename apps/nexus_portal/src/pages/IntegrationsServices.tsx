import { Table, Button, Modal, Form, Input, InputNumber, Typography, Space, Tag, Card, message, Tooltip, Row, Col, Select, Drawer, Switch, Badge, Alert, Popconfirm, Divider } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState, useEffect, useRef } from 'react';
import {
    PlusOutlined, ReloadOutlined, ApiOutlined,
    DeleteOutlined, EditOutlined, KeyOutlined, CopyOutlined,
    CheckCircleOutlined, ClockCircleOutlined,
    SafetyCertificateOutlined, ThunderboltOutlined, EyeOutlined,
    StopOutlined, LockOutlined, UnlockOutlined,
} from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer } from '../theme';

const { Title, Text } = Typography;

// ─── Constants ───────────────────────────────────────────────────────────────

const RESOURCE_TYPES = [
    { value: 'secrets', label: 'Secrets' },
    { value: 'storage', label: 'Storage' },
    { value: 'llm', label: 'LLM' },
    { value: 'kb', label: 'Knowledge Base' },
    { value: 'servers', label: 'Servers' },
    { value: 'email', label: 'Email' },
    { value: 'dns', label: 'DNS' },
    { value: 'carriers', label: 'Carrier Inventory' },
];

const ACTION_OPTIONS: Record<string, string[]> = {
    secrets: ['read', 'list', 'write', 'rotate'],
    storage: ['read', 'write', 'delete', 'list'],
    llm: ['query', 'list'],
    kb: ['read', 'search', 'ingest'],
    servers: ['create', 'start', 'stop', 'delete', 'list'],
    email: ['create', 'delete', 'list', 'manage'],
    dns: ['add', 'remove', 'list', 'update'],
    carriers: ['add_did', 'remove_did', 'update_e911', 'manage_ip', 'list'],
};

// ─── Interfaces ──────────────────────────────────────────────────────────────

interface ServiceIntegration {
    id: string;
    name: string;
    service_id: string;
    api_key_prefix: string;
    description: string | null;
    permissions: string[];
    alias_pattern: string;
    rate_limit_rpm: number | null;
    daily_request_limit: number | null;
    is_active: boolean;
    last_seen_at: string | null;
    created_at: string;
    requests_24h: number;
    requests_30d: number;
    api_key?: string;
}

interface PermissionRule {
    id: string;
    service_integration_id: string;
    resource_type: string;
    resource_pattern: string;
    actions: string[];
    rate_limit_rpm: number | null;
    daily_limit: number | null;
    is_active: boolean;
    created_at: string | null;
}

interface UsageStats {
    service_id: string;
    requests_today: number;
    requests_7d: number;
    requests_30d: number;
    recent_requests: any[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatTimeAgo(isoStr: string | null): string {
    if (!isoStr) return 'Never';
    const diff = Date.now() - new Date(isoStr).getTime();
    if (diff < 60_000) return 'Just now';
    if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h ago`;
    return `${Math.floor(diff / 86400_000)}d ago`;
}

function isOnline(lastSeen: string | null): boolean {
    if (!lastSeen) return false;
    return Date.now() - new Date(lastSeen).getTime() < 300_000;
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function IntegrationsServices() {
    const queryClient = useQueryClient();
    const { mode } = useThemeStore();
    const t = getTokens(mode);
    const [addOpen, setAddOpen] = useState(false);
    const [addForm] = Form.useForm();
    const [editTarget, setEditTarget] = useState<ServiceIntegration | null>(null);
    const [editForm] = Form.useForm();
    const [newApiKey, setNewApiKey] = useState<string | null>(null);
    const [detailService, setDetailService] = useState<ServiceIntegration | null>(null);
    const [ruleFormOpen, setRuleFormOpen] = useState(false);
    const [editingRule, setEditingRule] = useState<PermissionRule | null>(null);
    const [ruleForm] = Form.useForm();
    const [selectedResourceType, setSelectedResourceType] = useState<string>('secrets');
    const [revealOpen, setRevealOpen] = useState(false);
    const [revealForm] = Form.useForm();
    const [revealedKey, setRevealedKey] = useState<string | null>(null);
    const [revealCountdown, setRevealCountdown] = useState(0);
    const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Auto-hide revealed key after countdown
    const startCountdown = (seconds: number) => {
        setRevealCountdown(seconds);
        if (countdownRef.current) clearInterval(countdownRef.current);
        countdownRef.current = setInterval(() => {
            setRevealCountdown(prev => {
                if (prev <= 1) {
                    if (countdownRef.current) clearInterval(countdownRef.current);
                    setRevealedKey(null);
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);
    };

    useEffect(() => {
        return () => { if (countdownRef.current) clearInterval(countdownRef.current); };
    }, []);

    // ── Queries ──────────────────────────────────────────────────────────────

    const { data: services, isLoading, refetch } = useQuery<ServiceIntegration[]>({
        queryKey: ['service_integrations'],
        queryFn: async () => (await apiClient.get('/portal/service-integrations')).data,
        refetchInterval: 30000,
    });

    const { data: usageData } = useQuery<UsageStats>({
        queryKey: ['service_usage', detailService?.service_id],
        queryFn: async () => (await apiClient.get(`/portal/service-integrations/${detailService!.service_id}/usage`)).data,
        enabled: !!detailService,
    });

    const { data: rules, refetch: refetchRules } = useQuery<PermissionRule[]>({
        queryKey: ['service_rules', detailService?.service_id],
        queryFn: async () => (await apiClient.get(`/portal/service-integrations/${detailService!.service_id}/rules`)).data,
        enabled: !!detailService,
    });

    // ── Mutations ────────────────────────────────────────────────────────────

    const createMutation = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/portal/service-integrations', values)).data,
        onSuccess: (data) => {
            setNewApiKey(data.api_key);
            message.success('Service registered');
            queryClient.invalidateQueries({ queryKey: ['service_integrations'] });
            addForm.resetFields();
            setAddOpen(false);
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed to create'),
    });

    const updateMutation = useMutation({
        mutationFn: async ({ id, values }: { id: string; values: any }) =>
            (await apiClient.patch(`/portal/service-integrations/${id}`, values)).data,
        onSuccess: () => {
            message.success('Service updated');
            queryClient.invalidateQueries({ queryKey: ['service_integrations'] });
            setEditTarget(null);
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Update failed'),
    });

    const deleteMutation = useMutation({
        mutationFn: async (id: string) => await apiClient.delete(`/portal/service-integrations/${id}`),
        onSuccess: () => {
            message.success('Service revoked');
            queryClient.invalidateQueries({ queryKey: ['service_integrations'] });
            setDetailService(null);
        },
    });

    const regenMutation = useMutation({
        mutationFn: async (id: string) => (await apiClient.post(`/portal/service-integrations/${id}/regenerate-key`)).data,
        onSuccess: (data) => {
            setNewApiKey(data.api_key);
            message.success('API key regenerated');
            queryClient.invalidateQueries({ queryKey: ['service_integrations'] });
        },
    });

    // Rule mutations
    const createRuleMutation = useMutation({
        mutationFn: async (values: any) =>
            (await apiClient.post(`/portal/service-integrations/${detailService!.service_id}/rules`, values)).data,
        onSuccess: () => {
            message.success('Rule added');
            refetchRules();
            setRuleFormOpen(false);
            setEditingRule(null);
            ruleForm.resetFields();
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    const updateRuleMutation = useMutation({
        mutationFn: async ({ ruleId, values }: { ruleId: string; values: any }) =>
            (await apiClient.patch(`/portal/service-integrations/${detailService!.service_id}/rules/${ruleId}`, values)).data,
        onSuccess: () => {
            message.success('Rule updated');
            refetchRules();
            setRuleFormOpen(false);
            setEditingRule(null);
            ruleForm.resetFields();
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    const deleteRuleMutation = useMutation({
        mutationFn: async (ruleId: string) =>
            await apiClient.delete(`/portal/service-integrations/${detailService!.service_id}/rules/${ruleId}`),
        onSuccess: () => {
            message.success('Rule deleted');
            refetchRules();
        },
    });

    const revealMutation = useMutation({
        mutationFn: async (values: { password: string; reason: string }) =>
            (await apiClient.post(`/portal/service-integrations/${detailService!.service_id}/reveal-key`, values)).data,
        onSuccess: (data) => {
            setRevealedKey(data.api_key);
            setRevealOpen(false);
            revealForm.resetFields();
            startCountdown(120);
            message.success('Key revealed — auto-hides in 120s');
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Reveal failed'),
    });

    const toggleRuleMutation = useMutation({
        mutationFn: async ({ ruleId, active }: { ruleId: string; active: boolean }) =>
            (await apiClient.patch(`/portal/service-integrations/${detailService!.service_id}/rules/${ruleId}`, { is_active: active })).data,
        onSuccess: () => refetchRules(),
    });

    // ── Handlers ─────────────────────────────────────────────────────────────

    const handleOpenAddRule = () => {
        setEditingRule(null);
        ruleForm.resetFields();
        setSelectedResourceType('secrets');
        setRuleFormOpen(true);
    };

    const handleEditRule = (rule: PermissionRule) => {
        setEditingRule(rule);
        setSelectedResourceType(rule.resource_type);
        ruleForm.setFieldsValue(rule);
        setRuleFormOpen(true);
    };

    const handleSubmitRule = () => {
        ruleForm.validateFields().then(v => {
            if (editingRule) {
                updateRuleMutation.mutate({ ruleId: editingRule.id, values: v });
            } else {
                createRuleMutation.mutate(v);
            }
        });
    };

    // ── Stats Cards ──────────────────────────────────────────────────────────

    const totalServices = services?.length || 0;
    const activeServices = services?.filter(s => s.is_active).length || 0;
    const onlineServices = services?.filter(s => isOnline(s.last_seen_at)).length || 0;
    const totalRequests24h = services?.reduce((sum, s) => sum + s.requests_24h, 0) || 0;

    const statCards = [
        { label: 'Total Services', value: totalServices, icon: <ApiOutlined />, color: '#4169E1' },
        { label: 'Active', value: activeServices, icon: <CheckCircleOutlined />, color: '#00C853' },
        { label: 'Online Now', value: onlineServices, icon: <ThunderboltOutlined />, color: '#00CED1' },
        { label: 'Requests (24h)', value: totalRequests24h, icon: <ClockCircleOutlined />, color: '#FF6B35' },
    ];

    // ── Table Columns ────────────────────────────────────────────────────────

    const columns = [
        {
            title: 'Service',
            key: 'name',
            render: (_: any, row: ServiceIntegration) => (
                <Space direction="vertical" size={0}>
                    <Space>
                        <Badge status={isOnline(row.last_seen_at) ? 'success' : row.is_active ? 'default' : 'error'} />
                        <Text strong style={{ color: t.text }}>{row.name}</Text>
                    </Space>
                    <Text type="secondary" style={{ fontSize: 11 }}>{row.service_id}</Text>
                </Space>
            ),
        },
        {
            title: 'Status',
            key: 'status',
            width: 100,
            render: (_: any, row: ServiceIntegration) => (
                row.is_active
                    ? <Tag color={isOnline(row.last_seen_at) ? 'green' : 'default'}>{isOnline(row.last_seen_at) ? 'Online' : 'Idle'}</Tag>
                    : <Tag color="red">Disabled</Tag>
            ),
        },
        {
            title: 'API Key',
            key: 'key',
            width: 120,
            render: (_: any, row: ServiceIntegration) => (
                <Text code style={{ fontSize: 11, color: t.muted }}>{row.api_key_prefix}…</Text>
            ),
        },
        {
            title: 'Requests (24h)',
            dataIndex: 'requests_24h',
            width: 120,
            render: (v: number) => <Text style={{ color: t.text, fontWeight: 600 }}>{v.toLocaleString()}</Text>,
        },
        {
            title: 'Last Seen',
            key: 'last_seen',
            width: 120,
            render: (_: any, row: ServiceIntegration) => (
                <Text type="secondary" style={{ fontSize: 12 }}>{formatTimeAgo(row.last_seen_at)}</Text>
            ),
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 180,
            render: (_: any, row: ServiceIntegration) => (
                <Space size="small">
                    <Tooltip title="View Details">
                        <Button size="small" type="text" icon={<EyeOutlined />}
                            onClick={() => setDetailService(row)} />
                    </Tooltip>
                    <Tooltip title="Edit">
                        <Button size="small" type="text" icon={<EditOutlined />}
                            onClick={() => { setEditTarget(row); editForm.setFieldsValue(row); }} />
                    </Tooltip>
                    <Tooltip title="Regenerate Key">
                        <Button size="small" type="text" icon={<KeyOutlined />}
                            onClick={() => Modal.confirm({
                                title: 'Regenerate API Key?',
                                content: 'The old key will be invalidated immediately.',
                                onOk: () => regenMutation.mutate(row.service_id),
                            })} />
                    </Tooltip>
                    <Tooltip title="Revoke">
                        <Button size="small" type="text" danger icon={<DeleteOutlined />}
                            onClick={() => Modal.confirm({
                                title: `Revoke ${row.name}?`,
                                content: 'This will delete the service, all permission rules, and usage logs.',
                                okText: 'Revoke',
                                okButtonProps: { danger: true },
                                onOk: () => deleteMutation.mutate(row.service_id),
                            })} />
                    </Tooltip>
                </Space>
            ),
        },
    ];

    // ── Rule Columns (for drawer) ────────────────────────────────────────────

    const ruleColumns = [
        {
            title: 'Resource',
            key: 'resource',
            render: (_: any, rule: PermissionRule) => (
                <Space direction="vertical" size={0}>
                    <Tag color="blue" style={{ fontSize: 11 }}>{rule.resource_type}</Tag>
                    <Text code style={{ fontSize: 10 }}>{rule.resource_pattern}</Text>
                </Space>
            ),
        },
        {
            title: 'Actions',
            key: 'actions',
            render: (_: any, rule: PermissionRule) => (
                <Space size={2} wrap>{rule.actions?.map(a => <Tag key={a} style={{ fontSize: 10 }}>{a}</Tag>)}</Space>
            ),
        },
        {
            title: 'Limits',
            key: 'limits',
            width: 90,
            render: (_: any, rule: PermissionRule) => (
                <Space direction="vertical" size={0}>
                    <Text style={{ fontSize: 10, color: t.muted }}>{rule.rate_limit_rpm ? `${rule.rate_limit_rpm}/min` : '∞ rpm'}</Text>
                    <Text style={{ fontSize: 10, color: t.muted }}>{rule.daily_limit ? `${rule.daily_limit}/day` : '∞ day'}</Text>
                </Space>
            ),
        },
        {
            title: '',
            key: 'ops',
            width: 90,
            render: (_: any, rule: PermissionRule) => (
                <Space size={2}>
                    <Tooltip title={rule.is_active ? 'Enabled' : 'Disabled'}>
                        <Switch size="small" checked={rule.is_active}
                            onChange={(checked) => toggleRuleMutation.mutate({ ruleId: rule.id, active: checked })} />
                    </Tooltip>
                    <Button size="small" type="text" icon={<EditOutlined style={{ fontSize: 12 }} />}
                        onClick={() => handleEditRule(rule)} />
                    <Popconfirm title="Delete this rule?" onConfirm={() => deleteRuleMutation.mutate(rule.id)}>
                        <Button size="small" type="text" danger icon={<DeleteOutlined style={{ fontSize: 12 }} />} />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div style={pageContainer(t)}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: t.text }}>
                        <ApiOutlined style={{ marginRight: 10, color: '#4169E1' }} />
                        Service Integrations
                    </Title>
                    <Text type="secondary" style={{ fontSize: 13 }}>
                        Manage external services that connect to Nexus via API keys
                    </Text>
                </div>
                <Space>
                    <Button icon={<ReloadOutlined />} onClick={() => refetch()}>Refresh</Button>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
                        Register Service
                    </Button>
                </Space>
            </div>

            {/* Stats Cards */}
            <Row gutter={16} style={{ marginBottom: 24 }}>
                {statCards.map((sc) => (
                    <Col span={6} key={sc.label}>
                        <Card size="small" style={{ background: t.cardBg, border: `1px solid ${t.border}`, borderRadius: 10 }}>
                            <Space>
                                <div style={{
                                    width: 40, height: 40, borderRadius: 10,
                                    background: `${sc.color}18`, display: 'flex',
                                    alignItems: 'center', justifyContent: 'center',
                                    fontSize: 18, color: sc.color,
                                }}>
                                    {sc.icon}
                                </div>
                                <div>
                                    <Text type="secondary" style={{ fontSize: 11 }}>{sc.label}</Text>
                                    <div style={{ fontSize: 22, fontWeight: 700, color: t.text }}>{sc.value}</div>
                                </div>
                            </Space>
                        </Card>
                    </Col>
                ))}
            </Row>

            {/* Table */}
            <Card style={{ background: t.cardBg, border: `1px solid ${t.border}`, borderRadius: 10 }}>
                <Table
                    dataSource={services || []}
                    columns={columns}
                    loading={isLoading}
                    rowKey="id"
                    pagination={false}
                    size="middle"
                />
            </Card>

            {/* ── API Key Reveal Modal ──────────────────────────────────────── */}
            <Modal
                title={<><SafetyCertificateOutlined style={{ color: '#00CED1', marginRight: 8 }} />Your New API Key</>}
                open={!!newApiKey}
                onCancel={() => setNewApiKey(null)}
                footer={<Button type="primary" onClick={() => setNewApiKey(null)}>Done</Button>}
                width={500}
            >
                <Alert
                    message="Copy this key now — it will not be shown again."
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                />
                <Input.TextArea
                    value={newApiKey || ''}
                    readOnly
                    rows={2}
                    style={{ fontFamily: 'monospace', fontSize: 13 }}
                />
                <Button
                    icon={<CopyOutlined />}
                    style={{ marginTop: 8 }}
                    onClick={() => {
                        navigator.clipboard.writeText(newApiKey || '');
                        message.success('API key copied to clipboard');
                    }}
                >
                    Copy to Clipboard
                </Button>
            </Modal>

            {/* ── Add Service Modal (simplified — rules added after) ─────── */}
            <Modal
                title={<><PlusOutlined style={{ color: '#4169E1', marginRight: 8 }} />Register New Service</>}
                open={addOpen}
                onCancel={() => { setAddOpen(false); addForm.resetFields(); }}
                onOk={() => addForm.validateFields().then(v => createMutation.mutate(v))}
                okText="Register"
                confirmLoading={createMutation.isPending}
                width={520}
            >
                <Form form={addForm} layout="vertical" style={{ marginTop: 16 }}>
                    <Form.Item name="name" label="Display Name" rules={[{ required: true }]}>
                        <Input placeholder="e.g. VibePrompter" />
                    </Form.Item>
                    <Form.Item name="service_id" label="Service ID" rules={[{ required: true, pattern: /^[a-z0-9_-]+$/, message: 'Lowercase alphanumeric, hyphens, underscores only' }]}
                        extra="Machine-readable ID used in headers (e.g. vibeprompter)">
                        <Input placeholder="e.g. vibeprompter" />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                        <Input.TextArea rows={2} placeholder="What does this service do?" />
                    </Form.Item>
                    <Alert
                        message="After registering, open the service details to add permission rules that control what resources this service can access."
                        type="info"
                        showIcon
                        style={{ marginBottom: 0 }}
                    />
                </Form>
            </Modal>

            {/* ── Edit Service Modal ───────────────────────────────────────── */}
            <Modal
                title={<><EditOutlined style={{ color: '#4169E1', marginRight: 8 }} />Edit Service</>}
                open={!!editTarget}
                onCancel={() => setEditTarget(null)}
                onOk={() => editForm.validateFields().then(v => updateMutation.mutate({ id: editTarget!.service_id, values: v }))}
                okText="Save"
                confirmLoading={updateMutation.isPending}
                width={520}
            >
                <Form form={editForm} layout="vertical" style={{ marginTop: 16 }}>
                    <Form.Item name="name" label="Display Name" rules={[{ required: true }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                        <Input.TextArea rows={2} />
                    </Form.Item>
                    <Form.Item name="is_active" label="Active" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>

            {/* ── Detail Drawer ────────────────────────────────────────────── */}
            <Drawer
                title={detailService?.name || 'Service Details'}
                open={!!detailService}
                onClose={() => { setDetailService(null); setRuleFormOpen(false); setEditingRule(null); setRevealedKey(null); setRevealOpen(false); if (countdownRef.current) clearInterval(countdownRef.current); }}
                width={560}
            >
                {detailService && (
                    <Space direction="vertical" style={{ width: '100%' }} size="large">
                        {/* Info Card */}
                        <Card size="small" style={{ background: t.cardBg, border: `1px solid ${t.border}` }}>
                            <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                <div><Text type="secondary">Service ID:</Text> <Text code>{detailService.service_id}</Text></div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <Text type="secondary">API Key:</Text> <Text code>{detailService.api_key_prefix}…</Text>
                                    <Tooltip title="Break-glass: reveal full key">
                                        <Button size="small" type="text" icon={<UnlockOutlined />}
                                            onClick={() => { setRevealedKey(null); setRevealOpen(true); }} />
                                    </Tooltip>
                                </div>
                                {revealedKey && (
                                    <div style={{ marginTop: 8, padding: 8, background: '#1a1a2e', borderRadius: 6, border: '1px solid #ff6b35' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                            <Text style={{ color: '#ff6b35', fontSize: 11, fontWeight: 600 }}>
                                                <LockOutlined /> REVEALED — auto-hides in {revealCountdown}s
                                            </Text>
                                            <Button size="small" type="text" icon={<CopyOutlined />}
                                                onClick={() => { navigator.clipboard.writeText(revealedKey); message.success('Copied'); }} />
                                        </div>
                                        <Input.TextArea value={revealedKey} readOnly rows={2}
                                            style={{ fontFamily: 'monospace', fontSize: 12, background: '#0d0d1a', border: 'none', color: '#00ff88' }} />
                                    </div>
                                )}
                                <div><Text type="secondary">Status:</Text> {detailService.is_active ? <Tag color="green">Active</Tag> : <Tag color="red">Disabled</Tag>}</div>
                                <div><Text type="secondary">Connection:</Text> {isOnline(detailService.last_seen_at) ? <Tag color="green">Online</Tag> : <Tag color="default">Offline</Tag>}</div>
                                <div><Text type="secondary">Last Seen:</Text> <Text>{formatTimeAgo(detailService.last_seen_at)}</Text></div>
                                <div><Text type="secondary">Created:</Text> <Text>{new Date(detailService.created_at).toLocaleDateString()}</Text></div>
                            </Space>
                        </Card>

                        {/* Permission Rules Card */}
                        <Card
                            size="small"
                            title={<><SafetyCertificateOutlined style={{ color: '#4169E1', marginRight: 6 }} />Permission Rules</>}
                            extra={<Button size="small" type="primary" icon={<PlusOutlined />} onClick={handleOpenAddRule}>Add Rule</Button>}
                            style={{ background: t.cardBg, border: `1px solid ${t.border}` }}
                        >
                            {(!rules || rules.length === 0) ? (
                                <div style={{ textAlign: 'center', padding: '16px 0' }}>
                                    <StopOutlined style={{ fontSize: 24, color: t.muted, marginBottom: 8 }} />
                                    <div><Text type="secondary" style={{ fontSize: 12 }}>No permission rules — this service cannot access any resources.</Text></div>
                                    <Button size="small" type="link" onClick={handleOpenAddRule}>Add your first rule</Button>
                                </div>
                            ) : (
                                <Table
                                    dataSource={rules}
                                    columns={ruleColumns}
                                    rowKey="id"
                                    pagination={false}
                                    size="small"
                                    style={{ fontSize: 12 }}
                                />
                            )}

                            {/* Inline Rule Form */}
                            {ruleFormOpen && (
                                <>
                                    <Divider style={{ margin: '12px 0' }} />
                                    <div style={{ padding: '8px 0' }}>
                                        <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                                            {editingRule ? 'Edit Rule' : 'New Permission Rule'}
                                        </Text>
                                        <Form form={ruleForm} layout="vertical" size="small">
                                            <Row gutter={8}>
                                                <Col span={10}>
                                                    <Form.Item name="resource_type" label="Resource Type" rules={[{ required: true }]}>
                                                        <Select onChange={(v) => { setSelectedResourceType(v); ruleForm.setFieldValue('actions', ['read']); }}>
                                                            {RESOURCE_TYPES.map(rt => <Select.Option key={rt.value} value={rt.value}>{rt.label}</Select.Option>)}
                                                        </Select>
                                                    </Form.Item>
                                                </Col>
                                                <Col span={14}>
                                                    <Form.Item name="resource_pattern" label="Resource Pattern" initialValue="*"
                                                        extra={<span style={{ fontSize: 10 }}>Glob: openai.*, storage-1, *</span>}>
                                                        <Input placeholder="*" />
                                                    </Form.Item>
                                                </Col>
                                            </Row>
                                            <Form.Item name="actions" label="Allowed Actions" initialValue={['read']} rules={[{ required: true }]}>
                                                <Select mode="multiple">
                                                    {(ACTION_OPTIONS[selectedResourceType] || ['read']).map(a =>
                                                        <Select.Option key={a} value={a}>{a}</Select.Option>)}
                                                </Select>
                                            </Form.Item>
                                            <Row gutter={8}>
                                                <Col span={12}>
                                                    <Form.Item name="rate_limit_rpm" label="RPM Limit">
                                                        <InputNumber min={1} style={{ width: '100%' }} placeholder="Unlimited" />
                                                    </Form.Item>
                                                </Col>
                                                <Col span={12}>
                                                    <Form.Item name="daily_limit" label="Daily Limit">
                                                        <InputNumber min={1} style={{ width: '100%' }} placeholder="Unlimited" />
                                                    </Form.Item>
                                                </Col>
                                            </Row>
                                            <Space>
                                                <Button type="primary" size="small" onClick={handleSubmitRule}
                                                    loading={createRuleMutation.isPending || updateRuleMutation.isPending}>
                                                    {editingRule ? 'Update' : 'Add Rule'}
                                                </Button>
                                                <Button size="small" onClick={() => { setRuleFormOpen(false); setEditingRule(null); ruleForm.resetFields(); }}>
                                                    Cancel
                                                </Button>
                                            </Space>
                                        </Form>
                                    </div>
                                </>
                            )}
                        </Card>

                        {/* Usage Stats */}
                        {usageData && (
                            <Card size="small" title="Usage Stats" style={{ background: t.cardBg, border: `1px solid ${t.border}` }}>
                                <Row gutter={16}>
                                    <Col span={8}>
                                        <div style={{ textAlign: 'center' }}>
                                            <div style={{ fontSize: 20, fontWeight: 700, color: t.text }}>{usageData.requests_today}</div>
                                            <Text type="secondary" style={{ fontSize: 11 }}>Today</Text>
                                        </div>
                                    </Col>
                                    <Col span={8}>
                                        <div style={{ textAlign: 'center' }}>
                                            <div style={{ fontSize: 20, fontWeight: 700, color: t.text }}>{usageData.requests_7d}</div>
                                            <Text type="secondary" style={{ fontSize: 11 }}>7 Days</Text>
                                        </div>
                                    </Col>
                                    <Col span={8}>
                                        <div style={{ textAlign: 'center' }}>
                                            <div style={{ fontSize: 20, fontWeight: 700, color: t.text }}>{usageData.requests_30d}</div>
                                            <Text type="secondary" style={{ fontSize: 11 }}>30 Days</Text>
                                        </div>
                                    </Col>
                                </Row>
                                {usageData.recent_requests.length > 0 && (
                                    <>
                                        <div style={{ borderTop: `1px solid ${t.border}`, marginTop: 16, paddingTop: 12 }}>
                                            <Text strong style={{ fontSize: 12 }}>Recent Requests</Text>
                                        </div>
                                        {usageData.recent_requests.slice(0, 10).map((req: any) => (
                                            <div key={req.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 11 }}>
                                                <Text code style={{ fontSize: 10 }}>{req.method} {req.endpoint}</Text>
                                                <Text type="secondary" style={{ fontSize: 10 }}>{formatTimeAgo(req.ts)}</Text>
                                            </div>
                                        ))}
                                    </>
                                )}
                            </Card>
                        )}
                    </Space>
                )}
            </Drawer>

            {/* ── Break-Glass Reveal Modal ────────────────────────────────── */}
            <Modal
                title={<><LockOutlined style={{ color: '#ff6b35', marginRight: 8 }} />Break-Glass: Reveal API Key</>}
                open={revealOpen}
                onCancel={() => { setRevealOpen(false); revealForm.resetFields(); }}
                onOk={() => revealForm.validateFields().then(v => revealMutation.mutate(v))}
                okText="Reveal Key"
                okButtonProps={{ danger: true }}
                confirmLoading={revealMutation.isPending}
                width={460}
            >
                <Alert
                    message="This action is logged and auditable."
                    description="You must provide your password and a reason. The key will auto-hide after 120 seconds."
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                />
                <Form form={revealForm} layout="vertical">
                    <Form.Item name="password" label="Your Password" rules={[{ required: true, message: 'Password required' }]}>
                        <Input.Password prefix={<LockOutlined />} placeholder="Re-enter your password" />
                    </Form.Item>
                    <Form.Item name="reason" label="Reason" rules={[{ required: true, min: 3, message: 'Provide a reason (min 3 chars)' }]}>
                        <Input.TextArea rows={2} placeholder="e.g. Migrating to new VibePrompter instance" />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
