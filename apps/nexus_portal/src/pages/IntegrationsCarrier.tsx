import { Table, Modal, Typography, Space, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';
import { PhoneOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text } = Typography;

export default function IntegrationsCarrier() {
    const [selectedItem, setSelectedItem] = useState<any>(null);
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const { data, isLoading } = useQuery({
        queryKey: ['carrier_snapshots'],
        queryFn: async () => {
            try {
                return (await apiClient.get('/carrier/snapshots')).data;
            } catch (e: any) {
                if (e?.response?.status === 404) return [];
                throw e;
            }
        }
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
        { title: 'Task ID', dataIndex: 'task_id', key: 'task_id', render: (id: number) => <Text style={{ color: t.accent, fontWeight: 600 }}>{id}</Text> },
        { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag style={{ background: s === 'succeeded' ? `${t.green}18` : `${t.red}18`, color: s === 'succeeded' ? t.green : t.red, border: `1px solid ${s === 'succeeded' ? `${t.green}40` : `${t.red}40`}` }}>{s}</Tag> },
        { title: 'Target Carrier ID', dataIndex: 'carrier_target_id', key: 'carrier_target_id' },
        { title: 'Created At', dataIndex: 'created_at', key: 'created_at', render: (date: string) => <Text style={{ color: t.muted, fontSize: 12 }}><ClockCircleOutlined style={{ marginRight: 4 }} />{new Date(date).toLocaleString()}</Text> },
        { title: 'Details', key: 'details', render: (_: any, record: any) => <a onClick={() => setSelectedItem(record)} style={{ color: t.accent }}>View Summary</a> }
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ marginBottom: 20 }}>
                <Title level={3} style={{ margin: 0, color: t.text }}><PhoneOutlined style={{ marginRight: 10, color: t.accent }} />Carrier Inventory</Title>
                <Text style={{ color: t.muted }}>Read-only view of carrier snapshot data</Text>
            </div>
            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <Table dataSource={data} columns={columns} rowKey="id" loading={isLoading} size="middle" />
            </div>
            <Modal title={`Carrier Snapshot: ${selectedItem?.id}`} open={!!selectedItem} onCancel={() => setSelectedItem(null)} footer={null}>
                {selectedItem && (
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Text style={{ color: t.text }}>Status: <Tag style={{ background: `${t.accent}18`, color: t.accent, border: `1px solid ${t.accent}40` }}>{selectedItem.status}</Tag></Text>
                        <pre style={{ background: t.bg, padding: 12, borderRadius: 8, border: `1px solid ${t.border}`, color: t.text, fontSize: 12 }}>{JSON.stringify(selectedItem.summary, null, 2)}</pre>
                    </Space>
                )}
            </Modal>
        </div>
    );
}
