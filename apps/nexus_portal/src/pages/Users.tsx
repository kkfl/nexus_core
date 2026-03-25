import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';
import {
    Table, Button, Tag, Space, Modal, Form, Input, Select, Switch, message, Typography,
    Tooltip, Row, Col, Statistic, Badge, Drawer, Divider,
} from 'antd';
import {
    UserAddOutlined, EditOutlined, KeyOutlined, TeamOutlined,
    CrownOutlined, SafetyCertificateOutlined, EyeOutlined, LockOutlined,
} from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';
import { TiltCard } from '../components/TiltCard';

const { Title, Text } = Typography;

interface UserRecord {
    id: number;
    email: string;
    role: string;
    is_active: boolean;
    module_permissions: Record<string, string> | null;
    created_at: string;
}

const MODULE_LABELS: Record<string, string> = {
    dashboard: 'Dashboard',
    orchestration: 'Orchestration',
    personas: 'Personas',
    knowledge_base: 'Knowledge Base',
    entities: 'System of Record',
    secrets: 'Secrets & Credentials',
    audit: 'Audit Trail',
    pbx: 'PBX Fleet Management',
    monitoring: 'Monitoring',
    storage: 'Storage Jobs',
    carrier: 'Carrier Inventory',
    email: 'Email Admin',
    dns: 'DNS Management',
    servers: 'Servers',
    integrations: 'Service Integrations',
    users: 'User Management',
    api_keys: 'API Keys',
    ip_allowlist: 'IP Allowlist',
    backup: 'Backup & Restore',
};

const ALL_MODULES = Object.keys(MODULE_LABELS);

const ACCESS_OPTIONS = [
    { value: 'none', label: '⛔ None' },
    { value: 'read', label: '👁 Read' },
    { value: 'manage', label: '✏️ Manage' },
];

const ROLE_PRESETS: Record<string, Record<string, string>> = {
    admin: Object.fromEntries(ALL_MODULES.map(m => [m, m === 'audit' ? 'read' : 'manage'])),
    operator: {
        dashboard: 'read', orchestration: 'manage', personas: 'manage', knowledge_base: 'manage',
        entities: 'read', secrets: 'read', audit: 'read', pbx: 'manage', monitoring: 'manage',
        storage: 'manage', carrier: 'manage', email: 'manage', dns: 'manage', servers: 'manage',
        integrations: 'read', users: 'none', api_keys: 'none', ip_allowlist: 'none', backup: 'none',
    },
    reader: Object.fromEntries(ALL_MODULES.map(m =>
        [m, ['secrets', 'integrations', 'users', 'api_keys', 'ip_allowlist', 'backup'].includes(m) ? 'none' : 'read']
    )),
};

const roleColors: Record<string, string> = {
    admin: '#f5222d',
    operator: '#1890ff',
    reader: '#52c41a',
};

const roleIcons: Record<string, React.ReactNode> = {
    admin: <CrownOutlined />,
    operator: <SafetyCertificateOutlined />,
    reader: <EyeOutlined />,
};

