import { Table, Modal, Typography, Space, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';

const { Title, Text } = Typography;

export default function IntegrationsPbx() {
    const [selectedItem, setSelectedItem] = useState<any>(null);

    const { data, isLoading } = useQuery({
        queryKey: ['pbx_snapshots'],
        queryFn: async () => {
            try {
                return (await apiClient.get('/pbx/snapshots')).data;
            } catch (e: any) {
                if (e?.response?.status === 404) return [];
                throw e;
            }
        }
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: 'Task ID', dataIndex: 'task_id', key: 'task_id', render: (id: number) => <strong>{id}</strong> },
        { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'succeeded' ? 'green' : 'red'}>{s}</Tag> },
        { title: 'Target PBX ID', dataIndex: 'pbx_target_id', key: 'pbx_target_id' },
        { title: 'Created At', dataIndex: 'created_at', key: 'created_at', render: (date: string) => new Date(date).toLocaleString() },
        {
            title: 'Details', key: 'details', render: (_: any, record: any) => (
                <a onClick={() => setSelectedItem(record)}>View Summary</a>
            )
        }
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>PBX Snapshots (Read-Only)</Title>
            </div>

            <Table dataSource={data} columns={columns} rowKey="id" loading={isLoading} size="middle" />

            <Modal title={`Snapshot: ${selectedItem?.id}`} open={!!selectedItem} onCancel={() => setSelectedItem(null)} footer={null}>
                {selectedItem && (
                    <div>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Text strong>Status: <Tag>{selectedItem.status}</Tag></Text>
                            <Text strong>Summary Metrics:</Text>
                            <pre style={{ background: '#f5f5f5', padding: 10 }}>{JSON.stringify(selectedItem.summary, null, 2)}</pre>
                        </Space>
                    </div>
                )}
            </Modal>
        </div>
    );
}
