import { Table, Modal, Typography, Space, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';
import { SafetyOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text } = Typography;

export default function Audits() {
    const [selectedAudit, setSelectedAudit] = useState<any>(null);
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const { data: audits, isLoading } = useQuery({
        queryKey: ['audits'],
        queryFn: async () => (await apiClient.get('/audit/?limit=100')).data
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
        { title: 'Actor', key: 'actor', render: (_: any, r: any) => <Space><Text style={{ color: t.cyan, fontWeight: 600 }}>{r.actor_type}</Text><Text style={{ color: t.muted }}>{r.actor_id}</Text></Space> },
        { title: 'Action', dataIndex: 'action', key: 'action', render: (a: string) => <Tag style={{ background: `${t.purple}18`, color: t.purple, border: `1px solid ${t.purple}40` }}>{a}</Tag> },
        { title: 'Target', key: 'target', render: (_: any, r: any) => <Space><Text style={{ color: t.text, fontWeight: 600 }}>{r.target_type}</Text><Text style={{ color: t.muted }}>{r.target_id || ''}</Text></Space> },
        { title: 'Timestamp', dataIndex: 'created_at', key: 'created_at', render: (date: string) => <Text style={{ color: t.muted, fontSize: 12 }}><ClockCircleOutlined style={{ marginRight: 4 }} />{new Date(date).toLocaleString()}</Text> },
        {
            title: 'Details', key: 'details', render: (_: any, record: any) => (
                <a onClick={() => setSelectedAudit(record)} style={{ color: t.accent }}>View Meta</a>
            )
        }
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ marginBottom: 20 }}>
                <Title level={3} style={{ margin: 0, color: t.text }}>
                    <SafetyOutlined style={{ marginRight: 10, color: t.accent }} />
                    System Audit Trail
                </Title>
                <Text style={{ color: t.muted }}>Complete record of all system modifications</Text>
            </div>

            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <Table dataSource={audits} columns={columns} rowKey="id" loading={isLoading} size="middle" />
            </div>

            <Modal title={`Audit Event ${selectedAudit?.id}: ${selectedAudit?.action}`} open={!!selectedAudit} onCancel={() => setSelectedAudit(null)} footer={null}>
                {selectedAudit && (
                    <pre style={{ background: t.bg, padding: 12, borderRadius: 8, border: `1px solid ${t.border}`, color: t.text, fontSize: 12 }}>
                        {JSON.stringify(selectedAudit.meta_data, null, 2)}
                    </pre>
                )}
            </Modal>
        </div>
    );
}
