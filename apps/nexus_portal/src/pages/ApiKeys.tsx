/**
 * API Keys Management — Settings → Security
 *
 * CRUD for API keys with copy-to-clipboard, rotate, toggle, and delete.
 * Admin-only page with 3D hover stat cards.
 */
import { useMemo, useState } from 'react';
import {
    Typography, Table, Button, Tag, Space, Modal, Form, Input, Select,
    Popconfirm, message, Row, Col, Statistic, Tooltip,
} from 'antd';
import {
    KeyOutlined, PlusOutlined, SyncOutlined, DeleteOutlined,
    CopyOutlined, CheckCircleOutlined, StopOutlined,
    LockOutlined, UnlockOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';
import { apiClient } from '../api/client';
import { TiltCard } from '../components/TiltCard';

const { Title, Text } = Typography;

interface ApiKeyRecord {
    id: number;
    owner_type: string;
    owner_id: number;
    name: string;
    is_active: boolean;
    last_used_at: string | null;
    created_at: string;
    key?: string;
}

export default function ApiKeys() {
    const { mode } = useThemeStore();
    const t = getTokens(mode);
    const qc = useQueryClient();
    const [createOpen, setCreateOpen] = useState(false);
    const [newRawKey, setNewRawKey] = useState<string | null>(null);
    const [rotatedKey, setRotatedKey] = useState<{ id: number; key: string } | null>(null);
    const [form] = Form.useForm();

    // ── Queries ──────────────────────────────────────────────────────
    const { data: keys = [], isLoading } = useQuery<ApiKeyRecord[]>({
        queryKey: ['api-keys'],
        queryFn: () => apiClient.get('/auth/api-keys').then(r => r.data),
    });

    // ── Mutations ────────────────────────────────────────────────────
    const createMut = useMutation({
        mutationFn: (body: { owner_type: string; owner_id: number; name: string }) =>
            apiClient.post('/auth/api-keys', body),
        onSuccess: (res) => {
            setNewRawKey(res.data.key);
            qc.invalidateQueries({ queryKey: ['api-keys'] });
            message.success('API key created');
            form.resetFields();
            setCreateOpen(false);
        },
    });

    const rotateMut = useMutation({
        mutationFn: (id: number) => apiClient.post(`/auth/api-keys/${id}/rotate`),
        onSuccess: (res) => {
            setRotatedKey({ id: res.data.id, key: res.data.raw_key });
            qc.invalidateQueries({ queryKey: ['api-keys'] });
            message.success('API key rotated');
        },
    });

    const toggleMut = useMutation({
        mutationFn: (id: number) => apiClient.patch(`/auth/api-keys/${id}`),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['api-keys'] });
            message.success('API key status updated');
        },
    });

    const deleteMut = useMutation({
        mutationFn: (id: number) => apiClient.delete(`/auth/api-keys/${id}`),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['api-keys'] });
            message.success('API key permanently deleted');
        },
    });

    // ── Stats ────────────────────────────────────────────────────────
    const totalKeys = keys.length;
    const activeKeys = keys.filter(k => k.is_active).length;
    const recentlyUsed = useMemo(() => keys.filter(k => {
        if (!k.last_used_at) return false;
        // eslint-disable-next-line react-hooks/purity
        const diff = Date.now() - new Date(k.last_used_at).getTime();
        return diff < 24 * 60 * 60 * 1000; // 24h
    }).length, [keys]);

    // ── Copy helper ──────────────────────────────────────────────────
    const copyKey = (key: string) => {
        navigator.clipboard.writeText(key);
        message.success('Copied to clipboard');
    };

    // ── Table columns ────────────────────────────────────────────────
    const columns = [
        {
            title: 'Name', dataIndex: 'name', key: 'name',
            render: (name: string, rec: ApiKeyRecord) => (
                <Space>
                    <KeyOutlined style={{ color: rec.is_active ? t.accent : t.muted }} />
                    <Text style={{ color: t.text, fontWeight: 600 }}>{name}</Text>
                </Space>
            ),
        },
        {
            title: 'Owner', key: 'owner',
            render: (_: unknown, rec: ApiKeyRecord) => (
                <Tag color={rec.owner_type === 'agent' ? 'blue' : 'purple'}>
                    {rec.owner_type}:{rec.owner_id}
                </Tag>
            ),
        },
        {
            title: 'Status', key: 'status',
            render: (_: unknown, rec: ApiKeyRecord) => (
                <Tag
                    icon={rec.is_active ? <CheckCircleOutlined /> : <StopOutlined />}
                    color={rec.is_active ? 'success' : 'error'}
                >
                    {rec.is_active ? 'Active' : 'Disabled'}
                </Tag>
            ),
        },
        {
            title: 'Last Used', dataIndex: 'last_used_at', key: 'last_used',
            render: (v: string | null) => v
                ? <Text style={{ color: t.muted, fontSize: 12 }}>{new Date(v).toLocaleString()}</Text>
                : <Text style={{ color: t.muted, fontSize: 12, fontStyle: 'italic' }}>Never</Text>,
        },
        {
            title: 'Created', dataIndex: 'created_at', key: 'created',
            render: (v: string) =>
                <Text style={{ color: t.muted, fontSize: 12 }}>{new Date(v).toLocaleDateString()}</Text>,
        },
        {
            title: 'Actions', key: 'actions', width: 200,
            render: (_: unknown, rec: ApiKeyRecord) => (
                <Space size={4}>
                    <Tooltip title={rec.is_active ? 'Disable' : 'Enable'}>
                        <Button
                            type="text" size="small"
                            icon={rec.is_active ? <LockOutlined /> : <UnlockOutlined />}
                            onClick={() => toggleMut.mutate(rec.id)}
                            style={{ color: rec.is_active ? t.orange : t.green }}
                        />
                    </Tooltip>
                    <Tooltip title="Rotate">
                        <Popconfirm
                            title="Rotate this key?"
                            description="The current key will stop working immediately."
                            onConfirm={() => rotateMut.mutate(rec.id)}
                        >
                            <Button type="text" size="small" icon={<SyncOutlined />} style={{ color: t.accent }} />
                        </Popconfirm>
                    </Tooltip>
                    <Tooltip title="Delete permanently">
                        <Popconfirm
                            title="Delete this API key?"
                            description="This cannot be undone."
                            onConfirm={() => deleteMut.mutate(rec.id)}
                        >
                            <Button type="text" size="small" icon={<DeleteOutlined />} style={{ color: t.red }} />
                        </Popconfirm>
                    </Tooltip>
                </Space>
            ),
        },
    ];

    return (
        <div style={pageContainer(t)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={3} style={{ color: t.text, margin: 0 }}>
                        <KeyOutlined style={{ marginRight: 10 }} />
                        API Keys
                    </Title>
                    <Text style={{ color: t.muted }}>
                        Manage programmatic access credentials for agents and external services
                    </Text>
                </div>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                    Create Key
                </Button>
            </div>

            {/* Stats */}
            <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={8}>
                    <TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.accent } as React.CSSProperties}>
                        <Statistic title={<Text style={{ color: t.muted }}>Total Keys</Text>} value={totalKeys} prefix={<KeyOutlined />} valueStyle={{ color: t.text }} />
                    </TiltCard>
                </Col>
                <Col span={8}>
                    <TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.green } as React.CSSProperties}>
                        <Statistic title={<Text style={{ color: t.muted }}>Active</Text>} value={activeKeys} prefix={<CheckCircleOutlined />} valueStyle={{ color: t.green }} />
                    </TiltCard>
                </Col>
                <Col span={8}>
                    <TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.orange } as React.CSSProperties}>
                        <Statistic title={<Text style={{ color: t.muted }}>Used (24h)</Text>} value={recentlyUsed} prefix={<ClockCircleOutlined />} valueStyle={{ color: t.orange }} />
                    </TiltCard>
                </Col>
            </Row>

            {/* Table */}
            <div style={cardStyle(t)}>
                <style>{tableStyleOverrides(t, 'nx-table')}</style>
                <Table
                    rowKey="id"
                    dataSource={keys}
                    columns={columns}
                    loading={isLoading}
                    pagination={{ pageSize: 15, showSizeChanger: false }}
                    size="small"
                />
            </div>

            {/* ── Create Modal ── */}
            <Modal
                title="Create API Key"
                open={createOpen}
                onCancel={() => { setCreateOpen(false); form.resetFields(); }}
                onOk={() => form.submit()}
                confirmLoading={createMut.isPending}
            >
                <Form form={form} layout="vertical" onFinish={(v) => createMut.mutate(v)}>
                    <Form.Item name="name" label="Key Name" rules={[{ required: true }]}>
                        <Input placeholder="e.g. monitoring-agent-prod" />
                    </Form.Item>
                    <Form.Item name="owner_type" label="Owner Type" rules={[{ required: true }]} initialValue="agent">
                        <Select options={[{ value: 'agent', label: 'Agent' }, { value: 'user', label: 'User' }]} />
                    </Form.Item>
                    <Form.Item name="owner_id" label="Owner ID" rules={[{ required: true }]}>
                        <Input type="number" placeholder="e.g. 1" />
                    </Form.Item>
                </Form>
            </Modal>

            {/* ── New Key Display Modal ── */}
            <Modal
                title="🔑 API Key Created"
                open={!!newRawKey}
                onCancel={() => setNewRawKey(null)}
                footer={[
                    <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={() => copyKey(newRawKey!)}>
                        Copy Key
                    </Button>,
                    <Button key="close" onClick={() => setNewRawKey(null)}>Done</Button>,
                ]}
            >
                <div style={{
                    background: 'rgba(0,0,0,0.3)', borderRadius: 8, padding: 16,
                    fontFamily: "'SF Mono', 'Fira Code', monospace", fontSize: 13,
                    wordBreak: 'break-all', color: t.green, border: `1px solid ${t.border}`,
                }}>
                    {newRawKey}
                </div>
                <Text type="warning" style={{ display: 'block', marginTop: 12 }}>
                    ⚠️ This key will only be shown once. Copy it now and store it securely.
                </Text>
            </Modal>

            {/* ── Rotated Key Display Modal ── */}
            <Modal
                title="🔄 Key Rotated"
                open={!!rotatedKey}
                onCancel={() => setRotatedKey(null)}
                footer={[
                    <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={() => copyKey(rotatedKey!.key)}>
                        Copy New Key
                    </Button>,
                    <Button key="close" onClick={() => setRotatedKey(null)}>Done</Button>,
                ]}
            >
                <div style={{
                    background: 'rgba(0,0,0,0.3)', borderRadius: 8, padding: 16,
                    fontFamily: "'SF Mono', 'Fira Code', monospace", fontSize: 13,
                    wordBreak: 'break-all', color: t.accent, border: `1px solid ${t.border}`,
                }}>
                    {rotatedKey?.key}
                </div>
                <Text type="warning" style={{ display: 'block', marginTop: 12 }}>
                    ⚠️ The old key has been permanently invalidated. Copy the new key now.
                </Text>
            </Modal>
        </div>
    );
}
