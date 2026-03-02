import { Table, Button, Space, Tag, Modal, Form, Input, Select, Typography, message, Upload, Tooltip } from 'antd';
import { UploadOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useState } from 'react';

const { Title } = Typography;
const { TextArea } = Input;

export default function KbDocuments() {
    const queryClient = useQueryClient();
    const role = useAuthStore(s => s.user?.role);
    const { accessToken } = useAuthStore();

    const [isTextModalOpen, setIsTextModalOpen] = useState(false);
    const [isFileModalOpen, setIsFileModalOpen] = useState(false);
    const [isUrlModalOpen, setIsUrlModalOpen] = useState(false);
    const [form] = Form.useForm();
    const [fileForm] = Form.useForm();
    const [urlForm] = Form.useForm();

    const { data: documents, isLoading } = useQuery({
        queryKey: ['kb_documents'],
        queryFn: async () => (await apiClient.get('/kb/documents')).data,
        refetchInterval: 5000,  // poll for status updates
    });

    const { data: sources } = useQuery({
        queryKey: ['kb_sources'],
        queryFn: async () => (await apiClient.get('/kb/sources')).data
    });

    const ingestText = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/kb/documents/text', values)).data,
        onSuccess: () => {
            message.success('Text document queued for ingestion');
            setIsTextModalOpen(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['kb_documents'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Ingestion failed')
    });

    const ingestUrl = useMutation({
        mutationFn: async (values: any) => (await apiClient.post('/kb/documents/url', values)).data,
        onSuccess: () => {
            message.success('URL ingest queued');
            setIsUrlModalOpen(false);
            urlForm.resetFields();
            queryClient.invalidateQueries({ queryKey: ['kb_documents'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'URL ingest failed')
    });

    const reingest = useMutation({
        mutationFn: async (docId: number) => (await apiClient.post(`/kb/documents/${docId}/reingest`)).data,
        onSuccess: () => {
            message.success('Re-ingest queued');
            queryClient.invalidateQueries({ queryKey: ['kb_documents'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Re-ingest failed')
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
        { title: 'Title', dataIndex: 'title', key: 'title', render: (t: string) => <strong>{t}</strong> },
        { title: 'Namespace', dataIndex: 'namespace', key: 'namespace', render: (ns: string) => <Tag color="geekblue">{ns}</Tag> },
        {
            title: 'Status', dataIndex: 'ingest_status', key: 'ingest_status', render: (s: string, record: any) => {
                const color = s === 'ready' ? 'green' : s === 'failed' ? 'red' : s === 'processing' ? 'blue' : 'orange';
                const tag = <Tag color={color}>{s.toUpperCase()}</Tag>;
                if (s === 'failed' && record.error_message) {
                    return <Tooltip title={record.error_message}>{tag}</Tooltip>;
                }
                return tag;
            }
        },
        { title: 'Ver', dataIndex: 'version', key: 'version', width: 50 },
        { title: 'Type', dataIndex: 'content_type', key: 'content_type', width: 120 },
        { title: 'Source', dataIndex: 'source_id', key: 'source_id', width: 70 },
        {
            title: 'Actions', key: 'actions', width: 100,
            render: (_: any, record: any) => (
                role !== 'reader' ? (
                    <Tooltip title="Re-ingest">
                        <Button
                            size="small"
                            icon={<ReloadOutlined />}
                            onClick={() => reingest.mutate(record.id)}
                            loading={reingest.isPending}
                        />
                    </Tooltip>
                ) : null
            )
        },
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>Knowledge Base Documents</Title>
                {role !== 'reader' && (
                    <Space>
                        <Button onClick={() => setIsTextModalOpen(true)}>Ingest Text</Button>
                        <Button icon={<LinkOutlined />} onClick={() => setIsUrlModalOpen(true)}>Ingest URL</Button>
                        <Button type="primary" onClick={() => setIsFileModalOpen(true)} icon={<UploadOutlined />}>Upload File</Button>
                    </Space>
                )}
            </div>

            <Table dataSource={documents} columns={columns} rowKey="id" loading={isLoading} size="middle" />

            {/* Text Ingestion */}
            <Modal title="Ingest Raw Text" open={isTextModalOpen} onCancel={() => setIsTextModalOpen(false)} onOk={() => form.submit()} confirmLoading={ingestText.isPending} width={600}>
                <Form form={form} layout="vertical" onFinish={ingestText.mutate} initialValues={{ namespace: 'global' }}>
                    <Form.Item name="source_id" label="KB Source" rules={[{ required: true }]}>
                        <Select options={sources?.map((s: any) => ({ label: s.name, value: s.id }))} />
                    </Form.Item>
                    <Form.Item name="namespace" label="Namespace"><Input /></Form.Item>
                    <Form.Item name="title" label="Document Title" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="text" label="Content (Markdown/Text)" rules={[{ required: true }]}><TextArea rows={10} /></Form.Item>
                </Form>
            </Modal>

            {/* URL Ingestion */}
            <Modal title="Ingest from URL" open={isUrlModalOpen} onCancel={() => setIsUrlModalOpen(false)} onOk={() => urlForm.submit()} confirmLoading={ingestUrl.isPending} width={500}>
                <Form form={urlForm} layout="vertical" onFinish={ingestUrl.mutate} initialValues={{ namespace: 'global' }}>
                    <Form.Item name="source_id" label="KB Source" rules={[{ required: true }]}>
                        <Select options={sources?.map((s: any) => ({ label: s.name, value: s.id }))} />
                    </Form.Item>
                    <Form.Item name="url" label="URL" rules={[{ required: true, type: 'url', message: 'Enter a valid URL' }]}><Input placeholder="https://example.com/article" /></Form.Item>
                    <Form.Item name="namespace" label="Namespace"><Input /></Form.Item>
                    <Form.Item name="title" label="Document Title" rules={[{ required: true }]}><Input /></Form.Item>
                </Form>
            </Modal>

            {/* File Upload */}
            <Modal title="Upload Document File" open={isFileModalOpen} onCancel={() => setIsFileModalOpen(false)} footer={null}>
                <Form form={fileForm} layout="vertical" initialValues={{ namespace: 'global' }}>
                    <Form.Item name="source_id" label="KB Source" rules={[{ required: true }]}>
                        <Select options={sources?.map((s: any) => ({ label: s.name, value: s.id }))} />
                    </Form.Item>
                    <Form.Item name="namespace" label="Namespace"><Input /></Form.Item>
                    <Form.Item label="File">
                        <Upload
                            action={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/kb/documents/upload`}
                            headers={{ Authorization: `Bearer ${accessToken}` }}
                            data={(file) => ({
                                source_id: fileForm.getFieldValue('source_id'),
                                namespace: fileForm.getFieldValue('namespace'),
                                title: file.name
                            })}
                            onChange={(info) => {
                                if (info.file.status === 'done') {
                                    message.success(`${info.file.name} uploaded successfully`);
                                    setIsFileModalOpen(false);
                                    queryClient.invalidateQueries({ queryKey: ['kb_documents'] });
                                } else if (info.file.status === 'error') {
                                    message.error(`${info.file.name} upload failed.`);
                                }
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
