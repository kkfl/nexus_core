import { Table, Button, Space, Tag, Modal, Typography, Collapse } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';
import { ProfileOutlined } from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';

const { Title, Text, Paragraph } = Typography;

export default function Tasks() {
    const [selectedTask, setSelectedTask] = useState<any>(null);
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const { data: tasks, isLoading } = useQuery({
        queryKey: ['tasks'],
        queryFn: async () => (await apiClient.get('/tasks?limit=50')).data
    });

    const getArtifacts = useQuery({
        queryKey: ['artifacts', selectedTask?.id],
        queryFn: async () => (await apiClient.get(`/artifacts/${selectedTask?.id}`)).data,
        enabled: !!selectedTask
    });

    const statusColor = (s: string) => {
        if (s === 'queued') return { bg: `${t.accent}18`, color: t.accent, border: `${t.accent}40` };
        if (s === 'running') return { bg: `${t.orange}18`, color: t.orange, border: `${t.orange}40` };
        if (s === 'succeeded') return { bg: `${t.green}18`, color: t.green, border: `${t.green}40` };
        if (s === 'failed') return { bg: `${t.red}18`, color: t.red, border: `${t.red}40` };
        return { bg: `${t.muted}18`, color: t.muted, border: `${t.muted}40` };
    };

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
        { title: 'Type', dataIndex: 'type', key: 'type', render: (v: string) => <Text style={{ color: t.cyan, fontWeight: 600, fontFamily: 'monospace' }}>{v}</Text> },
        { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => { const c = statusColor(s); return <Tag style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}>{s.toUpperCase()}</Tag>; } },
        { title: 'Created', dataIndex: 'created_at', key: 'created_at', render: (date: string) => <Text style={{ color: t.muted, fontSize: 12 }}>{new Date(date).toLocaleString()}</Text> },
        { title: 'Actions', key: 'actions', render: (_: any, record: any) => <Button size="small" onClick={() => setSelectedTask(record)} style={{ color: t.accent }}>View Details</Button> }
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ marginBottom: 20 }}>
                <Title level={3} style={{ margin: 0, color: t.text }}><ProfileOutlined style={{ marginRight: 10, color: t.accent }} />Tasks & Artifacts</Title>
                <Text style={{ color: t.muted }}>View task execution history and output artifacts</Text>
            </div>
            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, overflow: 'hidden' }}>
                <Table dataSource={tasks} columns={columns} rowKey="id" loading={isLoading} size="middle" />
            </div>
            <Modal title={`Task ${selectedTask?.id}: ${selectedTask?.type}`} open={!!selectedTask} onCancel={() => setSelectedTask(null)} footer={null} width={800}>
                {selectedTask && (
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <div style={{ marginBottom: 16 }}>
                            <Paragraph style={{ color: t.text }}><Text style={{ fontWeight: 600 }}>Status: </Text><Tag>{selectedTask.status}</Tag></Paragraph>
                            <Paragraph style={{ color: t.text }}><Text style={{ fontWeight: 600 }}>Priority: </Text>{selectedTask.priority}</Paragraph>
                            <Paragraph style={{ color: t.text }}><Text style={{ fontWeight: 600 }}>Persona Version ID: </Text>{selectedTask.persona_version_id || 'None'}</Paragraph>
                            <Paragraph style={{ color: t.text }}><Text style={{ fontWeight: 600 }}>Correlation ID: </Text>{selectedTask.correlation_id || 'N/A'}</Paragraph>
                            {selectedTask.error_details && <Paragraph style={{ color: t.red }}><Text style={{ fontWeight: 600 }}>Error: </Text>{selectedTask.error_details}</Paragraph>}
                        </div>
                        <Collapse items={[
                            { key: 'payload', label: 'Task Payload', children: <pre style={{ background: t.bg, padding: 12, borderRadius: 8, border: `1px solid ${t.border}`, color: t.text, fontSize: 12 }}>{JSON.stringify(selectedTask.payload, null, 2)}</pre> },
                            {
                                key: 'artifacts', label: 'Artifacts', children: (
                                    <div>
                                        {getArtifacts.isLoading ? 'Loading...' : (
                                            getArtifacts.data?.length > 0 ? getArtifacts.data.map((art: any) => (
                                                <div key={art.id} style={{ marginBottom: 10, padding: 10, border: `1px solid ${t.border}`, borderRadius: 8 }}>
                                                    <Space split={"|"}><Text style={{ color: t.text, fontWeight: 600 }}>{art.label || 'Default Output'}</Text><Text style={{ color: t.muted }}>{art.content_type}</Text></Space>
                                                </div>
                                            )) : <Text style={{ color: t.muted }}>No artifacts generated</Text>
                                        )}
                                    </div>
                                )
                            }
                        ]} />
                    </Space>
                )}
            </Modal>
        </div>
    );
}
