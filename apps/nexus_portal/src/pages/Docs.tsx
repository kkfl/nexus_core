import { useState, useEffect } from 'react';
import { Typography, List, Card, Spin, Alert, Empty } from 'antd';
import { FileMarkdownOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { apiClient } from '../api/client';

const { Title, Text } = Typography;

export default function Docs() {
    const [docList, setDocList] = useState<Array<{ name: string; title: string }>>([]);
    const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
    const [content, setContent] = useState<string>('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        apiClient.get('/docs/list')
            .then((res: { data: Array<{ name: string; title: string }> }) => setDocList(res.data))
            .catch(() => setError('Failed to load docs list.'));
    }, []);

    const loadDoc = async (name: string) => {
        setLoading(true);
        setSelectedDoc(name);
        setContent('');
        try {
            const res = await apiClient.get(`/docs/${name}`);
            setContent(res.data);
        } catch {
            setContent('');
            setError(`Failed to load ${name}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ display: 'flex', gap: 24, height: '100%' }}>
            <div style={{ width: 240, flexShrink: 0 }}>
                <Title level={5} style={{ marginBottom: 12 }}>Documents</Title>
                <List
                    bordered
                    dataSource={docList}
                    renderItem={item => (
                        <List.Item
                            onClick={() => loadDoc(item.name)}
                            style={{
                                cursor: 'pointer',
                                background: selectedDoc === item.name ? '#e6f4ff' : undefined,
                                borderLeft: selectedDoc === item.name ? '3px solid #1677ff' : '3px solid transparent',
                                padding: '10px 16px',
                            }}
                        >
                            <FileMarkdownOutlined style={{ marginRight: 8, color: '#1677ff' }} />
                            <Text>{item.title}</Text>
                        </List.Item>
                    )}
                    locale={{ emptyText: <Empty description="No docs found" /> }}
                />
            </div>

            <Card style={{ flex: 1, overflow: 'auto' }} >
                {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} closable onClose={() => setError(null)} />}
                {loading ? (
                    <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
                ) : content ? (
                    <div style={{ fontFamily: 'Inter, sans-serif', lineHeight: 1.7 }}>
                        <ReactMarkdown>{content}</ReactMarkdown>
                    </div>
                ) : (
                    <Empty description="Select a document from the list to read it." style={{ marginTop: 60 }} />
                )}
            </Card>
        </div>
    );
}
