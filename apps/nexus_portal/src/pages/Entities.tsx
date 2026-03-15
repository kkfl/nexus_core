import { Table, Space, Tag, Modal, Typography, Collapse, Input } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';
import { AppstoreOutlined } from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text } = Typography;

export default function Entities() {
    const [selectedEntity, setSelectedEntity] = useState<any>(null);
    const [kindFilter, setKindFilter] = useState<string>('');
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const { data: entities, isLoading } = useQuery({
        queryKey: ['entities', kindFilter],
        queryFn: async () => { const qs = kindFilter ? `?kind=${kindFilter}` : ''; return (await apiClient.get(`/entities${qs}`)).data; }
    });

    const getEvents = useQuery({
        queryKey: ['entity_events', selectedEntity?.id],
        queryFn: async () => (await apiClient.get(`/entities/${selectedEntity?.id}/events`)).data,
        enabled: !!selectedEntity
    });

    const columns = [
        { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (k: string) => <Tag style={{ background: `${t.accent}18`, color: t.accent, border: `1px solid ${t.accent}40` }}>{k}</Tag> },
        { title: 'External Ref', dataIndex: 'external_ref', key: 'external_ref' },
        { title: 'Version', dataIndex: 'version', key: 'version' },
        { title: 'Updated', dataIndex: 'updated_at', key: 'updated_at', render: (date: string) => <Text style={{ color: t.muted, fontSize: 12 }}>{new Date(date).toLocaleString()}</Text> },
        { title: 'Actions', key: 'actions', render: (_: any, record: any) => <a onClick={() => setSelectedEntity(record)} style={{ color: t.accent }}>View State & History</a> }
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: t.text }}><AppstoreOutlined style={{ marginRight: 10, color: t.accent }} />System of Record</Title>
                    <Text style={{ color: t.muted }}>Canonical entity state and version history</Text>
                </div>
                <Space><Input placeholder="Filter by Kind..." allowClear onChange={(e) => setKindFilter(e.target.value)} style={{ width: 250 }} /></Space>
            </div>
            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <Table dataSource={entities} columns={columns} rowKey="id" loading={isLoading} size="middle" />
            </div>
            <Modal title={`Entity: ${selectedEntity?.kind} (${selectedEntity?.external_ref})`} open={!!selectedEntity} onCancel={() => setSelectedEntity(null)} footer={null} width={900}>
                <Collapse defaultActiveKey={['current']} items={[
                    { key: 'current', label: `Current State (Version ${selectedEntity?.version})`, children: <pre style={{ background: t.bg, padding: 12, borderRadius: 8, border: `1px solid ${t.border}`, color: t.text, fontSize: 12 }}>{JSON.stringify(selectedEntity?.data, null, 2)}</pre> },
                    {
                        key: 'history', label: 'History Logs', children: (
                            <Table dataSource={getEvents.data} loading={getEvents.isLoading} rowKey="id" size="small"
                                expandable={{
                                    expandedRowRender: (record: any) => (
                                        <div style={{ display: 'flex', gap: 16 }}>
                                            <div style={{ flex: 1 }}><Text style={{ color: t.text, fontWeight: 600 }}>Before:</Text><pre style={{ background: t.bg, padding: 10, borderRadius: 8, border: `1px solid ${t.border}`, color: t.text, fontSize: 12 }}>{JSON.stringify(record.data_before, null, 2)}</pre></div>
                                            <div style={{ flex: 1 }}><Text style={{ color: t.text, fontWeight: 600 }}>After:</Text><pre style={{ background: `${t.green}08`, padding: 10, borderRadius: 8, border: `1px solid ${t.green}30`, color: t.text, fontSize: 12 }}>{JSON.stringify(record.data_after, null, 2)}</pre></div>
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
