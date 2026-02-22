import { Table, Space, Tag, Modal, Typography, Collapse, Input, Select } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';

const { Title, Text } = Typography;
const { Search } = Input;

export default function Entities() {
    const [selectedEntity, setSelectedEntity] = useState<any>(null);
    const [kindFilter, setKindFilter] = useState<string>('');

    const { data: entities, isLoading } = useQuery({
        queryKey: ['entities', kindFilter],
        queryFn: async () => {
            const qs = kindFilter ? `?kind=${kindFilter}` : '';
            return (await apiClient.get(`/entities${qs}`)).data;
        }
    });

    const getEvents = useQuery({
        queryKey: ['entity_events', selectedEntity?.id],
        queryFn: async () => (await apiClient.get(`/entities/${selectedEntity?.id}/events`)).data,
        enabled: !!selectedEntity
    });

    const columns = [
        { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (k: string) => <Tag color="blue">{k}</Tag> },
        { title: 'External Ref', dataIndex: 'external_ref', key: 'external_ref' },
        { title: 'Version', dataIndex: 'version', key: 'version' },
        { title: 'Updated', dataIndex: 'updated_at', key: 'updated_at', render: (date: string) => new Date(date).toLocaleString() },
        {
            title: 'Actions', key: 'actions', render: (_: any, record: any) => (
                <a onClick={() => setSelectedEntity(record)}>View State & History</a>
            )
        }
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>Canonical System of Record</Title>
                <Space>
                    <Input placeholder="Filter by Kind..." allowClear onChange={(e) => setKindFilter(e.target.value)} style={{ width: 250 }} />
                </Space>
            </div>

            <Table dataSource={entities} columns={columns} rowKey="id" loading={isLoading} size="middle" />

            <Modal title={`Entity: ${selectedEntity?.kind} (${selectedEntity?.external_ref})`} open={!!selectedEntity} onCancel={() => setSelectedEntity(null)} footer={null} width={900}>
                <Collapse defaultActiveKey={['current']} items={[
                    {
                        key: 'current',
                        label: `Current State (Version ${selectedEntity?.version})`,
                        children: <pre style={{ background: '#f5f5f5', padding: 10 }}>{JSON.stringify(selectedEntity?.data, null, 2)}</pre>
                    },
                    {
                        key: 'history',
                        label: 'Append-Only History Logs',
                        children: (
                            <Table
                                dataSource={getEvents.data}
                                loading={getEvents.isLoading}
                                rowKey="id"
                                size="small"
                                expandable={{
                                    expandedRowRender: (record: any) => (
                                        <div style={{ display: 'flex', gap: 16 }}>
                                            <div style={{ flex: 1 }}>
                                                <Text strong>Before Change:</Text>
                                                <pre style={{ background: '#f5f5f5', padding: 10 }}>{JSON.stringify(record.data_before, null, 2)}</pre>
                                            </div>
                                            <div style={{ flex: 1 }}>
                                                <Text strong>After Change:</Text>
                                                <pre style={{ background: '#e6f7ff', padding: 10, border: '1px solid #91d5ff' }}>{JSON.stringify(record.data_after, null, 2)}</pre>
                                            </div>
                                        </div>
                                    )
                                }}
                                columns={[
                                    { title: 'Action', dataIndex: 'action', key: 'action' },
                                    { title: 'Timestamp', dataIndex: 'created_at', key: 'created_at', render: (d: string) => new Date(d).toLocaleString() },
                                ]}
                            />
                        )
                    }
                ]} />
            </Modal>
        </div>
    );
}
