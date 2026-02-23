import { Table, Button, Tag, Modal, Form, Input, Switch, InputNumber, message, Typography, Select } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';

const { Title } = Typography;

export default function TaskRoutes() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [form] = Form.useForm();

    const { data: routes, isLoading } = useQuery({
        queryKey: ['routes'],
        queryFn: async () => (await apiClient.get('/task-routes')).data
    });

    const { data: agents } = useQuery({
        queryKey: ['agents'],
        queryFn: async () => (await apiClient.get('/agents')).data
    });

    const createRoute = useMutation({
        mutationFn: async (values: any) => {
            // clean up optional arrays
            return (await apiClient.post('/task-routes', {
                ...values,
                required_capabilities: values.required_capabilities || [],
                rag_namespaces: values.rag_namespaces || []
            })).data;
        },
        onSuccess: () => {
            message.success('Task Route created');
            setIsModalOpen(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['routes'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed to create route')
    });

    const columns = [
        { title: 'Task Type', dataIndex: 'task_type', key: 'task_type', render: (t: string) => <strong>{t}</strong> },
        { title: 'Capabilities', dataIndex: 'required_capabilities', key: 'required_capabilities', render: (caps: string[]) => caps?.map(c => <Tag key={c}>{c}</Tag>) },
        { title: 'Pref Agent ID', dataIndex: 'preferred_agent_id', key: 'preferred_agent_id' },
        { title: 'Needs RAG', dataIndex: 'needs_rag', key: 'needs_rag', render: (val: boolean) => val ? <Tag color="blue">RAG Used</Tag> : '-' },
        { title: 'Max Retries', dataIndex: 'max_retries', key: 'max_retries' },
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>Task Routing Table</Title>
                {role !== 'reader' && <Button type="primary" onClick={() => setIsModalOpen(true)}>Add Route</Button>}
            </div>

            <Table dataSource={routes} columns={columns} rowKey="task_type" loading={isLoading} size="middle" />

            <Modal title="Configure Task Route" open={isModalOpen} onCancel={() => setIsModalOpen(false)} onOk={() => form.submit()} confirmLoading={createRoute.isPending} width={600}>
                <Form form={form} layout="vertical" onFinish={createRoute.mutate} initialValues={{ needs_rag: false, rag_top_k: 5, max_retries: 3 }}>
                    <Form.Item name="task_type" label="Task Type (e.g. system.echo)" rules={[{ required: true }]}><Input /></Form.Item>

                    <Form.Item name="required_capabilities" label="Required Capabilities">
                        <Select mode="tags" style={{ width: '100%' }} placeholder="Add capability requirements" />
                    </Form.Item>

                    <Form.Item name="preferred_agent_id" label="Preferred Agent">
                        <Select allowClear placeholder="Any capability match">
                            {agents?.map((a: any) => <Select.Option key={a.id} value={a.id}>{a.name} (ID: {a.id})</Select.Option>)}
                        </Select>
                    </Form.Item>

                    <Form.Item name="needs_rag" valuePropName="checked"><Switch checkedChildren="Inject RAG Context" unCheckedChildren="No Context" /></Form.Item>

                    <Form.Item name="rag_namespaces" label="RAG Namespaces (Optional)">
                        <Select mode="tags" style={{ width: '100%' }} placeholder="global, persona:*" />
                    </Form.Item>

                    <Form.Item name="rag_top_k" label="RAG Top-K Chunks"><InputNumber min={1} max={20} /></Form.Item>
                    <Form.Item name="max_retries" label="Max Execution Retries"><InputNumber min={0} max={10} /></Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
