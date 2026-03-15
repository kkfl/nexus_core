import { Table, Button, Space, Tag, Modal, Form, Input, Select, Typography, message, Upload, Tooltip } from 'antd';
import { UploadOutlined, LinkOutlined, ReloadOutlined, FileTextOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text } = Typography;
const { TextArea } = Input;

export default function KbDocuments() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const { accessToken } = useAuthStore();
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const [isTextModalOpen, setIsTextModalOpen] = useState(false);
    const [isFileModalOpen, setIsFileModalOpen] = useState(false);
    const [isUrlModalOpen, setIsUrlModalOpen] = useState(false);
    const [form] = Form.useForm();
    const [fileForm] = Form.useForm();
    const [urlForm] = Form.useForm();

    const { data: documents, isLoading } = useQuery({
        queryKey: ['kb_documents'],
        queryFn: async () => (await apiClient.get('/kb/documents')).data,
        refetchInterval: 5000,
    });

    const { data: sources } = useQuery({
        queryKey: ['kb_sources'],
        queryFn: async () => (await apiClient.get('/kb/sources')).data
    });

    const ingestText = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/kb/documents/text', values)).data,
        onSuccess: () => { message.success('Text document queued'); setIsTextModalOpen(false); form.resetFields(); queryClient.invalidateQueries({ queryKey: ['kb_documents'] }); },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Ingestion failed')
    });

    const ingestUrl = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/kb/documents/url', values)).data,
        onSuccess: () => { message.success('URL ingest queued'); setIsUrlModalOpen(false); urlForm.resetFields(); queryClient.invalidateQueries({ queryKey: ['kb_documents'] }); },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'URL ingest failed')
    });

    const reingest = useMutation({
        mutationFn: async (docId: number) => (await apiClient.post(`/kb/documents/${docId}/reingest`)).data,
        onSuccess: () => { message.success('Re-ingest queued'); queryClient.invalidateQueries({ queryKey: ['kb_documents'] }); },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Re-ingest failed')
    });

    const statusColor = (s: string) => {
        if (s === 'ready') return { bg: `${t.green}18`, color: t.green, border: `${t.green}40` };
        if (s === 'failed') return { bg: `${t.red}18`, color: t.red, border: `${t.red}40` };
        if (s === 'processing') return { bg: `${t.accent}18`, color: t.accent, border: `${t.accent}40` };
        return { bg: `${t.orange}18`, color: t.orange, border: `${t.orange}40` };
    };

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
        { title: 'Title', dataIndex: 'title', key: 'title', render: (v: string) => <Text style={{ color: t.text, fontWeight: 600 }}>{v}</Text> },
        { title: 'Namespace', dataIndex: 'namespace', key: 'namespace', render: (ns: string) => <Tag style={{ background: `${t.accent}18`, color: t.accent, border: `1px solid ${t.accent}40` }}>{ns}</Tag> },
        {
            title: 'Status', dataIndex: 'ingest_status', key: 'ingest_status', render: (s: string, record: any) => {
                const c = statusColor(s);
                const tag = <Tag style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}>{s.toUpperCase()}</Tag>;
                return s === 'failed' && record.error_message ? <Tooltip title={record.error_message}>{tag}</Tooltip> : tag;
            }
        },
        { title: 'Ver', dataIndex: 'version', key: 'version', width: 50 },
        { title: 'Type', dataIndex: 'content_type', key: 'content_type', width: 120 },
        { title: 'Source', dataIndex: 'source_id', key: 'source_id', width: 70 },
        {
            title: 'Actions', key: 'actions', width: 100,
            render: (_: any, record: any) => role !== 'reader' ? (
                <Tooltip title="Re-ingest"><Button size="small" icon={<ReloadOutlined />} onClick={() => reingest.mutate(record.id)} loading={reingest.isPending} /></Tooltip>
            ) : null
        },
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: t.text }}><FileTextOutlined style={{ marginRight: 10, color: t.accent }} />Knowledge Base Documents</Title>
                    <Text style={{ color: t.muted }}>Manage and ingest documents into the knowledge base</Text>
                </div>
                {role !== 'reader' && (
                    <Space>
                        <Button onClick={() => setIsTextModalOpen(true)}>Ingest Text</Button>
                        <Button icon={<LinkOutlined />} onClick={() => setIsUrlModalOpen(true)}>Ingest URL</Button>
                        <Button type="primary" onClick={() => setIsFileModalOpen(true)} icon={<UploadOutlined />}>Upload File</Button>
                    </Space>
                )}
            </div>
            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <Table dataSource={documents} columns={columns} rowKey="id" loading={isLoading} size="middle" />
            </div>

            <Modal title="Ingest Raw Text" open={isTextModalOpen} onCancel={() => setIsTextModalOpen(false)} onOk={() => form.submit()} confirmLoading={ingestText.isPending} width={600}>
                <Form form={form} layout="vertical" onFinish={ingestText.mutate} initialValues={{ namespace: 'global' }}>
                    <Form.Item name="source_id" label="KB Source" rules={[{ required: true }]}><Select options={sources?.map((s: any) => ({ label: s.name, value: s.id }))} /></Form.Item>
                    <Form.Item name="namespace" label="Namespace"><Input /></Form.Item>
                    <Form.Item name="title" label="Document Title" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="text" label="Content (Markdown/Text)" rules={[{ required: true }]}><TextArea rows={10} /></Form.Item>
                </Form>
            </Modal>

            <Modal title="Ingest from URL" open={isUrlModalOpen} onCancel={() => setIsUrlModalOpen(false)} onOk={() => urlForm.submit()} confirmLoading={ingestUrl.isPending} width={500}>
                <Form form={urlForm} layout="vertical" onFinish={ingestUrl.mutate} initialValues={{ namespace: 'global' }}>
                    <Form.Item name="source_id" label="KB Source" rules={[{ required: true }]}><Select options={sources?.map((s: any) => ({ label: s.name, value: s.id }))} /></Form.Item>
                    <Form.Item name="url" label="URL" rules={[{ required: true, type: 'url', message: 'Enter a valid URL' }]}><Input placeholder="https://example.com/article" /></Form.Item>
                    <Form.Item name="namespace" label="Namespace"><Input /></Form.Item>
                    <Form.Item name="title" label="Document Title" rules={[{ required: true }]}><Input /></Form.Item>
                </Form>
            </Modal>

            <Modal title="Upload Document File" open={isFileModalOpen} onCancel={() => setIsFileModalOpen(false)} footer={null}>
                <Form form={fileForm} layout="vertical" initialValues={{ namespace: 'global' }}>
                    <Form.Item name="source_id" label="KB Source" rules={[{ required: true }]}><Select options={sources?.map((s: any) => ({ label: s.name, value: s.id }))} /></Form.Item>
                    <Form.Item name="namespace" label="Namespace"><Input /></Form.Item>
                    <Form.Item label="File">
                        <Upload
                            action={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/kb/documents/upload`}
                            headers={{ Authorization: `Bearer ${accessToken}` }}
                            data={(file) => ({ source_id: fileForm.getFieldValue('source_id'), namespace: fileForm.getFieldValue('namespace'), title: file.name })}
                            onChange={(info) => {
                                if (info.file.status === 'done') { message.success(`${info.file.name} uploaded`); setIsFileModalOpen(false); queryClient.invalidateQueries({ queryKey: ['kb_documents'] }); }
                                else if (info.file.status === 'error') { message.error(`${info.file.name} upload failed.`); }
                            }}
                            showUploadList={false}
                        >
                            <Button icon={<UploadOutlined />}>Click to Upload (PDF, MD, TXT)</Button>
                        </Upload>
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
