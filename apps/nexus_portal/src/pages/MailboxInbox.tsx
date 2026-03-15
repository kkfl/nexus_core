import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Button, Typography, Space, Input, Tooltip, Drawer, Tabs, Empty, Spin, message, Descriptions, Tag, Card } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { emailClient } from '../api/emailClient';
import { useState } from 'react';
import {
    ArrowLeftOutlined, ReloadOutlined, MailOutlined, PaperClipOutlined,
    EyeOutlined, EyeInvisibleOutlined, SearchOutlined, DownloadOutlined,
    FileTextOutlined, SendOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, tableStyleOverrides } from '../theme';

const { Title, Text, Paragraph } = Typography;
const { Search } = Input;

interface MessageItem {
    uid: string;
    subject: string;
    from_addr: string;
    to_addr: string;
    date: string;
    flags: string[];
    has_attachments: boolean;
    size_bytes: number;
    is_read: boolean;
}

interface AttachmentInfo {
    id: string;
    filename: string;
    content_type: string;
    size_bytes: number;
}

interface FullMessage {
    uid: string;
    subject: string;
    from_addr: string;
    to_addr: string;
    cc_addr: string;
    date: string;
    body_text: string | null;
    body_html: string | null;
    attachments: AttachmentInfo[];
    has_attachments: boolean;
}

interface SentMessage {
    queue_id: string;
    sender: string;
    recipient: string;
    sent_at: string;
    status: string;
    dsn: string;
    delay_seconds: string;
    relay: string;
    status_detail: string;
    collected_at: string;
}

