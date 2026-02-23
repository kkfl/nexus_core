import { Button, Form, Input, Select, InputNumber, Typography, List, Card, Space, Tag } from 'antd';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';

const { Title, Text, Paragraph } = Typography;

export default function KbSearch() {
    const [form] = Form.useForm();
    const [searchResults, setSearchResults] = useState<any[]>([]);

    const { data: documents } = useQuery({
        queryKey: ['kb_documents'],
        queryFn: async () => (await apiClient.get('/kb/documents')).data
    });

    // Extract unique namespaces
    const namespaces = Array.from(new Set(documents?.map((d: any) => d.namespace).filter(Boolean)));

    const searchKb = useMutation({
        mutationFn: async (values: any) => {
            const payload = {
                query: values.query,
                namespaces: values.namespaces && values.namespaces.length ? values.namespaces : undefined,
                top_k: values.top_k || 5,
                min_score: values.min_score || 0.0
            };
            return (await apiClient.post('/kb/search', payload)).data;
        },
        onSuccess: (data) => setSearchResults(data)
    });

    return (
        <div>
            <Title level={3}>Knowledge Base Similarity Search</Title>

            <Card style={{ marginBottom: 24 }}>
                <Form form={form} layout="vertical" onFinish={searchKb.mutate} initialValues={{ top_k: 5, min_score: 0.5 }}>
                    <Form.Item name="query" label="Search Query" rules={[{ required: true }]}>
                        <Input.TextArea rows={2} placeholder="Enter a natural language question or keywords..." />
                    </Form.Item>

                    <Space size="large" wrap>
                        <Form.Item name="namespaces" label="Namespaces (Optional Filter)" style={{ minWidth: 250 }}>
                            <Select mode="tags" options={namespaces.map(ns => ({ label: ns, value: ns }))} placeholder="global" />
                        </Form.Item>

                        <Form.Item name="top_k" label="Top-K Chunks">
                            <InputNumber min={1} max={20} />
                        </Form.Item>

                        <Form.Item name="min_score" label="Min Confidence Score (0-1)">
                            <InputNumber min={0} max={1} step={0.1} />
                        </Form.Item>

                        <Form.Item label=" ">
                            <Button type="primary" htmlType="submit" loading={searchKb.isPending}>Search Embeddings</Button>
                        </Form.Item>
                    </Space>
                </Form>
            </Card>

            <Title level={4}>Results ({searchResults.length})</Title>
            <List
                dataSource={searchResults}
                renderItem={(item: any) => (
                    <List.Item>
                        <Card style={{ width: '100%' }} size="small"
                            title={
                                <Space>
                                    <Text strong>Score: {(item.score * 100).toFixed(1)}%</Text>
                                    <Tag color="geekblue">{item.document?.namespace || 'global'}</Tag>
                                    <Text type="secondary">{item.document?.title}</Text>
                                </Space>
                            }>
                            <Paragraph style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 13 }}>
                                {item.text}
                            </Paragraph>
                            <Text type="secondary" style={{ fontSize: 12 }}>Chunk Index: {item.chunk_index}</Text>
                        </Card>
                    </List.Item>
                )}
            />
        </div>
    );
}
