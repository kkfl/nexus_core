import { Table, Button, Space, Tag, Modal, Form, Input, Switch, Typography, message, Collapse } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';

const { Title } = Typography;
const { TextArea } = Input;

export default function Personas() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);

    const [isPersonaModalOpen, setIsPersonaModalOpen] = useState(false);
    const [isVersionModalOpen, setIsVersionModalOpen] = useState(false);
    const [selectedPersona, setSelectedPersona] = useState<any>(null);
    const [pForm] = Form.useForm();
    const [vForm] = Form.useForm();

    const { data: personas, isLoading } = useQuery({
        queryKey: ['personas'],
        queryFn: async () => (await apiClient.get('/personas')).data
    });

    const getVersions = useQuery({
        queryKey: ['persona_versions', selectedPersona?.id],
        queryFn: async () => (await apiClient.get(`/personas/${selectedPersona?.id}/versions`)).data,
        enabled: !!selectedPersona
    });

    const createPersona = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/personas', values)).data,
        onSuccess: () => {
            message.success('Persona created');
            setIsPersonaModalOpen(false);
            pForm.resetFields();
            queryClient.invalidateQueries({ queryKey: ['personas'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed to create persona')
    });

    const createVersion = useMutation({
        mutationFn: async (values: any) => {
            const payload = { ...values };
            try {
                if (payload.tools_policy) payload.tools_policy = JSON.parse(payload.tools_policy);
                if (payload.meta_data) payload.meta_data = JSON.parse(payload.meta_data);
            } catch {
                throw new Error("Invalid JSON in policy or meta");
            }
            return (await apiClient.post(`/personas/${selectedPersona.id}/versions`, payload)).data;
        },
        onSuccess: () => {
            message.success('Version created');
            setIsVersionModalOpen(false);
            vForm.resetFields();
            queryClient.invalidateQueries({ queryKey: ['persona_versions', selectedPersona.id] });
        },
        onError: (e: any) => message.error(e.message || e?.response?.data?.detail || 'Error creating version')
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: 'Name', dataIndex: 'name', key: 'name', render: (n: string) => <strong>{n}</strong> },
        { title: 'Description', dataIndex: 'description', key: 'description' },
        { title: 'Active', dataIndex: 'is_active', key: 'is_active', render: (val: boolean) => val ? <Tag color="green">Yes</Tag> : <Tag color="red">No</Tag> },
        {
            title: 'Actions', key: 'actions', render: (_: any, record: any) => (
                <Button size="small" onClick={() => setSelectedPersona(record)}>Manage Versions</Button>
            )
        }
    ];

    const versionColumns = [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: 'Version Code', dataIndex: 'version', key: 'version', render: (v: string) => <Tag color="blue">{v}</Tag> },
        {
            title: 'Capabilities', key: 'caps', render: (_: any, record: any) => (
                <Space wrap>
                    {(record.tools_policy?.allowed_capabilities || []).map((c: string) => <Tag key={c}>{c}</Tag>)}
                </Space>
            )
        },
        { title: 'RAG', key: 'rag', render: (_: any, record: any) => record.tools_policy?.rag?.enabled ? <Tag color="purple">Enabled</Tag> : '-' },
        { title: 'Created', dataIndex: 'created_at', key: 'created_at', render: (date: string) => new Date(date).toLocaleString() },
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>Persona Registry</Title>
                {role !== 'reader' && <Button type="primary" onClick={() => setIsPersonaModalOpen(true)}>Create Persona</Button>}
            </div>

            <Table dataSource={personas} columns={columns} rowKey="id" loading={isLoading} size="middle" />

            {/* Persona Detail Modal */}
            <Modal title={`Persona: ${selectedPersona?.name}`} open={!!selectedPersona} onCancel={() => setSelectedPersona(null)} footer={null} width={900}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                    <Title level={4}>Versions</Title>
                    {role !== 'reader' && <Button onClick={() => setIsVersionModalOpen(true)}>Draft New Version</Button>}
                </div>
                <Table dataSource={getVersions.data} columns={versionColumns} rowKey="id" loading={getVersions.isLoading} size="small"
                    expandable={{
                        expandedRowRender: record => (
                            <Collapse items={[
                                { key: 'prompt', label: 'System Prompt', children: <pre style={{ whiteSpace: 'pre-wrap' }}>{record.system_prompt}</pre> },
                                { key: 'policy', label: 'Tools Policy (JSON)', children: <pre>{JSON.stringify(record.tools_policy, null, 2)}</pre> }
                            ]} />
                        )
                    }}
                />
            </Modal>

            {/* Create Persona */}
            <Modal title="Create Persona" open={isPersonaModalOpen} onCancel={() => setIsPersonaModalOpen(false)} onOk={() => pForm.submit()} confirmLoading={createPersona.isPending}>
                <Form form={pForm} layout="vertical" onFinish={createPersona.mutate} initialValues={{ is_active: true }}>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="description" label="Description"><Input /></Form.Item>
                    <Form.Item name="is_active" valuePropName="checked"><Switch checkedChildren="Active" unCheckedChildren="Inactive" /></Form.Item>
                </Form>
            </Modal>

            {/* Create Version */}
            <Modal title="Draft Persona Version" open={isVersionModalOpen} onCancel={() => setIsVersionModalOpen(false)} onOk={() => vForm.submit()} confirmLoading={createVersion.isPending} width={700}>
                <Form form={vForm} layout="vertical" onFinish={createVersion.mutate} initialValues={{ version: '1.0', tools_policy: '{\n  "allowed_capabilities": ["system.echo"]\n}' }}>
                    <Form.Item name="version" label="Version Code (e.g. 1.0, 1.1-beta)" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="system_prompt" label="System Prompt" rules={[{ required: true }]}><TextArea rows={4} /></Form.Item>
                    <Form.Item name="tools_policy" label="Tools Policy (Valid JSON)"><TextArea rows={6} style={{ fontFamily: 'monospace' }} /></Form.Item>
                    <Form.Item name="meta_data" label="Metadata (Valid JSON, Optional)"><TextArea rows={2} style={{ fontFamily: 'monospace' }} placeholder="{}" /></Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