export default function MailboxInbox() {
    const { email } = useParams<{ email: string }>();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const decodedEmail = email ? decodeURIComponent(email) : '';
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedUid, setSelectedUid] = useState<string | null>(null);
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [searchParams] = useSearchParams();
    const [activeTab, setActiveTab] = useState(searchParams.get('tab') === 'sent' ? 'sent' : 'inbox');
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    // Message list
    const { data: messages, isLoading, refetch } = useQuery<MessageItem[]>({
        queryKey: ['mailbox_messages', decodedEmail, searchQuery],
        queryFn: async () => {
            const params = new URLSearchParams({ folder: 'INBOX', limit: '100' });
            if (searchQuery) params.append('q', searchQuery);
            return (await emailClient.get(`/email/mailbox/${encodeURIComponent(decodedEmail)}/messages?${params}`)).data;
        },
        enabled: !!decodedEmail,
    });

    // Selected message detail
    const { data: messageDetail, isLoading: detailLoading } = useQuery<FullMessage>({
        queryKey: ['mailbox_message', decodedEmail, selectedUid],
        queryFn: async () =>
            (await emailClient.get(`/email/mailbox/${encodeURIComponent(decodedEmail)}/message/${selectedUid}`)).data,
        enabled: !!selectedUid && !!decodedEmail,
    });

    // Mark read/unread
    const markReadMutation = useMutation({
        mutationFn: async ({ uid, read }: { uid: string; read: boolean }) =>
            (await emailClient.post(`/email/mailbox/${encodeURIComponent(decodedEmail)}/message/${uid}/${read ? 'mark_read' : 'mark_unread'}`)).data,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['mailbox_messages', decodedEmail] });
            message.success('Flags updated');
        },
    });

    // Sent messages
    const { data: sentData, isLoading: sentLoading, refetch: refetchSent } = useQuery<{ ok: boolean; messages: SentMessage[]; count: number }>({
        queryKey: ['mailbox_sent', decodedEmail],
        queryFn: async () => (await emailClient.get(`/email/admin/mailbox/${encodeURIComponent(decodedEmail)}/sent?limit=100`)).data,
        enabled: !!decodedEmail && activeTab === 'sent',
    });

    const formatSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const openMessage = (uid: string) => {
        setSelectedUid(uid);
        setDrawerOpen(true);
    };

    const statusIcon = (status: string) => {
        switch (status) {
            case 'sent': return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
            case 'bounced': return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
            case 'deferred': return <ClockCircleOutlined style={{ color: '#faad14' }} />;
            default: return null;
        }
    };

    const statusColor = (status: string) => {
        switch (status) {
            case 'sent': return 'green';
            case 'bounced': return 'red';
            case 'deferred': return 'orange';
            default: return 'default';
        }
    };

    const sentColumns = [
        {
            title: 'Recipient',
            dataIndex: 'recipient',
            key: 'recipient',
            ellipsis: true,
            render: (r: string) => <Text style={{ fontSize: 13 }}>{r}</Text>,
        },
        {
            title: 'Status',
            dataIndex: 'status',
            key: 'status',
            width: 110,
            render: (status: string) => (
                <Tag icon={statusIcon(status)} color={statusColor(status)}>
                    {status?.charAt(0).toUpperCase() + status?.slice(1)}
                </Tag>
            ),
        },
        {
            title: 'Sent At',
            dataIndex: 'sent_at',
            key: 'sent_at',
            width: 180,
            render: (date: string) => <Text type="secondary" style={{ fontSize: 12 }}>{date}</Text>,
        },
        {
            title: 'Relay',
            dataIndex: 'relay',
            key: 'relay',
            width: 200,
            ellipsis: true,
            render: (relay: string) => <Text type="secondary" style={{ fontSize: 12 }}>{relay}</Text>,
        },
        {
            title: 'Delay',
            dataIndex: 'delay_seconds',
            key: 'delay',
            width: 80,
            render: (delay: string) => <Text type="secondary" style={{ fontSize: 12 }}>{delay}s</Text>,
        },
        {
            title: 'DSN',
            dataIndex: 'dsn',
            key: 'dsn',
            width: 80,
            render: (dsn: string) => <Text type="secondary" style={{ fontSize: 12 }}>{dsn}</Text>,
        },
        {
            title: 'Detail',
            dataIndex: 'status_detail',
            key: 'detail',
            ellipsis: true,
            render: (detail: string) => (
                <Tooltip title={detail}>
                    <Text type="secondary" style={{ fontSize: 12 }}>{detail}</Text>
                </Tooltip>
            ),
        },
    ];

    const columns = [
        {
            title: '',
            key: 'status',
            width: 40,
            render: (_: any, record: MessageItem) => (
                <Tooltip title={record.is_read ? 'Read' : 'Unread'}>
                    {record.is_read
                        ? <EyeOutlined style={{ color: '#999' }} />
                        : <MailOutlined style={{ color: '#1677ff', fontWeight: 'bold' }} />
                    }
                </Tooltip>
            ),
        },
        {
            title: 'From',
            dataIndex: 'from_addr',
            key: 'from',
            width: 250,
            ellipsis: true,
            render: (from: string, record: MessageItem) => (
                <Text strong={!record.is_read} style={{ fontSize: 13 }}>{from}</Text>
            ),
        },
        {
            title: 'Subject',
            dataIndex: 'subject',
            key: 'subject',
            ellipsis: true,
            render: (subject: string, record: MessageItem) => (
                <Space>
                    <Text strong={!record.is_read} style={{ cursor: 'pointer', color: '#1677ff' }}
                        onClick={() => openMessage(record.uid)}>
                        {subject || '(no subject)'}
                    </Text>
                    {record.has_attachments && <PaperClipOutlined style={{ color: '#999' }} />}
                </Space>
            ),
        },
        {
            title: 'Date',
            dataIndex: 'date',
            key: 'date',
            width: 180,
            render: (date: string) => <Text type="secondary" style={{ fontSize: 12 }}>{date}</Text>,
        },
        {
            title: 'Size',
            dataIndex: 'size_bytes',
            key: 'size',
            width: 80,
            render: (size: number) => <Text type="secondary" style={{ fontSize: 12 }}>{formatSize(size)}</Text>,
        },
        {
            title: '',
            key: 'actions',
            width: 80,
            render: (_: any, record: MessageItem) => (
                <Space size={4}>
                    <Tooltip title={record.is_read ? 'Mark Unread' : 'Mark Read'}>
                        <Button
                            size="small"
                            type="text"
                            icon={record.is_read ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                            onClick={() => markReadMutation.mutate({ uid: record.uid, read: !record.is_read })}
                        />
                    </Tooltip>
                </Space>
            ),
        },
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <Space>
                    <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/integrations/email')}>Back</Button>
                    <Title level={4} style={{ margin: 0, color: t.text }}>
                        <MailOutlined style={{ marginRight: 8, color: t.accent }} />
                        {decodedEmail}
                    </Title>
                </Space>
                <Space>
                    <Search
                        placeholder="Search subjects..."
                        allowClear
                        style={{ width: 250 }}
                        onSearch={(value) => setSearchQuery(value)}
                        prefix={<SearchOutlined />}
                    />
                    <Button icon={<ReloadOutlined />} onClick={() => refetch()}>Refresh</Button>
                </Space>
            </div>

            {/* Tabs: Inbox / Sent */}
            <Tabs
                activeKey={activeTab}
                onChange={setActiveTab}
                items={[
                    {
                        key: 'inbox',
                        label: <Space><MailOutlined />Inbox ({messages?.length ?? 0})</Space>,
                        children: (
                            <>
                                {/* Stats bar */}
                                <Card size="small" style={{ marginBottom: 16 }}>
                                    <Space size="large">
                                        <Text type="secondary">
                                            <MailOutlined style={{ marginRight: 4 }} />
                                            {messages?.length ?? 0} messages
                                        </Text>
                                        <Text type="secondary">
                                            {messages?.filter(m => !m.is_read).length ?? 0} unread
                                        </Text>
                                    </Space>
                                </Card>

                                {/* Message list */}
                                <Table
                                    dataSource={messages}
                                    columns={columns}
                                    rowKey="uid"
                                    loading={isLoading}
                                    size="small"
                                    pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (total) => `${total} messages` }}
                                    onRow={(record) => ({
                                        onClick: () => openMessage(record.uid),
                                        style: {
                                            cursor: 'pointer',
                                            backgroundColor: record.is_read ? undefined : t.hoverBg,
                                        },
                                    })}
                                />
                            </>
                        ),
                    },
                    {
                        key: 'sent',
                        label: <Space><SendOutlined />Sent</Space>,
                        children: (
                            <>
                                <Card size="small" style={{ marginBottom: 16 }}>
                                    <Space size="large">
                                        <Text type="secondary">
                                            <SendOutlined style={{ marginRight: 4 }} />
                                            {sentData?.count ?? 0} sent messages
                                        </Text>
                                        <Button
                                            size="small"
                                            icon={<ReloadOutlined />}
                                            onClick={() => refetchSent()}
                                        >
                                            Refresh
                                        </Button>
                                    </Space>
                                </Card>

                                <Table
                                    dataSource={sentData?.messages}
                                    columns={sentColumns}
                                    rowKey="queue_id"
                                    loading={sentLoading}
                                    size="small"
                                    pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (total) => `${total} sent messages` }}
                                    locale={{ emptyText: <Empty description="No sent messages found in recent logs" /> }}
                                />
                            </>
                        ),
                    },
                ]}
            />

            {/* Message Detail Drawer */}
            <Drawer
                title={messageDetail?.subject || 'Loading...'}
                placement="right"
                size="large"
                open={drawerOpen}
                onClose={() => { setDrawerOpen(false); setSelectedUid(null); }}
                extra={
                    selectedUid && (
                        <Space>
                            <Tooltip title="Download raw .eml">
                                <Button
                                    size="small"
                                    icon={<DownloadOutlined />}
                                    href={`/email/mailbox/${encodeURIComponent(decodedEmail)}/message/${selectedUid}/raw`}
                                    target="_blank"
                                >
                                    Raw
                                </Button>
                            </Tooltip>
                        </Space>
                    )
                }
            >
                {detailLoading ? (
                    <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
                ) : messageDetail ? (
                    <div>
                        <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
                            <Descriptions.Item label="From">{messageDetail.from_addr}</Descriptions.Item>
                            <Descriptions.Item label="To">{messageDetail.to_addr}</Descriptions.Item>
                            {messageDetail.cc_addr && <Descriptions.Item label="Cc">{messageDetail.cc_addr}</Descriptions.Item>}
                            <Descriptions.Item label="Date">{messageDetail.date}</Descriptions.Item>
                        </Descriptions>

                        <Tabs
                            defaultActiveKey="body"
                            items={[
                                {
                                    key: 'body',
                                    label: 'Body',
                                    children: messageDetail.body_html ? (
                                        <div
                                            style={{ border: `1px solid ${t.border}`, borderRadius: 6, padding: 12, background: t.cardBg, maxHeight: 500, overflow: 'auto' }}
                                            dangerouslySetInnerHTML={{ __html: messageDetail.body_html }}
                                        />
                                    ) : messageDetail.body_text ? (
                                        <Paragraph style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 13, background: t.bg, padding: 12, borderRadius: 6, color: t.text }}>
                                            {messageDetail.body_text}
                                        </Paragraph>
                                    ) : (
                                        <Empty description="No body content" />
                                    ),
                                },
                                ...(messageDetail.attachments?.length > 0 ? [{
                                    key: 'attachments',
                                    label: <Space><PaperClipOutlined />{`Attachments (${messageDetail.attachments.length})`}</Space>,
                                    children: (
                                        <div>
                                            {messageDetail.attachments.map((att: AttachmentInfo) => (
                                                <Card key={att.id} size="small" style={{ marginBottom: 8 }}>
                                                    <Space>
                                                        <FileTextOutlined />
                                                        <Text>{att.filename}</Text>
                                                        <Text type="secondary">({att.content_type}, {formatSize(att.size_bytes)})</Text>
                                                        <Button
                                                            size="small"
                                                            type="link"
                                                            icon={<DownloadOutlined />}
                                                            href={`/email/mailbox/${encodeURIComponent(decodedEmail)}/message/${selectedUid}/attachment/${att.id}`}
                                                            target="_blank"
                                                        >
                                                            Download
                                                        </Button>
                                                    </Space>
                                                </Card>
                                            ))}
                                        </div>
                                    ),
                                }] : []),
                            ]}
                        />
                    </div>
                ) : (
                    <Empty description="Message not found" />
                )}
            </Drawer>
        </div>
    );
}
