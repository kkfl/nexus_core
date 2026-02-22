import { Table, Button, Modal, Form, Input, Typography, message, Tag } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';

const { Title } = Typography;

export default function KbSources() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [form] = Form.useForm();

    const { data: sources, isLoading } = useQuery({
        queryKey: ['kb_sources'],
        queryFn: async () => (await apiClient.get('/kb/sources')).data
    });

    const createSource = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/kb/sources', values)).data,
        onSuccess: () => {
            message.success('Source created');
            setIsModalOpen(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['kb_sources'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed to create source')
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: 'Name', dataIndex: 'name', key: 'name', render: (n: string) => <strong>{n}</strong> },
        { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (k: string) => <Tag color="blue">{k}</Tag> },
        { title: 'Config', dataIndex: 'config', key: 'config', render: (cfg: any) => cfg ? JSON.stringify(cfg) : '-' },
        { title: 'Created', dataIndex: 'created_at', key: 'created_at', render: (date: string) => new Date(date).toLocaleString() },
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>Knowledge Base Sources</Title>
                {role !== 'reader' && <Button type="primary" onClick={() => setIsModalOpen(true)}>Add Source</Button>}
            </div>

            <Table dataSource={sources} columns={columns} rowKey="id" loading={isLoading} size="middle" />

            <Modal title="Create KB Source" open={isModalOpen} onCancel={() => setIsModalOpen(false)} onOk={() => form.submit()} confirmLoading={createSource.isPending}>
                <Form form={form} layout="vertical" onFinish={createSource.mutate} initialValues={{ kind: 'manual' }}>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="kind" label="Kind (e.g. manual, s3, confluence)"><Input /></Form.Item>
                    <Form.Item name="config_str" label="Config JSON (Optional)"><Input.TextArea rows={3} placeholder='{"bucket": "test"}' /></Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
