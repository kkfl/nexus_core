import { Table, Button, Modal, Form, Input, Typography, message, Tag } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';
import { FileTextOutlined, PlusOutlined } from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text } = Typography;

export default function KbSources() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [form] = Form.useForm();
    const { mode } = useThemeStore();
    const t = getTokens(mode);

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
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
        { title: 'Name', dataIndex: 'name', key: 'name', render: (n: string) => <Text style={{ color: t.text, fontWeight: 600 }}>{n}</Text> },
        { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (k: string) => <Tag style={{ background: `${t.accent}18`, color: t.accent, border: `1px solid ${t.accent}40` }}>{k}</Tag> },
        { title: 'Config', dataIndex: 'config', key: 'config', render: (cfg: any) => cfg ? <Text style={{ color: t.muted, fontFamily: 'monospace', fontSize: 11 }}>{JSON.stringify(cfg)}</Text> : <Text style={{ color: t.muted }}>—</Text> },
        { title: 'Created', dataIndex: 'created_at', key: 'created_at', render: (date: string) => <Text style={{ color: t.muted, fontSize: 12 }}>{new Date(date).toLocaleString()}</Text> },
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: t.text }}><FileTextOutlined style={{ marginRight: 10, color: t.accent }} />Knowledge Base Sources</Title>
                    <Text style={{ color: t.muted }}>Manage ingestion sources for the knowledge base</Text>
                </div>
                {role !== 'reader' && <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>Add Source</Button>}
            </div>
            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <Table dataSource={sources} columns={columns} rowKey="id" loading={isLoading} size="middle" />
            </div>
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
