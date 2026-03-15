import { Table, Button, Tag, Modal, Form, Input, Switch, InputNumber, message, Typography, Select } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';
import { BarsOutlined, PlusOutlined } from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text } = Typography;

export default function TaskRoutes() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [form] = Form.useForm();
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const { data: routes, isLoading } = useQuery({ queryKey: ['routes'], queryFn: async () => (await apiClient.get('/task-routes')).data });
    const { data: agents } = useQuery({ queryKey: ['agents'], queryFn: async () => (await apiClient.get('/agents')).data });

    const createRoute = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/task-routes', { ...values, required_capabilities: values.required_capabilities || [], rag_namespaces: values.rag_namespaces || [] })).data,
        onSuccess: () => { message.success('Route created'); setIsModalOpen(false); form.resetFields(); queryClient.invalidateQueries({ queryKey: ['routes'] }); },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed')
    });

    const columns = [
        { title: 'Task Type', dataIndex: 'task_type', key: 'task_type', render: (v: string) => <Text style={{ color: t.cyan, fontWeight: 600, fontFamily: 'monospace' }}>{v}</Text> },
        { title: 'Capabilities', dataIndex: 'required_capabilities', key: 'required_capabilities', render: (caps: string[]) => caps?.map(c => <Tag key={c} style={{ background: `${t.accent}18`, color: t.accent, border: `1px solid ${t.accent}40` }}>{c}</Tag>) },
        { title: 'Pref Agent ID', dataIndex: 'preferred_agent_id', key: 'preferred_agent_id' },
        { title: 'Needs RAG', dataIndex: 'needs_rag', key: 'needs_rag', render: (val: boolean) => val ? <Tag style={{ background: `${t.purple}18`, color: t.purple, border: `1px solid ${t.purple}40` }}>RAG Used</Tag> : <Text style={{ color: t.muted }}>—</Text> },
        { title: 'Max Retries', dataIndex: 'max_retries', key: 'max_retries' },
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: t.text }}><BarsOutlined style={{ marginRight: 10, color: t.accent }} />Task Routing Table</Title>
                    <Text style={{ color: t.muted }}>Configure task type to agent routing rules</Text>
                </div>
                {role !== 'reader' && <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>Add Route</Button>}
            </div>
            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <Table dataSource={routes} columns={columns} rowKey="task_type" loading={isLoading} size="middle" />
            </div>
            <Modal title="Configure Task Route" open={isModalOpen} onCancel={() => setIsModalOpen(false)} onOk={() => form.submit()} confirmLoading={createRoute.isPending} width={600}>
                <Form form={form} layout="vertical" onFinish={createRoute.mutate} initialValues={{ needs_rag: false, rag_top_k: 5, max_retries: 3 }}>
                    <Form.Item name="task_type" label="Task Type" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="required_capabilities" label="Required Capabilities"><Select mode="tags" style={{ width: '100%' }} placeholder="Add capabilities" /></Form.Item>
                    <Form.Item name="preferred_agent_id" label="Preferred Agent"><Select allowClear placeholder="Any">{agents?.map((a: any) => <Select.Option key={a.id} value={a.id}>{a.name} (ID: {a.id})</Select.Option>)}</Select></Form.Item>
                    <Form.Item name="needs_rag" valuePropName="checked"><Switch checkedChildren="RAG Context" unCheckedChildren="No Context" /></Form.Item>
                    <Form.Item name="rag_namespaces" label="RAG Namespaces"><Select mode="tags" style={{ width: '100%' }} placeholder="global" /></Form.Item>
                    <Form.Item name="rag_top_k" label="RAG Top-K"><InputNumber min={1} max={20} /></Form.Item>
                    <Form.Item name="max_retries" label="Max Retries"><InputNumber min={0} max={10} /></Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
