import { Table, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../api/client';

const { Text } = Typography;

export default function SecretAuditTable() {
    const { data: audits, isLoading } = useQuery({
        queryKey: ['portal-secrets-audit'],
        queryFn: async () => {
            const resp = await apiClient.get('/portal/secrets/audit');
            return resp.data;
        },
    });

    const columns = [
        {
            title: 'Timestamp',
            dataIndex: 'ts',
            key: 'ts',
            render: (text: string) => new Date(text).toLocaleString(),
        },
        {
            title: 'Actor',
            dataIndex: 'service_id',
            key: 'service_id',
            render: (text: string) => <Tag>{text}</Tag>,
        },
        {
            title: 'Action',
            dataIndex: 'action',
            key: 'action',
            render: (text: string) => (
                <Tag color={text === 'read' ? 'red' : 'blue'}>
                    {text.toUpperCase()}
                </Tag>
            ),
        },
        {
            title: 'Alias',
            dataIndex: 'secret_alias',
            key: 'secret_alias',
        },
        {
            title: 'Result',
            dataIndex: 'result',
            key: 'result',
            render: (text: string) => (
                <Tag color={text === 'allowed' ? 'green' : 'red'}>
                    {text.toUpperCase()}
                </Tag>
            ),
        },
        {
            title: 'Reason',
            dataIndex: 'reason',
            key: 'reason',
            render: (text: string) => <Text type="secondary">{text}</Text>,
        },
    ];

    return (
        <Table
            columns={columns}
            dataSource={audits}
            rowKey="id"
            loading={isLoading}
            size="small"
        />
    );
}
