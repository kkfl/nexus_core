import { Button, Form, Input, InputNumber, Typography, Card, Space, Tag, Row, Col, Collapse, Empty, Spin, Alert, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useState } from 'react';
import { QuestionCircleOutlined, FileTextOutlined, LinkOutlined, LikeOutlined, DislikeOutlined, CheckCircleOutlined } from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
const { Panel } = Collapse;

interface Citation {
    document_id: string;
    title: string;
    chunk_id: string;
    chunk_index: number | null;
    start_char: number | null;
    end_char: number | null;
    score: number;
    excerpt: string;
}

interface AskResponse {
    correlation_id: string;
    answer: string;
    citations: Citation[];
    retrieval_debug: {
        top_k: number;
        namespaces: string[];
        model: string;
        provider: string;
        chunks_returned: number;
        retrieve_ms?: number;
        total_ms?: number;
    };
}

export default function AskNexus() {
    const [form] = Form.useForm();
    const [response, setResponse] = useState<AskResponse | null>(null);
    const [feedbackSent, setFeedbackSent] = useState(false);

    const askMutation = useMutation({
        mutationFn: async (values: any) => {
            const payload = {
                query: values.query,
                top_k: values.top_k || 5,
                namespaces: ['global', 'repo-docs'],
            };
            return (await apiClient.post('/kb/ask', payload)).data;
        },
        onSuccess: (data) => {
            setResponse(data);
            setFeedbackSent(false);
        },
    });

    const feedbackMutation = useMutation({
        mutationFn: async (data: { rating: string; note?: string }) => {
            if (!response) return;
            return (await apiClient.post('/kb/ask/feedback', {
                correlation_id: response.correlation_id,
                rating: data.rating,
                note: data.note,
            })).data;
        },
        onSuccess: () => {
            setFeedbackSent(true);
            message.success('Feedback submitted — thank you!');
        },
    });

    const handleFeedback = (rating: 'good' | 'bad') => {
        const note = (document.getElementById('feedback-note') as HTMLTextAreaElement)?.value || undefined;
        feedbackMutation.mutate({ rating, note });
    };

    return (
        <div>
            <Title level={3}>
                <QuestionCircleOutlined style={{ marginRight: 8 }} />
                Ask Nexus
            </Title>
            <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
                Ask a question and get answers with citations from the knowledge base.
            </Text>

            <Card style={{ marginBottom: 24 }}>
                <Form form={form} layout="vertical" onFinish={askMutation.mutate} initialValues={{ top_k: 5 }}>
                    <Form.Item name="query" label="Your Question" rules={[{ required: true, message: 'Please enter a question (3+ characters)' }]}>
                        <Input.TextArea
                            rows={3}
                            placeholder="e.g. What RBAC roles does Nexus implement?"
                            style={{ fontSize: 15 }}
                            maxLength={2000}
                            showCount
                        />
                    </Form.Item>

                    <Row gutter={16} align="bottom">
                        <Col xs={12} md={4}>
                            <Form.Item name="top_k" label="Max Citations">
                                <InputNumber min={1} max={10} style={{ width: '100%' }} />
                            </Form.Item>
                        </Col>
                        <Col xs={24} md={6}>
                            <Form.Item>
                                <Button
                                    type="primary"
                                    htmlType="submit"
                                    loading={askMutation.isPending}
                                    icon={<QuestionCircleOutlined />}
                                    size="large"
                                    block
                                >
                                    Ask
                                </Button>
                            </Form.Item>
                        </Col>
                    </Row>
                </Form>
            </Card>

            {askMutation.isPending && (
                <div style={{ textAlign: 'center', padding: 48 }}>
                    <Spin size="large" />
                    <Text style={{ display: 'block', marginTop: 16 }}>Searching knowledge base...</Text>
                </div>
            )}

            {askMutation.isError && (
                <Alert
                    type="error"
                    message="Failed to get answer"
                    description={String((askMutation.error as any)?.response?.data?.detail || askMutation.error?.message)}
                    showIcon
                    style={{ marginBottom: 16 }}
                />
            )}

            {response && !askMutation.isPending && (
                <>
                    {/* Answer */}
                    <Card
                        title={
                            <Space>
                                <Text strong style={{ fontSize: 16 }}>Answer</Text>
                                <Tag color="blue">{response.citations.length} citation(s)</Tag>
                                <Tag>{response.retrieval_debug.model}</Tag>
                                {response.retrieval_debug.total_ms && (
                                    <Tag color="green">{response.retrieval_debug.total_ms}ms</Tag>
                                )}
                            </Space>
                        }
                        style={{ marginBottom: 24 }}
                    >
                        <Paragraph style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.8 }}>
                            {response.answer}
                        </Paragraph>
                        <div style={{ marginTop: 12, borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                                Correlation ID: {response.correlation_id} &bull;
                                Top-K: {response.retrieval_debug.top_k} &bull;
                                Namespaces: {response.retrieval_debug.namespaces.join(', ')}
                            </Text>
                        </div>

                        {/* Feedback */}
                        <div style={{ marginTop: 16, borderTop: '1px solid #f0f0f0', paddingTop: 16 }}>
                            {feedbackSent ? (
                                <Space>
                                    <CheckCircleOutlined style={{ color: '#52c41a' }} />
                                    <Text type="success">Thanks for your feedback!</Text>
                                </Space>
                            ) : (
                                <Space direction="vertical" style={{ width: '100%' }}>
                                    <Text strong>Was this answer helpful?</Text>
                                    <Space>
                                        <Button
                                            icon={<LikeOutlined />}
                                            onClick={() => handleFeedback('good')}
                                            loading={feedbackMutation.isPending}
                                        >
                                            Good
                                        </Button>
                                        <Button
                                            icon={<DislikeOutlined />}
                                            onClick={() => handleFeedback('bad')}
                                            loading={feedbackMutation.isPending}
                                            danger
                                        >
                                            Not helpful
                                        </Button>
                                    </Space>
                                    <Input.TextArea
                                        id="feedback-note"
                                        rows={2}
                                        placeholder="Optional: tell us what could be improved..."
                                        maxLength={500}
                                        style={{ marginTop: 4 }}
                                    />
                                </Space>
                            )}
                        </div>
                    </Card>

                    {/* Citations */}
                    <Title level={4}>
                        <LinkOutlined style={{ marginRight: 8 }} />
                        Citations ({response.citations.length})
                    </Title>

                    {response.citations.length === 0 ? (
                        <Empty description="No relevant documents found" />
                    ) : (
                        <Collapse accordion>
                            {response.citations.map((citation, idx) => (
                                <Panel
                                    key={idx}
                                    header={
                                        <Space>
                                            <FileTextOutlined />
                                            <Text strong>{citation.title}</Text>
                                            <Tag color={citation.score >= 0.7 ? 'green' : citation.score >= 0.5 ? 'orange' : 'red'}>
                                                {(citation.score * 100).toFixed(1)}%
                                            </Tag>
                                            {citation.chunk_index !== null && (
                                                <Tag>Chunk #{citation.chunk_index}</Tag>
                                            )}
                                        </Space>
                                    }
                                >
                                    <Paragraph
                                        style={{
                                            whiteSpace: 'pre-wrap',
                                            fontFamily: 'monospace',
                                            fontSize: 13,
                                            background: '#f5f5f5',
                                            padding: 16,
                                            borderRadius: 8,
                                            maxHeight: 300,
                                            overflow: 'auto',
                                        }}
                                    >
                                        {citation.excerpt}
                                    </Paragraph>
                                    <Space wrap style={{ marginTop: 8 }}>
                                        <Text type="secondary">Doc ID: {citation.document_id}</Text>
                                        <Text type="secondary">Chunk ID: {citation.chunk_id}</Text>
                                        {citation.start_char !== null && citation.end_char !== null && (
                                            <Text type="secondary">
                                                Chars: {citation.start_char} &ndash; {citation.end_char}
                                            </Text>
                                        )}
                                    </Space>
                                </Panel>
                            ))}
                        </Collapse>
                    )}
                </>
            )}
        </div>
    );
}
