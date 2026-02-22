import { Row, Col, Card, Statistic, Table, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';

const { Title } = Typography;

export default function Dashboard() {
    const { data: tasks, isLoading: isLoadingTasks } = useQuery({
        queryKey: ['recent-tasks'],
        queryFn: async () => {
            const res = await apiClient.get('/tasks?limit=20');
            return res.data;
        }
    });

    const { data: agents, isLoading: isLoadingAgents } = useQuery({
        queryKey: ['agents'],
        queryFn: async () => {
            const res = await apiClient.get('/agents');
            return res.data;
        }
    });

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: 'Type', dataIndex: 'type', key: 'type' },
        { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <strong style={{ color: s === 'failed' ? 'red' : s === 'succeeded' ? 'green' : 'orange' }}>{s}</strong> },
        { title: 'Priority', dataIndex: 'priority', key: 'priority' },
        { title: 'Created', dataIndex: 'created_at', key: 'created_at', render: (date: string) => new Date(date).toLocaleString() },
    ];

    const healthyAgents = agents?.filter((a: any) => a.is_active) || [];

    return (
        <div>
            <Title level={3}>Nexus Dashboard</Title>
            <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
                <Col span={8}>
                    <Card>
                        <Statistic title="Total Agents" value={agents?.length || 0} loading={isLoadingAgents} />
                        <div style={{ fontSize: 12, color: 'gray' }}>{healthyAgents.length} Active</div>
                    </Card>
                </Col>
                <Col span={8}>
                    <Card>
                        <Statistic title="Recent Tasks" value={tasks?.length || 0} loading={isLoadingTasks} />
                    </Card>
                </Col>
                <Col span={8}>
                    <Card>
                        <Statistic title="KB Documents" value="?" loading={false} />
                    </Card>
                </Col>
            </Row>

            <Card title="Recent Tasks">
                <Table
                    dataSource={tasks}
                    columns={columns}
                    rowKey="id"
                    loading={isLoadingTasks}
                    pagination={false}
                    size="small"
                />
            </Card>
        </div>
    );
}
