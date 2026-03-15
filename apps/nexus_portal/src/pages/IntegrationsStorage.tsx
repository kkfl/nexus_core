import { Table, Modal, Typography, Space, Tag, Button, Tabs, Form, Input, Select, Switch, message, Row, Col, Statistic, Tooltip, Badge } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';
import {
    HddOutlined, PlusOutlined, EditOutlined, ApiOutlined, CheckCircleOutlined,
    CloudServerOutlined, DatabaseOutlined,
} from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text } = Typography;

interface StorageTarget {
    id: string;
    name: string;
    description: string | null;
    kind: string;
    endpoint_url: string;
    region: string | null;
    bucket: string;
    base_prefix: string;
    is_active: boolean;
    tags: string[] | null;
    created_at: string;
}

interface StorageJob {
    id: string;
    storage_target_id: string;
    task_id: number;
    kind: string;
    status: string;
    summary: Record<string, any> | null;
    created_at: string;
}

export default function IntegrationsStorage() {
    const queryClient = useQueryClient();
    const { mode } = useThemeStore();
    const t = getTokens(mode);
    const [selectedJob, setSelectedJob] = useState<StorageJob | null>(null);
    const [createOpen, setCreateOpen] = useState(false);
    const [editTarget, setEditTarget] = useState<StorageTarget | null>(null);
    const [createForm] = Form.useForm();
    const [editForm] = Form.useForm();

    // ── Queries ──
    const { data: targets = [], isLoading: targetsLoading } = useQuery<StorageTarget[]>({
        queryKey: ['storage_targets'],
        queryFn: async () => {
            try { return (await apiClient.get('/storage/targets')).data; }
            catch (e: any) { if (e?.response?.status === 404) return []; throw e; }
        },
    });

    const { data: jobs = [], isLoading: jobsLoading } = useQuery<StorageJob[]>({
        queryKey: ['storage_jobs'],
        queryFn: async () => {
            try { return (await apiClient.get('/storage/jobs')).data; }
            catch (e: any) { if (e?.response?.status === 404) return []; throw e; }
        },
    });

    // ── Mutations ──
    const createMutation = useMutation({
        mutationFn: (values: any) => apiClient.post('/storage/targets', values),
        onSuccess: () => {
            message.success('Storage target created');
            queryClient.invalidateQueries({ queryKey: ['storage_targets'] });
            setCreateOpen(false);
            createForm.resetFields();
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed to create target'),
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, ...body }: any) => apiClient.patch(`/storage/targets/${id}`, body),
        onSuccess: () => {
            message.success('Storage target updated');
            queryClient.invalidateQueries({ queryKey: ['storage_targets'] });
            setEditTarget(null);
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed to update'),
    });

    const testMutation = useMutation({
        mutationFn: (targetId: string) => apiClient.post(`/storage/targets/${targetId}/test`),
        onSuccess: (res) => {
            message.success(`Test queued — Task #${res.data.task_id}`);
            queryClient.invalidateQueries({ queryKey: ['storage_jobs'] });
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Test failed'),
    });

    // ── Stats ──
    const totalTargets = targets.length;
    const activeTargets = targets.filter(t => t.is_active).length;
    const totalJobs = jobs.length;

    // ── Target name lookup for jobs table ──
    const targetNameMap = Object.fromEntries(targets.map(t => [t.id, t.name]));

    // ── Targets Table ──
    const targetColumns = [
        {
            title: 'Name', dataIndex: 'name', key: 'name',
            render: (name: string, record: StorageTarget) => (
                <Space>
                    <Badge status={record.is_active ? 'success' : 'error'} />
                    <Text strong>{name}</Text>
                </Space>
            ),
        },
        {
            title: 'Endpoint', dataIndex: 'endpoint_url', key: 'endpoint_url',
            render: (url: string) => <Text copyable style={{ fontSize: 12 }}>{url}</Text>,
        },
        {
            title: 'Bucket', dataIndex: 'bucket', key: 'bucket',
            render: (b: string) => <Tag color="blue">{b}</Tag>,
        },
        {
            title: 'Type', dataIndex: 'kind', key: 'kind', width: 80,
            render: (k: string) => <Tag color="geekblue">{k.toUpperCase()}</Tag>,
        },
        {
            title: 'Status', dataIndex: 'is_active', key: 'is_active', width: 90,
            render: (active: boolean) => <Tag color={active ? 'green' : 'default'}>{active ? 'Active' : 'Disabled'}</Tag>,
        },
        {
            title: 'Created', dataIndex: 'created_at', key: 'created_at', width: 140,
            render: (d: string) => d ? new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '—',
        },
        {
            title: 'Actions', key: 'actions', width: 120,
            render: (_: any, record: StorageTarget) => (
                <Space>
                    <Tooltip title="Edit target">
                        <Button type="text" size="small" icon={<EditOutlined />}
                            onClick={() => { setEditTarget(record); editForm.setFieldsValue(record); }}
                        />
                    </Tooltip>
                    <Tooltip title="Test connectivity">
                        <Button type="text" size="small" icon={<ApiOutlined />}
                            loading={testMutation.isPending}
                            onClick={() => testMutation.mutate(record.id)}
                        />
                    </Tooltip>
                </Space>
            ),
        },
    ];

    // ── Jobs Table ──
    const jobColumns = [
        {
            title: 'Target', dataIndex: 'storage_target_id', key: 'target',
            render: (id: string) => <Text strong>{targetNameMap[id] || id.slice(0, 8)}</Text>,
        },
        { title: 'Task ID', dataIndex: 'task_id', key: 'task_id', width: 80, render: (id: number) => <strong>#{id}</strong> },
        { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (k: string) => <Tag color="blue">{k}</Tag> },
        {
            title: 'Status', dataIndex: 'status', key: 'status',
            render: (s: string) => <Tag color={s === 'succeeded' ? 'green' : s === 'failed' ? 'red' : 'orange'}>{s}</Tag>,
        },
        {
            title: 'Created', dataIndex: 'created_at', key: 'created_at', width: 160,
            render: (d: string) => new Date(d).toLocaleString(),
        },
        {
            title: 'Details', key: 'details', width: 100,
            render: (_: any, record: StorageJob) => (
                <a onClick={() => setSelectedJob(record)}>View</a>
            ),
        },
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: t.text }}>
                        <HddOutlined style={{ marginRight: 8, color: t.accent }} />
                        Storage Administration
                    </Title>
                    <Text style={{ color: t.muted }}>Manage S3-compatible storage targets (MinIO, Synology, etc.)</Text>
                </div>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)} size="large">
                    Add Storage Target
                </Button>
            </div>

            {/* Stats */}
            <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={8}><div style={{ ...cardStyle(t), padding: 16 }}><Statistic title={<Text style={{ color: t.muted }}>Storage Targets</Text>} value={totalTargets} prefix={<CloudServerOutlined />} valueStyle={{ color: t.text }} /></div></Col>
                <Col span={8}><div style={{ ...cardStyle(t), padding: 16 }}><Statistic title={<Text style={{ color: t.muted }}>Active Targets</Text>} value={activeTargets} valueStyle={{ color: t.green }} prefix={<CheckCircleOutlined />} /></div></Col>
                <Col span={8}><div style={{ ...cardStyle(t), padding: 16 }}><Statistic title={<Text style={{ color: t.muted }}>Total Jobs</Text>} value={totalJobs} prefix={<DatabaseOutlined />} valueStyle={{ color: t.text }} /></div></Col>
            </Row>

            {/* Tabs */}
            <Tabs defaultActiveKey="targets" items={[
                {
                    key: 'targets',
                    label: <span><CloudServerOutlined /> Storage Targets</span>,
                    children: (
                        <Table
                            columns={targetColumns}
                            dataSource={targets}
                            rowKey="id"
                            loading={targetsLoading}
                            pagination={{ pageSize: 20, showSizeChanger: false }}
                            size="middle"
                        />
                    ),
                },
                {
                    key: 'jobs',
                    label: <span><DatabaseOutlined /> Storage Jobs</span>,
                    children: (
                        <Table
                            columns={jobColumns}
                            dataSource={jobs}
                            rowKey="id"
                            loading={jobsLoading}
                            pagination={{ pageSize: 20, showSizeChanger: false }}
                            size="middle"
                        />
                    ),
                },
            ]} />

            {/* Create Target Modal */}
            <Modal
                title="Add Storage Target"
                open={createOpen}
                onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
                onOk={() => createForm.submit()}
                confirmLoading={createMutation.isPending}
                okText="Add Target"
                width={600}
            >
                <Form form={createForm} layout="vertical" onFinish={(v) => createMutation.mutate(v)}>
                    <Row gutter={16}>
                        <Col span={16}>
                            <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                                <Input placeholder="e.g. synology-nas-01" />
                            </Form.Item>
                        </Col>
                        <Col span={8}>
                            <Form.Item name="kind" label="Type" initialValue="s3">
                                <Select options={[{ value: 's3', label: 'S3 Compatible' }]} />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Form.Item name="description" label="Description">
                        <Input placeholder="e.g. Synology DS920+ — backup storage" />
                    </Form.Item>
                    <Row gutter={16}>
                        <Col span={16}>
                            <Form.Item name="endpoint_url" label="Endpoint URL" rules={[{ required: true }]}>
                                <Input placeholder="http://192.168.1.100:9000" />
                            </Form.Item>
                        </Col>
                        <Col span={8}>
                            <Form.Item name="region" label="Region">
                                <Input placeholder="us-east-1" />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Row gutter={16}>
                        <Col span={12}>
                            <Form.Item name="bucket" label="Bucket" rules={[{ required: true }]}>
                                <Input placeholder="nexus-backups" />
                            </Form.Item>
                        </Col>
                        <Col span={12}>
                            <Form.Item name="base_prefix" label="Base Prefix" initialValue="">
                                <Input placeholder="optional/prefix/" />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Row gutter={16}>
                        <Col span={12}>
                            <Form.Item name="access_key_id" label="Access Key ID" rules={[{ required: true }]}>
                                <Input placeholder="minio-access-key" />
                            </Form.Item>
                        </Col>
                        <Col span={12}>
                            <Form.Item name="secret_access_key" label="Secret Access Key" rules={[{ required: true }]}>
                                <Input.Password placeholder="minio-secret-key" />
                            </Form.Item>
                        </Col>
                    </Row>
                </Form>
            </Modal>

            {/* Edit Target Modal */}
            <Modal
                title={`Edit Target — ${editTarget?.name}`}
                open={!!editTarget}
                onCancel={() => setEditTarget(null)}
                onOk={() => editForm.submit()}
                confirmLoading={updateMutation.isPending}
                okText="Save"
                width={600}
            >
                <Form form={editForm} layout="vertical"
                    onFinish={(v) => editTarget && updateMutation.mutate({ id: editTarget.id, ...v })}
                >
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                        <Input />
                    </Form.Item>
                    <Row gutter={16}>
                        <Col span={16}>
                            <Form.Item name="endpoint_url" label="Endpoint URL">
                                <Input />
                            </Form.Item>
                        </Col>
                        <Col span={8}>
                            <Form.Item name="region" label="Region">
                                <Input />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Row gutter={16}>
                        <Col span={12}>
                            <Form.Item name="bucket" label="Bucket">
                                <Input />
                            </Form.Item>
                        </Col>
                        <Col span={12}>
                            <Form.Item name="base_prefix" label="Base Prefix">
                                <Input />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Form.Item name="is_active" label="Active" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Job Detail Modal */}
            <Modal title={`Storage Job: ${selectedJob?.id?.slice(0, 8)}`} open={!!selectedJob} onCancel={() => setSelectedJob(null)} footer={null}>
                {selectedJob && (
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Text><strong>Target:</strong> {targetNameMap[selectedJob.storage_target_id] || selectedJob.storage_target_id}</Text>
                        <Text><strong>Kind:</strong> <Tag color="blue">{selectedJob.kind}</Tag></Text>
                        <Text><strong>Status:</strong> <Tag color={selectedJob.status === 'succeeded' ? 'green' : 'red'}>{selectedJob.status}</Tag></Text>
                        <Text strong>Summary:</Text>
                        <pre style={{ background: t.bg, padding: 12, borderRadius: 8, fontSize: 12, color: t.text, border: `1px solid ${t.border}` }}>
                            {JSON.stringify(selectedJob.summary, null, 2)}
                        </pre>
                    </Space>
                )}
            </Modal>
        </div>
    );
}
