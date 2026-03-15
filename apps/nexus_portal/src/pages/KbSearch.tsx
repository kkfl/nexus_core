import { Button, Form, Input, Select, InputNumber, Typography, List, Space, Tag, Row, Col } from 'antd';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';
import { SearchOutlined } from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle } from '../theme';

const { Title, Text, Paragraph } = Typography;

export default function KbSearch() {
    const [form] = Form.useForm();
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const { data: documents } = useQuery({
        queryKey: ['kb_documents'],
        queryFn: async () => (await apiClient.get('/kb/documents')).data
    });

    const namespaces = Array.from(new Set(documents?.map((d: any) => d.namespace).filter(Boolean)));

    const searchKb = useMutation({
        mutationFn: async (values: any) => {
            const payload = { query: values.query, namespaces: values.namespaces?.length ? values.namespaces : undefined, top_k: values.top_k || 5, min_score: values.min_score || 0.0 };
            return (await apiClient.post('/kb/search', payload)).data;
        },
        onSuccess: (data) => setSearchResults(data)
    });

    return (
        <div style={pageContainer(t)}>
            <div style={{ marginBottom: 20 }}>
                <Title level={3} style={{ margin: 0, color: t.text }}><SearchOutlined style={{ marginRight: 10, color: t.accent }} />Knowledge Base Search</Title>
                <Text style={{ color: t.muted }}>Semantic similarity search across embedded documents</Text>
            </div>

            <div style={{ ...cardStyle(t), marginBottom: 24, padding: 24 }}>
                <Form form={form} layout="vertical" onFinish={searchKb.mutate} initialValues={{ top_k: 5, min_score: 0.5 }}>
                    <Form.Item name="query" label={<Text style={{ color: t.text }}>Search Query</Text>} rules={[{ required: true }]}>
                        <Input.TextArea rows={2} placeholder="Enter a natural language question or keywords..." />
                    </Form.Item>
                    <Row gutter={16} align="bottom">
                        <Col xs={24} md={8}>
                            <Form.Item name="namespaces" label={<Text style={{ color: t.text }}>Namespaces</Text>}>
                                <Select mode="tags" options={namespaces.map(ns => ({ label: ns, value: ns }))} placeholder="global" />
                            </Form.Item>
                        </Col>
                        <Col xs={12} md={4}>
                            <Form.Item name="top_k" label={<Text style={{ color: t.text }}>Top-K</Text>}>
                                <InputNumber min={1} max={20} style={{ width: '100%' }} />
                            </Form.Item>
                        </Col>
                        <Col xs={12} md={6}>
                            <Form.Item name="min_score" label={<Text style={{ color: t.text }}>Min Score</Text>}>
                                <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={6}>
                            <Form.Item>
                                <Button type="primary" htmlType="submit" loading={searchKb.isPending} block>Search Embeddings</Button>
                            </Form.Item>
                        </Col>
                    </Row>
                </Form>
            </div>

            <Title level={4} style={{ color: t.text }}>Results ({searchResults.length})</Title>
            <List
                dataSource={searchResults}
                renderItem={(item: any) => (
                    <List.Item style={{ padding: '8px 0', border: 'none' }}>
                        <div style={{ ...cardStyle(t), width: '100%', padding: 16 }}>
                            <Space style={{ marginBottom: 8 }}>
                                <Tag style={{ background: `${t.green}18`, color: t.green, border: `1px solid ${t.green}40` }}>Score: {(item.score * 100).toFixed(1)}%</Tag>
                                <Tag style={{ background: `${t.accent}18`, color: t.accent, border: `1px solid ${t.accent}40` }}>{item.document?.namespace || 'global'}</Tag>
                                <Text style={{ color: t.muted }}>{item.document?.title}</Text>
                            </Space>
                            <Paragraph style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 13, color: t.textSecondary, margin: '8px 0' }}>
                                {item.text}
                            </Paragraph>
                            <Text style={{ color: t.muted, fontSize: 11 }}>Chunk Index: {item.chunk_index}</Text>
                        </div>
                    </List.Item>
                )}
            />
        </div>
    );
}
