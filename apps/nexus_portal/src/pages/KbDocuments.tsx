import { Table, Button, Space, Tag, Modal, Form, Input, Select, Typography, message, Upload } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
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
    const [form] = Form.useForm();
    const [fileForm] = Form.useForm();

    const { data: documents, isLoading } = useQuery({
        queryKey: ['kb_documents'],
        queryFn: async () => (await apiClient.get('/kb/documents')).data
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

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: 'Title', dataIndex: 'title', key: 'title', render: (t: string) => <strong>{t}</strong> },
        { title: 'Namespace', dataIndex: 'namespace', key: 'namespace', render: (ns: string) => <Tag color="geekblue">{ns}</Tag> },
        {
            title: 'Status', dataIndex: 'ingest_status', key: 'ingest_status', render: (s: string) => {
                const color = s === 'ready' ? 'green' : s === 'failed' ? 'red' : 'orange';
                return <Tag color={color}>{s.toUpperCase()}</Tag>;
            }
        },
        { title: 'Chunks', dataIndex: 'chunk_count', key: 'chunk_count' },
        { title: 'Source ID', dataIndex: 'source_id', key: 'source_id' },
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>Knowledge Base Documents</Title>
                {role !== 'reader' && (
                    <Space>
                        <Button onClick={() => setIsTextModalOpen(true)}>Ingest Text</Button>
                        <Button type="primary" onClick={() => setIsFileModalOpen(true)}>Upload File</Button>
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

            {/* File Upload API Route is natively multipart, easier to rely on Antd Upload */}
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
