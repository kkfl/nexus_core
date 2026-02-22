import { Table, Button, Space, Tag, Modal, Typography, Collapse } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';

const { Title, Text, Paragraph } = Typography;

export default function Tasks() {
    const [selectedTask, setSelectedTask] = useState<any>(null);

    const { data: tasks, isLoading } = useQuery({
        queryKey: ['tasks'],
        queryFn: async () => (await apiClient.get('/tasks?limit=50')).data
    });

    const getArtifacts = useQuery({
        queryKey: ['artifacts', selectedTask?.id],
        queryFn: async () => (await apiClient.get(`/artifacts/${selectedTask?.id}`)).data,
        enabled: !!selectedTask
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: 'Type', dataIndex: 'type', key: 'type', render: (t: string) => <strong>{t}</strong> },
        {
            title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => {
                let color = 'default';
                if (s === 'queued') color = 'blue';
                if (s === 'running') color = 'orange';
                if (s === 'succeeded') color = 'green';
                if (s === 'failed') color = 'red';
                return <Tag color={color}>{s.toUpperCase()}</Tag>;
            }
        },
        { title: 'Created', dataIndex: 'created_at', key: 'created_at', render: (date: string) => new Date(date).toLocaleString() },
        {
            title: 'Actions', key: 'actions', render: (_: any, record: any) => (
                <Button size="small" onClick={() => setSelectedTask(record)}>View Details</Button>
            )
        }
    ];

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Title level={3}>Tasks & Artifacts</Title>
            </div>

            <Table dataSource={tasks} columns={columns} rowKey="id" loading={isLoading} size="middle" />

            <Modal
                title={`Task ${selectedTask?.id}: ${selectedTask?.type}`}
                open={!!selectedTask}
                onCancel={() => setSelectedTask(null)}
                footer={null}
                width={800}
            >
                {selectedTask && (
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Descriptions task={selectedTask} />

                        <Collapse items={[
                            {
                                key: 'payload',
                                label: 'Task Payload (Input)',
                                children: <pre style={{ background: '#f5f5f5', padding: 10 }}>{JSON.stringify(selectedTask.payload, null, 2)}</pre>
                            },
                            {
                                key: 'artifacts',
                                label: 'Artifacts (Result)',
                                children: (
                                    <div>
                                        {getArtifacts.isLoading ? 'Loading artifacts...' : (
                                            getArtifacts.data?.length > 0 ? (
                                                getArtifacts.data.map((art: any) => (
                                                    <div key={art.id} style={{ marginBottom: 10, padding: 10, border: '1px solid #d9d9d9' }}>
                                                        <Space split={"|"}>
                                                            <Text strong>{art.label || 'Default Output'}</Text>
                                                            <Text type="secondary">{art.content_type}</Text>
                                                            <a href={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/artifacts/${selectedTask.id}/download-url`} target="_blank" rel="noreferrer">
                                                                View / Download JSON
                                                            </a>
                                                        </Space>
                                                    </div>
                                                ))
                                            ) : <Text type="secondary">No artifacts generated for this task.</Text>
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

function Descriptions({ task }: { task: any }) {
    return (
        <div style={{ marginBottom: 16 }}>
            <Paragraph><Text strong>Status: </Text><Tag>{task.status}</Tag></Paragraph>
            <Paragraph><Text strong>Priority: </Text>{task.priority}</Paragraph>
            <Paragraph><Text strong>Persona Version ID: </Text>{task.persona_version_id || 'None (Default Routing)'}</Paragraph>
            <Paragraph><Text strong>Correlation ID: </Text>{task.correlation_id || 'N/A'}</Paragraph>
            {task.error_details && <Paragraph type="danger"><Text strong>Error: </Text>{task.error_details}</Paragraph>}
        </div>
    );
}
