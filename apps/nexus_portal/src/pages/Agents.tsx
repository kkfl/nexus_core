import { Table, Button, Space, Tag, Modal, Form, Input, Switch, InputNumber, message, Typography } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';
import { ApiOutlined, CheckCircleOutlined, WarningOutlined, ClockCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text } = Typography;

export default function Agents() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [form] = Form.useForm();
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const { data: agents, isLoading } = useQuery({
        queryKey: ['agents'],
        queryFn: async () => (await apiClient.get('/agents')).data
    });

    const { data: dashboardData, isLoading: healthLoading } = useQuery({
        queryKey: ['dashboard-summary'],
        queryFn: async () => (await apiClient.get('/brain/dashboard/summary')).data,
        refetchInterval: 30000,
    });

    const createAgent = useMutation({
        mutationFn: async (values: any) => {
            const caps = values.capabilities_str ? values.capabilities_str.split(',').map((s: string) => s.trim()) : [];
            const payload = { ...values, capabilities: { capabilities: caps } };
            delete payload.capabilities_str;
            return (await apiClient.post('/agents', payload)).data;
        },
        onSuccess: () => { message.success('Agent created'); setIsModalOpen(false); form.resetFields(); queryClient.invalidateQueries({ queryKey: ['agents'] }); },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed')
    });

    const pingAgent = useMutation({
        mutationFn: async (id: number) => (await apiClient.post(`/agents/${id}/ping`)).data,
        onSuccess: (data) => message.success(`Ping success! Version: ${data.version}`),
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Ping failed')
    });

    const healthColumns = [
        {
            title: 'Agent', dataIndex: 'name', key: 'name',
            render: (name: string) => <Text style={{ color: t.text, fontWeight: 600 }}><ApiOutlined style={{ marginRight: 8, color: t.muted }} />{name}</Text>
        },
        {
            title: 'Health Status', dataIndex: 'status', key: 'status', width: 150,
            render: (s: string) => {
                const isOnline = s === 'active';
                return <Tag style={{ background: isOnline ? `${t.green}18` : `${t.red}18`, color: isOnline ? t.green : t.red, border: `1px solid ${isOnline ? `${t.green}40` : `${t.red}40`}` }} icon={isOnline ? <CheckCircleOutlined /> : <WarningOutlined />}>{isOnline ? 'Online' : 'Down'}</Tag>;
            }
        },
        {
            title: 'Last Heartbeat', dataIndex: 'last_seen_at', key: 'last_seen_at',
            render: (date: string | null) => date
                ? <Space><ClockCircleOutlined style={{ color: t.muted }} /><Text style={{ color: t.muted }}>{new Date(date).toLocaleString()}</Text></Space>
                : <Text style={{ color: t.muted }}>Never</Text>
        },
    ];

    const registryColumns = [
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
        { title: 'Name', dataIndex: 'name', key: 'name', render: (n: string) => <Text style={{ color: t.text, fontWeight: 600 }}>{n}</Text> },
        { title: 'Base URL', dataIndex: 'base_url', key: 'base_url', render: (u: string) => <Text style={{ color: t.cyan, fontFamily: 'monospace', fontSize: 12 }}>{u}</Text> },
        { title: 'Active', dataIndex: 'is_active', key: 'is_active', render: (val: boolean) => <Tag style={{ background: val ? `${t.green}18` : `${t.red}18`, color: val ? t.green : t.red, border: `1px solid ${val ? `${t.green}40` : `${t.red}40`}` }}>{val ? 'Yes' : 'No'}</Tag> },
        { title: 'Timeout', dataIndex: 'timeout_seconds', key: 'timeout_seconds' },
        { title: 'Concurrency', dataIndex: 'max_concurrency', key: 'max_concurrency' },
        {
            title: 'Actions', key: 'actions', render: (_: any, record: any) => (
                <Space>{role !== 'reader' && <Button size="small" onClick={() => pingAgent.mutate(record.id)} loading={pingAgent.isPending}>Ping</Button>}</Space>
            )
        }
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: t.text }}><ApiOutlined style={{ marginRight: 10, color: t.accent }} />Agents</Title>
                    <Text style={{ color: t.muted }}>Manage micro-agent registry and health</Text>
                </div>
                {role !== 'reader' && <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>Register Agent</Button>}
            </div>

            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden', marginBottom: 24 }}>
                <div style={{ padding: '14px 20px', borderBottom: `1px solid ${t.border}` }}>
                    <Text style={{ color: t.muted, fontSize: 11, letterSpacing: 1 }}>AGENT HEALTH & ACTIVITY</Text>
                </div>
                <Table dataSource={dashboardData?.recent_activity || []} columns={healthColumns} rowKey="name" loading={healthLoading} pagination={false} size="middle" />
            </div>

            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <div style={{ padding: '14px 20px', borderBottom: `1px solid ${t.border}` }}>
                    <Text style={{ color: t.muted, fontSize: 11, letterSpacing: 1 }}>AGENT REGISTRY</Text>
                </div>
                <Table dataSource={agents} columns={registryColumns} rowKey="id" loading={isLoading} size="middle" />
            </div>

            <Modal title="Register New Agent" open={isModalOpen} onCancel={() => setIsModalOpen(false)} onOk={() => form.submit()} confirmLoading={createAgent.isPending}>
                <Form form={form} layout="vertical" onFinish={createAgent.mutate} initialValues={{ is_active: true, max_concurrency: 2, timeout_seconds: 30 }}>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="base_url" label="Base URL" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="capabilities_str" label="Capabilities (comma separated)"><Input placeholder="system.echo, file.read" /></Form.Item>
                    <Form.Item name="max_concurrency" label="Max Concurrency"><InputNumber min={1} /></Form.Item>
                    <Form.Item name="timeout_seconds" label="Timeout (s)"><InputNumber min={5} /></Form.Item>
                    <Form.Item name="is_active" valuePropName="checked"><Switch checkedChildren="Active" unCheckedChildren="Inactive" /></Form.Item>
                    <Text style={{ color: t.muted, fontSize: 12 }}>API Key is returned once on creation.</Text>
                </Form>
            </Modal>
        </div>
    );
}
