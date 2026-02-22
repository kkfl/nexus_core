import { Table, Modal, Typography, Space } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';

const { Title, Text } = Typography;

export default function Audits() {
    const [selectedAudit, setSelectedAudit] = useState<any>(null);

    const { data: audits, isLoading } = useQuery({
        queryKey: ['audits'],
        queryFn: async () => (await apiClient.get('/audits?limit=100')).data
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: 'Actor', key: 'actor', render: (_: any, r: any) => <Space><Text strong>{r.actor_type}</Text><Text type="secondary">{r.actor_id}</Text></Space> },
        { title: 'Action', dataIndex: 'action', key: 'action', render: (a: string) => <strong style={{ color: 'purple' }}>{a}</strong> },
        { title: 'Target', key: 'target', render: (_: any, r: any) => <Space><Text strong>{r.target_type}</Text><Text type="secondary">{r.target_id}</Text></Space> },
        { title: 'Timestamp', dataIndex: 'created_at', key: 'created_at', render: (date: string) => new Date(date).toLocaleString() },
        {
            title: 'Details', key: 'details', render: (_: any, record: any) => (
                <a onClick={() => setSelectedAudit(record)}>View Meta</a>
            )
        }
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>System Audit Trail</Title>
            </div>

            <Table dataSource={audits} columns={columns} rowKey="id" loading={isLoading} size="middle" />

            <Modal title={`Audit Event ${selectedAudit?.id}: ${selectedAudit?.action}`} open={!!selectedAudit} onCancel={() => setSelectedAudit(null)} footer={null}>
                {selectedAudit && (
                    <div>
                        <pre style={{ background: '#f5f5f5', padding: 10 }}>{JSON.stringify(selectedAudit.meta_data, null, 2)}</pre>
                    </div>
                )}
            </Modal>
        </div>
    );
}