export default function Users() {
    const queryClient = useQueryClient();
    const [createOpen, setCreateOpen] = useState(false);
    const [editUser, setEditUser] = useState<UserRecord | null>(null);
    const [resetUser, setResetUser] = useState<UserRecord | null>(null);
    const [permsUser, setPermsUser] = useState<UserRecord | null>(null);
    const [permsState, setPermsState] = useState<Record<string, string>>({});
    const [createForm] = Form.useForm();
    const [editForm] = Form.useForm();
    const [resetForm] = Form.useForm();
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    // ── Queries ──
    const { data: users = [], isLoading } = useQuery<UserRecord[]>({
        queryKey: ['users'],
        queryFn: () => apiClient.get('/users').then(r => r.data),
    });

    // ── Mutations ──
    const createMutation = useMutation({
        mutationFn: (values: { email: string; password: string; role: string }) =>
            apiClient.post('/users', values),
        onSuccess: () => {
            message.success('User created');
            queryClient.invalidateQueries({ queryKey: ['users'] });
            setCreateOpen(false);
            createForm.resetFields();
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, ...body }: { id: number; email?: string; role?: string; is_active?: boolean }) =>
            apiClient.patch(`/users/${id}`, body),
        onSuccess: () => {
            message.success('User updated');
            queryClient.invalidateQueries({ queryKey: ['users'] });
            setEditUser(null);
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    const resetMutation = useMutation({
        mutationFn: ({ id, new_password }: { id: number; new_password: string }) =>
            apiClient.post(`/users/${id}/reset-password`, { new_password }),
        onSuccess: () => {
            message.success('Password reset');
            setResetUser(null);
            resetForm.resetFields();
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    const permsMutation = useMutation({
        mutationFn: ({ id, module_permissions }: { id: number; module_permissions: Record<string, string> }) =>
            apiClient.patch(`/users/${id}/permissions`, { module_permissions }),
        onSuccess: () => {
            message.success('Permissions updated — user must re-login for changes to take effect');
            queryClient.invalidateQueries({ queryKey: ['users'] });
            setPermsUser(null);
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    // ── Stats ──
    const totalUsers = users.length;
    const activeUsers = users.filter(u => u.is_active).length;
    const adminCount = users.filter(u => u.role === 'admin').length;

    // ── Table ──
    const columns = [
        {
            title: 'Email',
            dataIndex: 'email',
            key: 'email',
            render: (email: string, record: UserRecord) => (
                <Space>
                    <Badge status={record.is_active ? 'success' : 'error'} />
                    <Text strong>{email}</Text>
                </Space>
            ),
        },
        {
            title: 'Role',
            dataIndex: 'role',
            key: 'role',
            width: 140,
            render: (role: string) => (
                <Tag
                    icon={roleIcons[role]}
                    color={roleColors[role]}
                    style={{ borderRadius: 12, padding: '2px 12px', fontWeight: 600 }}
                >
                    {role.toUpperCase()}
                </Tag>
            ),
        },
        {
            title: 'Status',
            dataIndex: 'is_active',
            key: 'is_active',
            width: 100,
            render: (active: boolean) => (
                <Tag color={active ? 'green' : 'default'}>{active ? 'Active' : 'Disabled'}</Tag>
            ),
        },
        {
            title: 'Created',
            dataIndex: 'created_at',
            key: 'created_at',
            width: 180,
            render: (d: string) => d ? new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '—',
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 120,
            render: (_: any, record: UserRecord) => (
                <Space>
                    <Tooltip title="Edit user">
                        <Button
                            type="text"
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => {
                                setEditUser(record);
                                editForm.setFieldsValue(record);
                            }}
                        />
                    </Tooltip>
                    <Tooltip title="Reset password">
                        <Button
                            type="text"
                            size="small"
                            icon={<KeyOutlined />}
                            onClick={() => setResetUser(record)}
                        />
                    </Tooltip>
                    <Tooltip title="Permissions">
                        <Button
                            type="text"
                            size="small"
                            icon={<LockOutlined />}
                            onClick={() => {
                                setPermsUser(record);
                                setPermsState(record.module_permissions ?? ROLE_PRESETS[record.role] ?? ROLE_PRESETS.reader);
                            }}
                        />
                    </Tooltip>
                </Space>
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
                        <TeamOutlined style={{ marginRight: 8, color: t.accent }} />
                        User Management
                    </Title>
                    <Text style={{ color: t.muted }}>Manage portal access, roles, and credentials</Text>
                </div>
                <Button type="primary" icon={<UserAddOutlined />} onClick={() => setCreateOpen(true)} size="large">Create User</Button>
            </div>

            {/* Stats */}
            <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={8}><TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.accent } as React.CSSProperties}><Statistic title={<Text style={{ color: t.muted }}>Total Users</Text>} value={totalUsers} prefix={<TeamOutlined />} valueStyle={{ color: t.text }} /></TiltCard></Col>
                <Col span={8}><TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.green } as React.CSSProperties}><Statistic title={<Text style={{ color: t.muted }}>Active Users</Text>} value={activeUsers} valueStyle={{ color: t.green }} /></TiltCard></Col>
                <Col span={8}><TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.red } as React.CSSProperties}><Statistic title={<Text style={{ color: t.muted }}>Administrators</Text>} value={adminCount} prefix={<CrownOutlined />} valueStyle={{ color: t.red }} /></TiltCard></Col>
            </Row>

            {/* Table */}
            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <Table
                    columns={columns}
                    dataSource={users}
                    rowKey="id"
                    loading={isLoading}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    size="middle"
                />
            </div>

            {/* Create Modal */}
            <Modal
                title="Create User"
                open={createOpen}
                onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
                onOk={() => createForm.submit()}
                confirmLoading={createMutation.isPending}
                okText="Create"
            >
                <Form
                    form={createForm}
                    layout="vertical"
                    onFinish={(v) => createMutation.mutate(v)}
                >
                    <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email' }]}>
                        <Input placeholder="user@company.com" />
                    </Form.Item>
                    <Form.Item name="password" label="Password" rules={[{ required: true, min: 8 }]}>
                        <Input.Password placeholder="Minimum 8 characters" />
                    </Form.Item>
                    <Form.Item name="role" label="Role" initialValue="reader">
                        <Select options={[
                            { value: 'admin', label: '🔴 Admin — Full access' },
                            { value: 'operator', label: '🔵 Operator — Daily operations' },
                            { value: 'reader', label: '🟢 Reader — View only' },
                        ]} />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Edit Modal */}
            <Modal
                title={`Edit User — ${editUser?.email}`}
                open={!!editUser}
                onCancel={() => setEditUser(null)}
                onOk={() => editForm.submit()}
                confirmLoading={updateMutation.isPending}
                okText="Save"
            >
                <Form
                    form={editForm}
                    layout="vertical"
                    onFinish={(v) => {
                        if (!v.password) delete v.password; // Don't send blank passwords
                        if (editUser) updateMutation.mutate({ id: editUser.id, ...v });
                    }}
                >
                    <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email' }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="role" label="Role">
                        <Select options={[
                            { value: 'admin', label: '🔴 Admin' },
                            { value: 'operator', label: '🔵 Operator' },
                            { value: 'reader', label: '🟢 Reader' },
                        ]} />
                    </Form.Item>
                    <Form.Item name="is_active" label="Active" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                    <Form.Item
                        name="password"
                        label="New Password"
                        rules={[{ min: 8, message: 'Minimum 8 characters' }]}
                        help="Leave blank to keep current password"
                    >
                        <Input.Password placeholder="Enter new password (optional)" />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Reset Password Modal */}
            <Modal
                title={`Reset Password — ${resetUser?.email}`}
                open={!!resetUser}
                onCancel={() => { setResetUser(null); resetForm.resetFields(); }}
                onOk={() => resetForm.submit()}
                confirmLoading={resetMutation.isPending}
                okText="Reset Password"
            >
                <Form
                    form={resetForm}
                    layout="vertical"
                    onFinish={(v) => resetUser && resetMutation.mutate({ id: resetUser.id, ...v })}
                >
                    <Form.Item name="new_password" label="New Password" rules={[{ required: true, min: 8 }]}>
                        <Input.Password placeholder="Minimum 8 characters" />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Permissions Drawer */}
            <Drawer
                title={<Space><LockOutlined /> Module Permissions — {permsUser?.email}</Space>}
                open={!!permsUser}
                onClose={() => setPermsUser(null)}
                width={520}
                footer={
                    <div style={{ textAlign: 'right' }}>
                        <Button onClick={() => setPermsUser(null)} style={{ marginRight: 8 }}>Cancel</Button>
                        <Button
                            type="primary"
                            loading={permsMutation.isPending}
                            onClick={() => permsUser && permsMutation.mutate({ id: permsUser.id, module_permissions: permsState })}
                        >Save Permissions</Button>
                    </div>
                }
            >
                {permsUser?.role === 'admin' && (
                    <div style={{ padding: '8px 12px', marginBottom: 16, background: 'rgba(245,34,45,0.08)', borderRadius: 8, border: '1px solid rgba(245,34,45,0.2)' }}>
                        <Text style={{ color: '#f5222d', fontSize: 12 }}>
                            <CrownOutlined /> Admin users always have full access regardless of these settings.
                        </Text>
                    </div>
                )}

                <Space style={{ marginBottom: 16 }}>
                    <Text strong style={{ color: t.muted, fontSize: 11 }}>PRESETS:</Text>
                    <Button size="small" onClick={() => setPermsState({ ...ROLE_PRESETS.admin })}>All Manage</Button>
                    <Button size="small" onClick={() => setPermsState({ ...ROLE_PRESETS.operator })}>Operator</Button>
                    <Button size="small" onClick={() => setPermsState({ ...ROLE_PRESETS.reader })}>Reader</Button>
                    <Button size="small" danger onClick={() => setPermsState(Object.fromEntries(ALL_MODULES.map(m => [m, 'none'])))}>None</Button>
                </Space>

                <Divider style={{ margin: '8px 0 16px' }} />

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px', gap: '8px 12px', alignItems: 'center' }}>
                    {ALL_MODULES.map(mod => (
                        <>
                            <Text key={`label-${mod}`} style={{ color: t.text, fontSize: 13 }}>{MODULE_LABELS[mod]}</Text>
                            <Select
                                key={`select-${mod}`}
                                size="small"
                                value={permsState[mod] ?? 'none'}
                                onChange={(val) => setPermsState(prev => ({ ...prev, [mod]: val }))}
                                options={ACCESS_OPTIONS}
                                style={{ width: '100%' }}
                            />
                        </>
                    ))}
                </div>
            </Drawer>
        </div>
    );
}
