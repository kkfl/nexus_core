/**
 * IP Allowlist — Settings → Security
 *
 * Manage allowed source IPs for API access.
 * Fail-open: when no entries exist, all IPs are allowed.
 */
import { useState } from 'react';
import {
    Typography, Table, Button, Tag, Space, Modal, Form, Input,
    Popconfirm, message, Alert, Tooltip, Row, Col, Statistic,
} from 'antd';
import {
    GlobalOutlined, PlusOutlined, DeleteOutlined,
    CheckCircleOutlined, StopOutlined, SafetyOutlined,
    LockOutlined, UnlockOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';
import { apiClient } from '../api/client';
import { TiltCard } from '../components/TiltCard';

const { Title, Text } = Typography;

interface IpEntry {
    id: number;
    cidr: string;
    label: string;
    is_active: boolean;
    created_at: string;
}

export default function IpAllowlist() {
    const { mode } = useThemeStore();
    const t = getTokens(mode);
    const qc = useQueryClient();
    const [createOpen, setCreateOpen] = useState(false);
    const [form] = Form.useForm();

    const { data: entries = [], isLoading } = useQuery<IpEntry[]>({
        queryKey: ['ip-allowlist'],
        queryFn: () => apiClient.get('/settings/ip-allowlist/').then(r => r.data),
    });

    const createMut = useMutation({
        mutationFn: (body: { cidr: string; label: string }) =>
            apiClient.post('/settings/ip-allowlist/', body),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ip-allowlist'] });
            message.success('IP entry added');
            form.resetFields();
            setCreateOpen(false);
        },
        onError: (err: any) => {
            message.error(err?.response?.data?.detail?.[0]?.msg || 'Invalid CIDR');
        },
    });

    const toggleMut = useMutation({
        mutationFn: (id: number) => apiClient.patch(`/settings/ip-allowlist/${id}`),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ip-allowlist'] });
            message.success('Entry updated');
        },
    });

    const deleteMut = useMutation({
        mutationFn: (id: number) => apiClient.delete(`/settings/ip-allowlist/${id}`),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ip-allowlist'] });
            message.success('Entry deleted');
        },
    });

    const activeEntries = entries.filter(e => e.is_active).length;

    const columns = [
        {
            title: 'CIDR', dataIndex: 'cidr', key: 'cidr',
            render: (cidr: string, rec: IpEntry) => (
                <Space>
                    <GlobalOutlined style={{ color: rec.is_active ? t.green : t.muted }} />
                    <Text style={{
                        color: t.text, fontFamily: "'SF Mono', 'Fira Code', monospace",
                        fontWeight: 600, fontSize: 13,
                    }}>
                        {cidr}
                    </Text>
                </Space>
            ),
        },
        {
            title: 'Label', dataIndex: 'label', key: 'label',
            render: (label: string) => <Text style={{ color: t.text }}>{label}</Text>,
        },
        {
            title: 'Status', key: 'status',
            render: (_: unknown, rec: IpEntry) => (
                <Tag
                    icon={rec.is_active ? <CheckCircleOutlined /> : <StopOutlined />}
                    color={rec.is_active ? 'success' : 'default'}
                >
                    {rec.is_active ? 'Active' : 'Disabled'}
                </Tag>
            ),
        },
        {
            title: 'Added', dataIndex: 'created_at', key: 'created',
            render: (v: string) =>
                <Text style={{ color: t.muted, fontSize: 12 }}>{new Date(v).toLocaleDateString()}</Text>,
        },
        {
            title: 'Actions', key: 'actions', width: 120,
            render: (_: unknown, rec: IpEntry) => (
                <Space size={4}>
                    <Tooltip title={rec.is_active ? 'Disable' : 'Enable'}>
                        <Button
                            type="text" size="small"
                            icon={rec.is_active ? <LockOutlined /> : <UnlockOutlined />}
                            onClick={() => toggleMut.mutate(rec.id)}
                            style={{ color: rec.is_active ? t.orange : t.green }}
                        />
                    </Tooltip>
                    <Tooltip title="Delete">
                        <Popconfirm title="Delete this entry?" onConfirm={() => deleteMut.mutate(rec.id)}>
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
                        <SafetyOutlined style={{ marginRight: 10 }} />
                        IP Allowlist
                    </Title>
                    <Text style={{ color: t.muted }}>
                        Restrict API access to specific source IP addresses
                    </Text>
                </div>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                    Add IP Range
                </Button>
            </div>

            {entries.length === 0 && !isLoading && (
                <Alert
                    type="info" showIcon
                    message="Open Access Mode"
                    description="No IP entries configured. All source IPs are currently allowed. Add entries to restrict access."
                    style={{ marginBottom: 16 }}
                />
            )}

            {/* Stats */}
            <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={8}>
                    <TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.accent } as React.CSSProperties}>
                        <Statistic title={<Text style={{ color: t.muted }}>Total Rules</Text>} value={entries.length} prefix={<GlobalOutlined />} valueStyle={{ color: t.text }} />
                    </TiltCard>
                </Col>
                <Col span={8}>
                    <TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.green } as React.CSSProperties}>
                        <Statistic title={<Text style={{ color: t.muted }}>Active</Text>} value={activeEntries} prefix={<CheckCircleOutlined />} valueStyle={{ color: t.green }} />
                    </TiltCard>
                </Col>
                <Col span={8}>
                    <TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': entries.length > 0 ? t.green : t.red } as React.CSSProperties}>
                        <Statistic
                            title={<Text style={{ color: t.muted }}>Mode</Text>}
                            value={entries.length > 0 ? 'Restricted' : 'Open'}
                            prefix={entries.length > 0 ? <LockOutlined /> : <UnlockOutlined />}
                            valueStyle={{ color: entries.length > 0 ? t.green : t.red }}
                        />
                    </TiltCard>
                </Col>
            </Row>

            {/* Table */}
            <div style={cardStyle(t)}>
                <style>{tableStyleOverrides(t, 'nx-table')}</style>
                <Table
                    rowKey="id"
                    dataSource={entries}
                    columns={columns}
                    loading={isLoading}
                    pagination={false}
                    size="small"
                />
            </div>

            {/* Create Modal */}
            <Modal
                title="Add IP Range"
                open={createOpen}
                onCancel={() => { setCreateOpen(false); form.resetFields(); }}
                onOk={() => form.submit()}
                confirmLoading={createMut.isPending}
            >
                <Form form={form} layout="vertical" onFinish={(v) => createMut.mutate(v)}>
                    <Form.Item name="cidr" label="CIDR Range" rules={[{ required: true }]}
                        help="e.g. 10.0.0.0/8 or 1.2.3.4/32 for a single IP"
                    >
                        <Input placeholder="10.0.0.0/8" style={{ fontFamily: "'SF Mono', monospace" }} />
                    </Form.Item>
                    <Form.Item name="label" label="Label" rules={[{ required: true }]}>
                        <Input placeholder="e.g. Office VPN, Home IP" />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
