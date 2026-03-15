import { Table, Button, Space, Tag, Modal, Form, Input, Switch, Typography, message, Collapse } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';
import { IdcardOutlined, PlusOutlined } from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text } = Typography;
const { TextArea } = Input;

export default function Personas() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const [isPersonaModalOpen, setIsPersonaModalOpen] = useState(false);
    const [isVersionModalOpen, setIsVersionModalOpen] = useState(false);
    const [selectedPersona, setSelectedPersona] = useState<any>(null);
    const [pForm] = Form.useForm();
    const [vForm] = Form.useForm();
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const { data: personas, isLoading } = useQuery({ queryKey: ['personas'], queryFn: async () => (await apiClient.get('/personas')).data });
    const getVersions = useQuery({ queryKey: ['persona_versions', selectedPersona?.id], queryFn: async () => (await apiClient.get(`/personas/${selectedPersona?.id}/versions`)).data, enabled: !!selectedPersona });

    const createPersona = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/personas', values)).data,
        onSuccess: () => { message.success('Persona created'); setIsPersonaModalOpen(false); pForm.resetFields(); queryClient.invalidateQueries({ queryKey: ['personas'] }); },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed')
    });

    const createVersion = useMutation({
        mutationFn: async (values: any) => {
            const payload = { ...values };
            try { if (payload.tools_policy) payload.tools_policy = JSON.parse(payload.tools_policy); if (payload.meta_data) payload.meta_data = JSON.parse(payload.meta_data); } catch { throw new Error("Invalid JSON"); }
            return (await apiClient.post(`/personas/${selectedPersona.id}/versions`, payload)).data;
        },
        onSuccess: () => { message.success('Version created'); setIsVersionModalOpen(false); vForm.resetFields(); queryClient.invalidateQueries({ queryKey: ['persona_versions', selectedPersona.id] }); },
        onError: (e: any) => message.error(e.message || e?.response?.data?.detail || 'Error')
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
        { title: 'Name', dataIndex: 'name', key: 'name', render: (n: string) => <Text style={{ color: t.text, fontWeight: 600 }}>{n}</Text> },
        { title: 'Description', dataIndex: 'description', key: 'description', render: (d: string) => <Text style={{ color: t.muted }}>{d}</Text> },
        { title: 'Active', dataIndex: 'is_active', key: 'is_active', render: (val: boolean) => <Tag style={{ background: val ? `${t.green}18` : `${t.red}18`, color: val ? t.green : t.red, border: `1px solid ${val ? `${t.green}40` : `${t.red}40`}` }}>{val ? 'Yes' : 'No'}</Tag> },
        { title: 'Actions', key: 'actions', render: (_: any, record: any) => <Button size="small" onClick={() => setSelectedPersona(record)} style={{ color: t.accent }}>Manage Versions</Button> }
    ];

    const versionColumns = [
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
        { title: 'Version', dataIndex: 'version', key: 'version', render: (v: string) => <Tag style={{ background: `${t.accent}18`, color: t.accent, border: `1px solid ${t.accent}40` }}>{v}</Tag> },
        { title: 'Capabilities', key: 'caps', render: (_: any, record: any) => <Space wrap>{(record.tools_policy?.allowed_capabilities || []).map((c: string) => <Tag key={c} style={{ background: `${t.muted}18`, color: t.muted, border: `1px solid ${t.muted}40` }}>{c}</Tag>)}</Space> },
        { title: 'RAG', key: 'rag', render: (_: any, record: any) => record.tools_policy?.rag?.enabled ? <Tag style={{ background: `${t.purple}18`, color: t.purple, border: `1px solid ${t.purple}40` }}>Enabled</Tag> : <Text style={{ color: t.muted }}>—</Text> },
        { title: 'Created', dataIndex: 'created_at', key: 'created_at', render: (date: string) => <Text style={{ color: t.muted, fontSize: 12 }}>{new Date(date).toLocaleString()}</Text> },
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: t.text }}><IdcardOutlined style={{ marginRight: 10, color: t.accent }} />Persona Registry</Title>
                    <Text style={{ color: t.muted }}>Manage AI persona definitions and versions</Text>
                </div>
                {role !== 'reader' && <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsPersonaModalOpen(true)}>Create Persona</Button>}
            </div>
            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <Table dataSource={personas} columns={columns} rowKey="id" loading={isLoading} size="middle" />
            </div>

            <Modal title={`Persona: ${selectedPersona?.name}`} open={!!selectedPersona} onCancel={() => setSelectedPersona(null)} footer={null} width={900}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                    <Title level={4} style={{ color: t.text }}>Versions</Title>
                    {role !== 'reader' && <Button onClick={() => setIsVersionModalOpen(true)}>Draft New Version</Button>}
                </div>
                <Table dataSource={getVersions.data} columns={versionColumns} rowKey="id" loading={getVersions.isLoading} size="small"
                    expandable={{
                        expandedRowRender: record => (
                            <Collapse items={[
                                { key: 'prompt', label: 'System Prompt', children: <pre style={{ whiteSpace: 'pre-wrap', color: t.text, background: t.bg, padding: 12, borderRadius: 8, border: `1px solid ${t.border}` }}>{record.system_prompt}</pre> },
                                { key: 'policy', label: 'Tools Policy', children: <pre style={{ color: t.text, background: t.bg, padding: 12, borderRadius: 8, border: `1px solid ${t.border}` }}>{JSON.stringify(record.tools_policy, null, 2)}</pre> }
                            ]} />
                        )
                    }}
                />
            </Modal>

            <Modal title="Create Persona" open={isPersonaModalOpen} onCancel={() => setIsPersonaModalOpen(false)} onOk={() => pForm.submit()} confirmLoading={createPersona.isPending}>
                <Form form={pForm} layout="vertical" onFinish={createPersona.mutate} initialValues={{ is_active: true }}>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="description" label="Description"><Input /></Form.Item>
                    <Form.Item name="is_active" valuePropName="checked"><Switch checkedChildren="Active" unCheckedChildren="Inactive" /></Form.Item>
                </Form>
            </Modal>

            <Modal title="Draft Persona Version" open={isVersionModalOpen} onCancel={() => setIsVersionModalOpen(false)} onOk={() => vForm.submit()} confirmLoading={createVersion.isPending} width={700}>
                <Form form={vForm} layout="vertical" onFinish={createVersion.mutate} initialValues={{ version: '1.0', tools_policy: '{\n  "allowed_capabilities": ["system.echo"]\n}' }}>
                    <Form.Item name="version" label="Version Code" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="system_prompt" label="System Prompt" rules={[{ required: true }]}><TextArea rows={4} /></Form.Item>
                    <Form.Item name="tools_policy" label="Tools Policy (JSON)"><TextArea rows={6} style={{ fontFamily: 'monospace' }} /></Form.Item>
                    <Form.Item name="meta_data" label="Metadata (JSON, Optional)"><TextArea rows={2} style={{ fontFamily: 'monospace' }} placeholder="{}" /></Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
