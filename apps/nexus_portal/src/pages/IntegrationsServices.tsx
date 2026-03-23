import { Table, Button, Modal, Form, Input, InputNumber, Typography, Space, Tag, Card, message, Tooltip, Row, Col, Select, Drawer, Switch, Badge, Alert } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';
import {
    PlusOutlined, ReloadOutlined, ApiOutlined,
    DeleteOutlined, EditOutlined, KeyOutlined, CopyOutlined,
    CheckCircleOutlined, ClockCircleOutlined,
    SafetyCertificateOutlined, ThunderboltOutlined, EyeOutlined,
} from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer } from '../theme';

const { Title, Text } = Typography;

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
    api_key?: string; // Only present on create / regenerate
}

interface UsageStats {
    service_id: string;
    requests_today: number;
    requests_7d: number;
    requests_30d: number;
    recent_requests: any[];
}

// ─── Helper ──────────────────────────────────────────────────────────────────

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
    return Date.now() - new Date(lastSeen).getTime() < 300_000; // 5 min
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

    // ── Query ────────────────────────────────────────────────────────────────

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
            title: 'Alias Pattern',
            key: 'alias',
            width: 160,
            render: (_: any, row: ServiceIntegration) => (
                <Text code style={{ fontSize: 11 }}>{row.alias_pattern}</Text>
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
                                content: 'The old key will be invalidated immediately. The service will need to be updated with the new key.',
                                onOk: () => regenMutation.mutate(row.service_id),
                            })} />
                    </Tooltip>
                    <Tooltip title="Revoke">
                        <Button size="small" type="text" danger icon={<DeleteOutlined />}
                            onClick={() => Modal.confirm({
                                title: `Revoke ${row.name}?`,
                                content: 'This will delete the service registration and all usage logs. The service will no longer be able to authenticate.',
                                okText: 'Revoke',
                                okButtonProps: { danger: true },
                                onOk: () => deleteMutation.mutate(row.service_id),
                            })} />
                    </Tooltip>
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

            {/* ── Add Service Modal ────────────────────────────────────────── */}
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
                    <Form.Item name="alias_pattern" label="Secret Alias Pattern" initialValue="*"
                        extra="Glob pattern controlling which secrets this service can access">
                        <Input placeholder="e.g. vibeprompter.*" />
                    </Form.Item>
                    <Form.Item name="permissions" label="Permissions" initialValue={['secrets:read', 'secrets:list']}>
                        <Select mode="tags" placeholder="permissions">
                            <Select.Option value="secrets:read">secrets:read</Select.Option>
                            <Select.Option value="secrets:list">secrets:list</Select.Option>
                            <Select.Option value="secrets:write">secrets:write</Select.Option>
                            <Select.Option value="secrets:rotate">secrets:rotate</Select.Option>
                        </Select>
                    </Form.Item>
                    <Row gutter={16}>
                        <Col span={12}>
                            <Form.Item name="rate_limit_rpm" label="Rate Limit (req/min)">
                                <InputNumber min={1} style={{ width: '100%' }} placeholder="Unlimited" />
                            </Form.Item>
                        </Col>
                        <Col span={12}>
                            <Form.Item name="daily_request_limit" label="Daily Request Limit">
                                <InputNumber min={1} style={{ width: '100%' }} placeholder="Unlimited" />
                            </Form.Item>
                        </Col>
                    </Row>
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
                    <Form.Item name="alias_pattern" label="Secret Alias Pattern">
                        <Input />
                    </Form.Item>
                    <Form.Item name="permissions" label="Permissions">
                        <Select mode="tags" placeholder="permissions">
                            <Select.Option value="secrets:read">secrets:read</Select.Option>
                            <Select.Option value="secrets:list">secrets:list</Select.Option>
                            <Select.Option value="secrets:write">secrets:write</Select.Option>
                            <Select.Option value="secrets:rotate">secrets:rotate</Select.Option>
                        </Select>
                    </Form.Item>
                    <Row gutter={16}>
                        <Col span={12}>
                            <Form.Item name="rate_limit_rpm" label="Rate Limit (req/min)">
                                <InputNumber min={1} style={{ width: '100%' }} placeholder="Unlimited" />
                            </Form.Item>
                        </Col>
                        <Col span={12}>
                            <Form.Item name="daily_request_limit" label="Daily Request Limit">
                                <InputNumber min={1} style={{ width: '100%' }} placeholder="Unlimited" />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Form.Item name="is_active" label="Active" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>

            {/* ── Detail Drawer ────────────────────────────────────────────── */}
            <Drawer
                title={detailService?.name || 'Service Details'}
                open={!!detailService}
                onClose={() => setDetailService(null)}
                width={480}
            >
                {detailService && (
                    <Space direction="vertical" style={{ width: '100%' }} size="large">
                        <Card size="small" style={{ background: t.cardBg, border: `1px solid ${t.border}` }}>
                            <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                <div><Text type="secondary">Service ID:</Text> <Text code>{detailService.service_id}</Text></div>
                                <div><Text type="secondary">API Key:</Text> <Text code>{detailService.api_key_prefix}…</Text></div>
                                <div><Text type="secondary">Status:</Text> {detailService.is_active ? <Tag color="green">Active</Tag> : <Tag color="red">Disabled</Tag>}</div>
                                <div><Text type="secondary">Connection:</Text> {isOnline(detailService.last_seen_at) ? <Tag color="green">Online</Tag> : <Tag color="default">Offline</Tag>}</div>
                                <div><Text type="secondary">Last Seen:</Text> <Text>{formatTimeAgo(detailService.last_seen_at)}</Text></div>
                                <div><Text type="secondary">Created:</Text> <Text>{new Date(detailService.created_at).toLocaleDateString()}</Text></div>
                            </Space>
                        </Card>

                        <Card size="small" title="Permissions & Limits" style={{ background: t.cardBg, border: `1px solid ${t.border}` }}>
                            <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                <div><Text type="secondary">Alias Pattern:</Text> <Text code>{detailService.alias_pattern}</Text></div>
                                <div><Text type="secondary">Permissions:</Text> {detailService.permissions.map(p => <Tag key={p}>{p}</Tag>)}</div>
                                <div><Text type="secondary">Rate Limit:</Text> <Text>{detailService.rate_limit_rpm ? `${detailService.rate_limit_rpm} req/min` : 'Unlimited'}</Text></div>
                                <div><Text type="secondary">Daily Limit:</Text> <Text>{detailService.daily_request_limit ? `${detailService.daily_request_limit} req/day` : 'Unlimited'}</Text></div>
                            </Space>
                        </Card>

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
        </div>
    );
}
