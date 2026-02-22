import { Table, Button, Space, Tag, Modal, Form, Input, Switch, InputNumber, message, Typography } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';

const { Title, Text } = Typography;

export default function Agents() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [form] = Form.useForm();

    const { data: agents, isLoading } = useQuery({
        queryKey: ['agents'],
        queryFn: async () => (await apiClient.get('/agents')).data
    });

    const createAgent = useMutation({
        mutationFn: async (values: any) => {
            // Parse capabilities string to array
            const caps = values.capabilities_str ? values.capabilities_str.split(',').map((s: string) => s.trim()) : [];
            const payload = { ...values, capabilities: { capabilities: caps } };
            delete payload.capabilities_str;
            return (await apiClient.post('/agents', payload)).data;
        },
        onSuccess: () => {
            message.success('Agent created safely. (API Key generated but hidden in V1 portal)');
            setIsModalOpen(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['agents'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed to create agent')
    });

    const pingAgent = useMutation({
        mutationFn: async (id: number) => (await apiClient.post(`/agents/${id}/ping`)).data,
        onSuccess: (data) => message.success(`Ping success! Agent version: ${data.version}`),
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Ping failed (Timeout/Error)')
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: 'Name', dataIndex: 'name', key: 'name' },
        { title: 'Base URL', dataIndex: 'base_url', key: 'base_url' },
        { title: 'Active', dataIndex: 'is_active', key: 'is_active', render: (val: boolean) => val ? <Tag color="green">Yes</Tag> : <Tag color="red">No</Tag> },
        { title: 'Timeout (s)', dataIndex: 'timeout_seconds', key: 'timeout_seconds' },
        { title: 'Concurrency', dataIndex: 'max_concurrency', key: 'max_concurrency' },
        {
            title: 'Actions', key: 'actions', render: (_: any, record: any) => (
                <Space>
                    {role !== 'reader' && (
                        <Button size="small" onClick={() => pingAgent.mutate(record.id)} loading={pingAgent.isPending}>Ping</Button>
                    )}
                </Space>
            )
        }
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>Agents Registry</Title>
                {role !== 'reader' && <Button type="primary" onClick={() => setIsModalOpen(true)}>Register Agent</Button>}
            </div>

            <Table dataSource={agents} columns={columns} rowKey="id" loading={isLoading} size="middle" />

            <Modal title="Register New Agent" open={isModalOpen} onCancel={() => setIsModalOpen(false)} onOk={() => form.submit()} confirmLoading={createAgent.isPending}>
                <Form form={form} layout="vertical" onFinish={createAgent.mutate} initialValues={{ is_active: true, max_concurrency: 2, timeout_seconds: 30 }}>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="base_url" label="Base URL (e.g. http://agent:8001)" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="capabilities_str" label="Capabilities (comma separated)"><Input placeholder="system.echo, file.read" /></Form.Item>
                    <Form.Item name="max_concurrency" label="Max Concurrency"><InputNumber min={1} /></Form.Item>
                    <Form.Item name="timeout_seconds" label="Timeout (Seconds)"><InputNumber min={5} /></Form.Item>
                    <Form.Item name="is_active" valuePropName="checked"><Switch checkedChildren="Active" unCheckedChildren="Inactive" /></Form.Item>
                    <Text type="secondary">Note: The agent API key is returned exactly once. For the V1 portal, creating an agent through the UI automatically configures it in the DB, but you need to retrieve the key from CLI if bridging external manual agents.</Text>
                </Form>
            </Modal>
        </div>
    );
}
