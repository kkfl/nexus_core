/**
 * Audit Log Viewer — Settings → Audit Log
 *
 * Real-time security event viewer with filtering.
 * Uses the existing GET /audit/ API.
 */
import { useMemo, useState } from 'react';
import {
    Typography, Table, Tag, Space, DatePicker, Select, Button, Row, Col, Statistic,
} from 'antd';
import {
    SafetyOutlined, ReloadOutlined, WarningOutlined,
    KeyOutlined, UserOutlined,
    ClockCircleOutlined, FilterOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer, cardStyle, tableStyleOverrides } from '../theme';
import { apiClient } from '../api/client';
import { TiltCard } from '../components/TiltCard';
import dayjs from 'dayjs';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

interface AuditEvent {
    id: number;
    actor_id: number | null;
    actor_type: string | null;
    action: string;
    target_type: string;
    target_id: number | null;
    meta_data: Record<string, unknown> | null;
    created_at: string;
}

// Map actions to colors for visual severity
const ACTION_COLORS: Record<string, string> = {
    login_success: 'green',
    login_failed: 'red',
    logout: 'default',
    token_refresh: 'blue',
    api_key_create: 'gold',
    api_key_rotate: 'orange',
    api_key_revoke: 'red',
    api_key_enable: 'green',
    api_key_disable: 'volcano',
    secret_decrypt: 'purple',
    secret_decrypt_denied: 'red',
    user_create: 'cyan',
    user_delete: 'red',
    password_change: 'orange',
};

export default function AuditLog() {
    const { mode } = useThemeStore();
    const t = getTokens(mode);
    const [actionFilter, setActionFilter] = useState<string | undefined>();
    const [actorFilter, setActorFilter] = useState<string | undefined>();
    const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);

    const { data: events = [], isLoading, refetch } = useQuery<AuditEvent[]>({
        queryKey: ['audit-log', actionFilter, actorFilter, dateRange?.map(d => d.toISOString())],
        queryFn: () => {
            const params: Record<string, string> = { limit: '200' };
            if (actionFilter) params.action = actionFilter;
            if (actorFilter) params.actor_type = actorFilter;
            if (dateRange) {
                params.since = dateRange[0].toISOString();
                params.until = dateRange[1].toISOString();
            }
            return apiClient.get('/audit/', { params }).then(r => r.data);
        },
    });

    // Stats
    const securityEvents = events.filter(e =>
        ['login_failed', 'api_key_revoke', 'secret_decrypt_denied', 'api_key_disable'].includes(e.action)
    ).length;
    const last24h = useMemo(() => events.filter(e => {
        // eslint-disable-next-line react-hooks/purity
        const diff = Date.now() - new Date(e.created_at).getTime();
        return diff < 24 * 60 * 60 * 1000;
    }).length, [events]);

    // Unique actions for the filter dropdown
    const uniqueActions = [...new Set(events.map(e => e.action))].sort();

    const columns = [
        {
            title: 'Time', dataIndex: 'created_at', key: 'time', width: 180,
            render: (v: string) => (
                <Text style={{ color: t.muted, fontSize: 12, fontFamily: "'SF Mono', monospace" }}>
                    {new Date(v).toLocaleString()}
                </Text>
            ),
        },
        {
            title: 'Action', dataIndex: 'action', key: 'action',
            render: (action: string) => (
                <Tag color={ACTION_COLORS[action] || 'default'}>
                    {action.replace(/_/g, ' ').toUpperCase()}
                </Tag>
            ),
        },
        {
            title: 'Actor', key: 'actor',
            render: (_: unknown, rec: AuditEvent) => (
                <Space size={4}>
                    {rec.actor_type === 'agent' ? <KeyOutlined /> : <UserOutlined />}
                    <Text style={{ color: t.text, fontSize: 13 }}>
                        {rec.actor_type}:{rec.actor_id}
                    </Text>
                </Space>
            ),
        },
        {
            title: 'Resource', key: 'resource',
            render: (_: unknown, rec: AuditEvent) => (
                <Text style={{ color: t.muted, fontSize: 12 }}>
                    {rec.target_type}{rec.target_id ? `:${rec.target_id}` : ''}
                </Text>
            ),
        },
        {
            title: 'Details', dataIndex: 'meta_data', key: 'meta',
            render: (meta: Record<string, unknown> | null) => meta ? (
                <Text style={{ color: t.muted, fontSize: 11, fontFamily: "'SF Mono', monospace" }}>
                    {JSON.stringify(meta).substring(0, 80)}
                    {JSON.stringify(meta).length > 80 ? '…' : ''}
                </Text>
            ) : <Text style={{ color: t.muted, fontSize: 11, fontStyle: 'italic' }}>—</Text>,
        },
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{tableStyleOverrides(t, 'nx-table')}</style>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={3} style={{ color: t.text, margin: 0 }}>
                        <SafetyOutlined style={{ marginRight: 10 }} />
                        Audit Log
                    </Title>
                    <Text style={{ color: t.muted }}>
                        Security events, authentication, and credential management activity
                    </Text>
                </div>
                <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
                    Refresh
                </Button>
            </div>

            {/* Stats */}
            <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={8}>
                    <TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.accent } as React.CSSProperties}>
                        <Statistic title={<Text style={{ color: t.muted }}>Total Events</Text>} value={events.length} prefix={<SafetyOutlined />} valueStyle={{ color: t.text }} />
                    </TiltCard>
                </Col>
                <Col span={8}>
                    <TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.red } as React.CSSProperties}>
                        <Statistic title={<Text style={{ color: t.muted }}>Security Alerts</Text>} value={securityEvents} prefix={<WarningOutlined />} valueStyle={{ color: t.red }} />
                    </TiltCard>
                </Col>
                <Col span={8}>
                    <TiltCard className="nx-card-hover" style={{ ...cardStyle(t), padding: 16, '--nx-glow': t.green } as React.CSSProperties}>
                        <Statistic title={<Text style={{ color: t.muted }}>Last 24h</Text>} value={last24h} prefix={<ClockCircleOutlined />} valueStyle={{ color: t.green }} />
                    </TiltCard>
                </Col>
            </Row>

            {/* Filters */}
            <div style={{ ...cardStyle(t), height: 'auto', padding: '12px 16px', marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
                <FilterOutlined style={{ color: t.muted }} />
                <Select
                    allowClear placeholder="Action"
                    style={{ width: 200 }}
                    value={actionFilter}
                    onChange={setActionFilter}
                    options={uniqueActions.map(a => ({ value: a, label: a.replace(/_/g, ' ') }))}
                />
                <Select
                    allowClear placeholder="Actor type"
                    style={{ width: 140 }}
                    value={actorFilter}
                    onChange={setActorFilter}
                    options={[{ value: 'user', label: 'User' }, { value: 'agent', label: 'Agent' }]}
                />
                <RangePicker
                    showTime
                    onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)}
                    style={{ flex: 1, maxWidth: 400 }}
                />
            </div>

            {/* Table */}
            <div className="nx-table" style={{ ...cardStyle(t), padding: 0, height: 'auto', overflow: 'visible' }}>
                <Table
                    rowKey="id"
                    dataSource={events}
                    columns={columns}
                    loading={isLoading}
                    pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `${total} events` }}
                    size="small"
                    rowClassName={(rec: AuditEvent) =>
                        ['login_failed', 'secret_decrypt_denied'].includes(rec.action) ? 'nx-row-critical' :
                        ['api_key_revoke', 'api_key_disable'].includes(rec.action) ? 'nx-row-warning' : ''
                    }
                />
            </div>
        </div>
    );
}
