import { Table, Button, Tag, Modal, Form, Input, Select, message, Typography } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';

const { Title, Text } = Typography;

export default function PersonaDefaults() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [form] = Form.useForm();

    const { data: defaults, isLoading } = useQuery({
        queryKey: ['persona_defaults'],
        queryFn: async () => (await apiClient.get('/personas/defaults')).data
    });

    const { data: personas } = useQuery({
        queryKey: ['personas_list'],
        queryFn: async () => {
            const res = await apiClient.get('/personas');
            const pairs: any[] = [];
            for (const p of res.data) {
                const vRes = await apiClient.get(`/personas/${p.id}/versions`);
                for (const v of vRes.data) {
                    pairs.push({ label: `${p.name} (v${v.version})`, value: v.id });
                }
            }
            return pairs;
        }
    });

    const createDefault = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/personas/defaults', values)).data,
        onSuccess: () => {
            message.success('Default configuration applied');
            setIsModalOpen(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['persona_defaults'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed to map default')
    });

    const columns = [
        { title: 'Level', dataIndex: 'level', key: 'level', render: (l: string) => <Tag color={l === 'global' ? 'red' : 'blue'}>{l.toUpperCase()}</Tag> },
        { title: 'Target ID', dataIndex: 'target_id', key: 'target_id', render: (t: string) => t || <Text type="secondary">N/A (Global)</Text> },
        { title: 'Persona Version Mapped', dataIndex: 'persona_version_id', key: 'persona_version_id', render: (id: number) => <strong>ID: {id}</strong> },
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>Persona Defaults & Routing Overrides</Title>
                {role !== 'reader' && <Button type="primary" onClick={() => setIsModalOpen(true)}>Add Binding</Button>}
            </div>

            <Table dataSource={defaults} columns={columns} rowKey="id" loading={isLoading} size="middle" />

            <Modal title="Configure Persona Binding" open={isModalOpen} onCancel={() => setIsModalOpen(false)} onOk={() => form.submit()} confirmLoading={createDefault.isPending}>
                <Form form={form} layout="vertical" onFinish={createDefault.mutate} initialValues={{ level: 'global' }}>
                    <Form.Item name="level" label="Binding Level (Priority)" rules={[{ required: true }]}>
                        <Select options={[
                            { label: 'Global (Fallback)', value: 'global' },
                            { label: 'Task Type Specific', value: 'task_type' },
                            { label: 'Agent Specific', value: 'agent_id' }
                        ]} />
                    </Form.Item>

                    <Form.Item name="target_id" label="Target Identifier (e.g. system.echo or 1)">
                        <Input placeholder="Leave blank for global" />
                    </Form.Item>

                    <Form.Item name="persona_version_id" label="Bind to Persona Version" rules={[{ required: true }]}>
                        <Select showSearch options={personas} placeholder="Select a specific version" />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
