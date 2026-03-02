import { useState } from 'react';
import { Table, Button, Card, Space, Tag, Input, Typography, Tabs } from 'antd';
import { KeyOutlined, PlusOutlined, SearchOutlined, HistoryOutlined, SafetyOutlined, EditOutlined, SyncOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';

// Components
import SecretCreateModal from '../components/Secrets/SecretCreateModal';
import SecretEditModal from '../components/Secrets/SecretEditModal';
import SecretRotateModal from '../components/Secrets/SecretRotateModal';
import SecretRevealModal from '../components/Secrets/SecretRevealModal';
import SecretDeleteModal from '../components/Secrets/SecretDeleteModal';
import SecretAuditTable from '../components/Secrets/SecretAuditTable';

const { Title, Text } = Typography;

export default function Secrets() {
    const [searchQuery, setSearchQuery] = useState('');
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [editingSecret, setEditingSecret] = useState<any>(null);
    const [rotatingSecret, setRotatingSecret] = useState<any>(null);
    const [revealingSecret, setRevealingSecret] = useState<any>(null);
    const [deletingSecret, setDeletingSecret] = useState<any>(null);

    const queryClient = useQueryClient();

    const { data: secrets, isLoading } = useQuery({
        queryKey: ['portal-secrets'],
        queryFn: async () => {
            const resp = await apiClient.get('/portal/secrets');
            return resp.data;
        },
    });
    const columns = [
        {
            title: 'Alias',
            dataIndex: 'alias',
            key: 'alias',
            render: (text: string) => <Text strong>{text}</Text>,
        },
        {
            title: 'Tenant',
            dataIndex: 'tenant_id',
            key: 'tenant_id',
            render: (text: string) => <Tag color="blue">{text}</Tag>,
        },
        {
            title: 'Env',
            dataIndex: 'env',
            key: 'env',
            render: (text: string) => (
                <Tag color={text === 'prod' ? 'red' : text === 'stage' ? 'orange' : 'green'}>
                    {text.toUpperCase()}
                </Tag>
            ),
        },
        {
            title: 'Description',
            dataIndex: 'description',
            key: 'description',
            ellipsis: true,
        },
        {
            title: 'Last Used',
            dataIndex: 'last_used_at',
            key: 'last_used_at',
            sorter: (a: any, b: any) => {
                if (!a.last_used_at && !b.last_used_at) return 0;
                if (!a.last_used_at) return 1;
                if (!b.last_used_at) return -1;
                return new Date(a.last_used_at).getTime() - new Date(b.last_used_at).getTime();
            },
            render: (text: string) => text
                ? new Date(text).toLocaleString()
                : <Text type="secondary" italic>Never</Text>,
        },
        {
            title: 'Updated At',
            dataIndex: 'updated_at',
            key: 'updated_at',
            render: (text: string) => new Date(text).toLocaleString(),
        },
        {
            title: 'Actions',
            key: 'actions',
            render: (_: any, record: any) => (
                <Space size="middle">
                    <Button
                        type="primary"
                        icon={<SafetyOutlined />}
                        onClick={() => setRevealingSecret(record)}
                        danger
                        title="Reveal Secret"
                    />
                    <Button type="default" icon={<EditOutlined />} onClick={() => setEditingSecret(record)} title="Edit Meta" />
                    <Button type="default" icon={<SyncOutlined />} onClick={() => setRotatingSecret(record)} title="Rotate Value" />
                    <Button type="primary" icon={<DeleteOutlined />} onClick={() => setDeletingSecret(record)} danger title="Delete Secret" />
                </Space>
            ),
        },
    ];

    const filteredSecrets = secrets?.filter((s: any) =>
        s.alias.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.tenant_id.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div style={{ width: '100%' }}>
            <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'nowrap' }}>
                <Title level={2} style={{ margin: 0, whiteSpace: 'nowrap', flexShrink: 0 }}>Secrets & Credentials Management</Title>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsCreateModalOpen(true)}>
                    Add Secret
                </Button>
            </div>

            <Tabs defaultActiveKey="secrets">
                <Tabs.TabPane tab={<span><KeyOutlined />Secrets</span>} key="secrets">
                    <Card style={{ marginTop: 16 }}>
                        <div style={{ marginBottom: 16 }}>
                            <Input
                                placeholder="Search by alias or tenant..."
                                prefix={<SearchOutlined />}
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                style={{ width: 300 }}
                            />
                        </div>
                        <Table
                            columns={columns}
                            dataSource={filteredSecrets}
                            rowKey="id"
                            loading={isLoading}
                            scroll={{ x: 1200 }}
                        />
                    </Card>
                </Tabs.TabPane>
                <Tabs.TabPane tab={<span><HistoryOutlined />Audit Log</span>} key="audit">
                    <Card style={{ marginTop: 16 }}>
                        <SecretAuditTable />
                    </Card>
                </Tabs.TabPane>
            </Tabs>

            <SecretCreateModal
                open={isCreateModalOpen}
                onClose={() => setIsCreateModalOpen(false)}
                onSuccess={() => {
                    setIsCreateModalOpen(false);
                    queryClient.invalidateQueries({ queryKey: ['portal-secrets'] });
                }}
            />

            {editingSecret && (
                <SecretEditModal
                    secret={editingSecret}
                    open={!!editingSecret}
                    onClose={() => setEditingSecret(null)}
                    onSuccess={() => {
                        setEditingSecret(null);
                        queryClient.invalidateQueries({ queryKey: ['portal-secrets'] });
                    }}
                />
            )}

            {rotatingSecret && (
                <SecretRotateModal
                    secret={rotatingSecret}
                    open={!!rotatingSecret}
                    onClose={() => setRotatingSecret(null)}
                    onSuccess={() => {
                        setRotatingSecret(null);
                        queryClient.invalidateQueries({ queryKey: ['portal-secrets'] });
                    }}
                />
            )}

            {revealingSecret && (
                <SecretRevealModal
                    secret={revealingSecret}
                    open={!!revealingSecret}
                    onClose={() => setRevealingSecret(null)}
                />
            )}

            {deletingSecret && (
                <SecretDeleteModal
                    secret={deletingSecret}
                    open={!!deletingSecret}
                    onClose={() => setDeletingSecret(null)}
                    onSuccess={() => {
                        setDeletingSecret(null);
                        queryClient.invalidateQueries({ queryKey: ['portal-secrets'] });
                    }}
                />
            )}
        </div>
    );
}
