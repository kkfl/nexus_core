import { useState, useEffect } from 'react';
import { Typography, List, Spin, Alert, Empty } from 'antd';
import { FileMarkdownOutlined, ReadOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { apiClient } from '../api/client';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle } from '../theme';

const { Title, Text } = Typography;

export default function Docs() {
    const [docList, setDocList] = useState<Array<{ name: string; title: string }>>([]);
    const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
    const [content, setContent] = useState<string>('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    useEffect(() => {
        apiClient.get('/docs/list')
            .then((res: { data: Array<{ name: string; title: string }> }) => setDocList(res.data))
            .catch(() => setError('Failed to load docs list.'));
    }, []);

    const loadDoc = async (name: string) => {
        setLoading(true); setSelectedDoc(name); setContent('');
        try { const res = await apiClient.get(`/docs/${name}`); setContent(res.data); }
        catch { setContent(''); setError(`Failed to load ${name}`); }
        finally { setLoading(false); }
    };

    return (
        <div style={{ ...pageContainer(t), display: 'flex', gap: 24 }}>
            <div style={{ marginBottom: 20, position: 'absolute', top: 28, left: 28 }}>
                <Title level={3} style={{ margin: 0, color: t.text }}><ReadOutlined style={{ marginRight: 10, color: t.accent }} />Pilot Docs</Title>
            </div>
            <div style={{ width: 240, flexShrink: 0, paddingTop: 60 }}>
                <Text style={{ color: t.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>DOCUMENTS</Text>
                <List
                    dataSource={docList}
                    renderItem={item => (
                        <List.Item
                            onClick={() => loadDoc(item.name)}
                            style={{
                                cursor: 'pointer',
                                background: selectedDoc === item.name ? `${t.accent}12` : 'transparent',
                                borderLeft: selectedDoc === item.name ? `3px solid ${t.accent}` : `3px solid transparent`,
                                padding: '10px 16px',
                                borderRadius: 6,
                                marginBottom: 2,
                                border: 'none',
                                borderBottom: 'none',
                                transition: 'all 0.15s ease',
                            }}
                        >
                            <FileMarkdownOutlined style={{ marginRight: 8, color: t.accent }} />
                            <Text style={{ color: t.text }}>{item.title}</Text>
                        </List.Item>
                    )}
                    locale={{ emptyText: <Empty description="No docs found" /> }}
                />
            </div>
            <div style={{ ...cardStyle(t), flex: 1, overflow: 'auto', marginTop: 60, padding: 28 }}>
                {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} closable onClose={() => setError(null)} />}
                {loading ? (
                    <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
                ) : content ? (
                    <div style={{ fontFamily: 'Inter, sans-serif', lineHeight: 1.7, color: t.text }}>
                        <ReactMarkdown>{content}</ReactMarkdown>
                    </div>
                ) : (
                    <Empty description="Select a document from the list to read it." style={{ marginTop: 60 }} />
                )}
            </div>
        </div>
    );
}
