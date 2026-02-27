import { Table, Button, Modal, Form, Input, Typography, Space, Tag, Card, message, Tooltip, Row, Col, Statistic } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { emailClient } from '../api/emailClient';
import { useState } from 'react';
import {
    MailOutlined,
    PlusOutlined,
    LockOutlined,
    StopOutlined,
    LinkOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
    ReloadOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;

interface Mailbox {
    email: string;
    domain: string;
    active: number;
    quota: number;
    created: string;
}

interface HealthStatus {
    smtp: string;
    imap: string;
    ssh_bridge: string;
    smtp_detail: string | null;
    imap_detail: string | null;
    ssh_detail: string | null;
}

export default function IntegrationsEmail() {
    const queryClient = useQueryClient();
    const [createOpen, setCreateOpen] = useState(false);
    const [passwordOpen, setPasswordOpen] = useState(false);
    const [aliasOpen, setAliasOpen] = useState(false);
    const [selectedEmail, setSelectedEmail] = useState('');
    const [createForm] = Form.useForm();
    const [passwordForm] = Form.useForm();
    const [aliasForm] = Form.useForm();

    // Health
    const { data: health, isLoading: healthLoading, refetch: refetchHealth } = useQuery<HealthStatus>({
        queryKey: ['email_health'],
        queryFn: async () => (await emailClient.get('/email/health')).data,
        refetchInterval: 30000,
    });

    // Mailbox list
    const { data: mailboxes, isLoading } = useQuery<Mailbox[]>({
        queryKey: ['email_mailboxes'],
        queryFn: async () => (await emailClient.get('/email/admin/mailbox/list')).data,
    });

    // Mutations
    const createMutation = useMutation({
        mutationFn: async (values: { email: string; password: string }) =>
            (await emailClient.post('/email/admin/mailbox/create', values)).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Mailbox ${data.email} ${data.action}`);
                queryClient.invalidateQueries({ queryKey: ['email_mailboxes'] });
                setCreateOpen(false);
                createForm.resetFields();
            } else {
                message.error(data.error || 'Creation failed');
            }
        },
        onError: () => message.error('Request failed'),
    });

    const passwordMutation = useMutation({
        mutationFn: async (values: { email: string; password: string }) =>
            (await emailClient.post('/email/admin/mailbox/password', values)).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Password updated for ${data.email}`);
                setPasswordOpen(false);
                passwordForm.resetFields();
            } else {
                message.error(data.error || 'Password update failed');
            }
        },
        onError: () => message.error('Request failed'),
    });

    const disableMutation = useMutation({
        mutationFn: async (email: string) =>
            (await emailClient.post('/email/admin/mailbox/disable', { email })).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Mailbox ${data.email} ${data.action}`);
                queryClient.invalidateQueries({ queryKey: ['email_mailboxes'] });
            } else {
                message.error(data.error || 'Disable failed');
            }
        },
        onError: () => message.error('Request failed'),
    });

    const aliasMutation = useMutation({
        mutationFn: async (values: { alias: string; destination: string }) =>
            (await emailClient.post('/email/admin/alias/add', values)).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Alias ${data.alias} → ${data.destination} ${data.action}`);
                setAliasOpen(false);
                aliasForm.resetFields();
            } else {
                message.error(data.error || 'Alias creation failed');
            }
        },
        onError: () => message.error('Request failed'),
    });

    // Stats
    const activeCount = mailboxes?.filter(m => m.active === 1).length || 0;
    const disabledCount = mailboxes?.filter(m => m.active === 0).length || 0;
    const domains = [...new Set(mailboxes?.map(m => m.domain) || [])];

    const statusIcon = (status: string) =>
        status === 'ok'
            ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
            : <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;

    const columns = [
        {
            title: 'Email',
            dataIndex: 'email',
            key: 'email',
            sorter: (a: Mailbox, b: Mailbox) => a.email.localeCompare(b.email),
            render: (email: string) => <Text strong><MailOutlined style={{ marginRight: 6 }} />{email}</Text>,
        },
        {
            title: 'Domain',
            dataIndex: 'domain',
            key: 'domain',
            filters: domains.map(d => ({ text: d, value: d })),
            onFilter: (value: any, record: Mailbox) => record.domain === value,
        },
        {
            title: 'Status',
            dataIndex: 'active',
            key: 'active',
            width: 100,
            render: (active: number) => (
                <Tag color={active === 1 ? 'green' : 'red'}>
                    {active === 1 ? 'Active' : 'Disabled'}
                </Tag>
            ),
            filters: [{ text: 'Active', value: 1 }, { text: 'Disabled', value: 0 }],
            onFilter: (value: any, record: Mailbox) => record.active === value,
        },
        {
            title: 'Quota (MB)',
            dataIndex: 'quota',
            key: 'quota',
            width: 100,
            render: (q: number) => q > 0 ? `${q}` : '—',
        },
        {
            title: 'Created',
            dataIndex: 'created',
            key: 'created',
            width: 180,
            render: (date: string) => date ? new Date(date).toLocaleDateString() : '—',
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 200,
            render: (_: any, record: Mailbox) => (
                <Space>
                    <Tooltip title="Reset Password">
                        <Button
                            size="small"
                            icon={<LockOutlined />}
                            onClick={() => { setSelectedEmail(record.email); passwordForm.setFieldsValue({ email: record.email }); setPasswordOpen(true); }}
                        />
                    </Tooltip>
                    {record.active === 1 && (
                        <Tooltip title="Disable">
                            <Button
                                size="small"
                                danger
                                icon={<StopOutlined />}
                                onClick={() => Modal.confirm({
                                    title: `Disable ${record.email}?`,
                                    content: 'This will prevent the mailbox from receiving new mail.',
                                    okText: 'Disable',
                                    okType: 'danger',
                                    onOk: () => disableMutation.mutate(record.email),
                                })}
                            />
                        </Tooltip>
                    )}
                </Space>
            ),
        },
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <Title level={3} style={{ margin: 0 }}>Email Administration</Title>
                <Space>
                    <Button icon={<LinkOutlined />} onClick={() => setAliasOpen(true)}>Add Alias</Button>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>Create Mailbox</Button>
                </Space>
            </div>

            {/* Health + Stats */}
            <Row gutter={16} style={{ marginBottom: 20 }}>
                <Col span={6}>
                    <Card size="small">
                        <Statistic title="Total Mailboxes" value={mailboxes?.length || 0} prefix={<MailOutlined />} />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card size="small">
                        <Statistic title="Active" value={activeCount} valueStyle={{ color: '#3f8600' }} />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card size="small">
                        <Statistic title="Disabled" value={disabledCount} valueStyle={{ color: disabledCount > 0 ? '#cf1322' : undefined }} />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card size="small" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                        <Space direction="vertical" size={2}>
                            <Space>{statusIcon(health?.smtp || 'error')} <Text>SMTP</Text></Space>
                            <Space>{statusIcon(health?.imap || 'error')} <Text>IMAP</Text></Space>
                            <Space>{statusIcon(health?.ssh_bridge || 'error')} <Text>SSH Bridge</Text></Space>
                        </Space>
                        <Button type="link" size="small" icon={<ReloadOutlined />} onClick={() => refetchHealth()} loading={healthLoading} style={{ padding: 0, marginTop: 4 }}>
                            Refresh
                        </Button>
                    </Card>
                </Col>
            </Row>

            {/* Mailbox Table */}
            <Table
                dataSource={mailboxes}
                columns={columns}
                rowKey="email"
                loading={isLoading}
                size="middle"
                pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `${total} mailboxes` }}
            />

            {/* Create Mailbox Modal */}
            <Modal
                title="Create Mailbox"
                open={createOpen}
                onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
                onOk={() => createForm.submit()}
                confirmLoading={createMutation.isPending}
            >
                <Form form={createForm} layout="vertical" onFinish={(values) => createMutation.mutate(values)}>
                    <Form.Item name="email" label="Email Address" rules={[{ required: true, type: 'email' }]}>
                        <Input placeholder="user@gsmcall.com" prefix={<MailOutlined />} />
                    </Form.Item>
                    <Form.Item name="password" label="Password" rules={[{ required: true, min: 8 }]}>
                        <Input.Password placeholder="Minimum 8 characters" prefix={<LockOutlined />} />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Reset Password Modal */}
            <Modal
                title={`Reset Password: ${selectedEmail}`}
                open={passwordOpen}
                onCancel={() => { setPasswordOpen(false); passwordForm.resetFields(); }}
                onOk={() => passwordForm.submit()}
                confirmLoading={passwordMutation.isPending}
            >
                <Form form={passwordForm} layout="vertical" onFinish={(values) => passwordMutation.mutate(values)}>
                    <Form.Item name="email" hidden><Input /></Form.Item>
                    <Form.Item name="password" label="New Password" rules={[{ required: true, min: 8 }]}>
                        <Input.Password placeholder="New password" prefix={<LockOutlined />} />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Add Alias Modal */}
            <Modal
                title="Add Mail Alias"
                open={aliasOpen}
                onCancel={() => { setAliasOpen(false); aliasForm.resetFields(); }}
                onOk={() => aliasForm.submit()}
                confirmLoading={aliasMutation.isPending}
            >
                <Form form={aliasForm} layout="vertical" onFinish={(values) => aliasMutation.mutate(values)}>
                    <Form.Item name="alias" label="Alias Address" rules={[{ required: true, type: 'email' }]}>
                        <Input placeholder="alias@gsmcall.com" prefix={<MailOutlined />} />
                    </Form.Item>
                    <Form.Item name="destination" label="Destination Address" rules={[{ required: true, type: 'email' }]}>
                        <Input placeholder="real@gsmcall.com" prefix={<MailOutlined />} />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
