import { Table, Button, Modal, Form, Input, InputNumber, Typography, Space, Tag, Card, message, Tooltip, Row, Col, Progress, Drawer, Empty, Alert, Popconfirm, Upload } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { pbxClient } from '../api/pbxClient';
import React, { useState } from 'react';
import {
    PhoneOutlined, PlusOutlined, ReloadOutlined, CheckCircleOutlined,
    CloseCircleOutlined, DashboardOutlined, LoadingOutlined, DeleteOutlined,
    SyncOutlined, WarningOutlined, ClockCircleOutlined,
    ApiOutlined, HddOutlined, KeyOutlined, SafetyCertificateOutlined, EditOutlined, UploadOutlined,
} from '@ant-design/icons';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer } from '../theme';

const { Title, Text } = Typography;

// ─── Interfaces ──────────────────────────────────────────────────────────────

interface FleetNode {
    target_id: string;
    name: string;
    host: string;
    status: string;
    online: boolean;
    ssh_ok: boolean;
    ami_ok: boolean;
    asterisk_up: boolean;
    asterisk_version: string | null;
    sip_registrations: number;
    active_calls: number;
    calls_24h: number;
    uptime_seconds: number;
    uptime_human: string | null;
    cpu_pct: number | null;
    ram_used_mb: number | null;
    ram_total_mb: number | null;
    ram_pct: number | null;
    disk_used_gb: number | null;
    disk_total_gb: number | null;
    disk_pct: number | null;
    last_polled_at: string | null;
    poll_error: string | null;
}

interface FleetSummary {
    total_targets: number;
    online: number;
    offline: number;
    asterisk_up: number;
    asterisk_down: number;
    total_active_calls: number;
    total_calls_24h: number;
    total_registrations: number;
    avg_cpu_pct: number | null;
    avg_ram_pct: number | null;
    avg_disk_pct: number | null;
}

interface FleetStatus {
    nodes: FleetNode[];
    summary: FleetSummary;
    refreshing: boolean;
    collected_at: string | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatUptime(seconds: number): string {
    if (seconds <= 0) return '—';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

function pctColor(pct: number | null): string {
    if (pct === null) return '#475569';
    if (pct > 90) return '#ef4444';
    if (pct > 70) return '#f59e0b';
    return '#22c55e';
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function IntegrationsPbx() {
    const queryClient = useQueryClient();
    const { mode } = useThemeStore();
    const t = getTokens(mode);
    const [detailNode, setDetailNode] = useState<FleetNode | null>(null);
    const [addOpen, setAddOpen] = useState(false);
    const [addForm] = Form.useForm();
    const [regResult, setRegResult] = useState<any>(null);
    const [verifyResult, setVerifyResult] = useState<any>(null);
    const [verifyingNodeId, setVerifyingNodeId] = useState<string | null>(null);
    const [verifyStreaming, setVerifyStreaming] = useState(false);
    const [editTarget, setEditTarget] = useState<any>(null);
    const [editForm] = Form.useForm();

    // Fleet status query
    const { data: fleet, isLoading, refetch } = useQuery<FleetStatus>({
        queryKey: ['pbx_fleet_status'],
        queryFn: async () => (await pbxClient.get('/v1/fleet/status')).data,
        refetchInterval: 30000,
    });

    // Force refresh
    const refreshMutation = useMutation({
        mutationFn: async () => (await pbxClient.post('/v1/fleet/refresh')).data,
        onSuccess: (data) => {
            if (data.ok) {
                message.success(`Fleet refreshed: ${data.online} online, ${data.offline} offline`);
                queryClient.invalidateQueries({ queryKey: ['pbx_fleet_status'] });
            }
        },
        onError: () => message.error('Fleet refresh failed'),
    });

    // Register + Verify PBX target
    const addMutation = useMutation({
        mutationFn: async (values: any) => (await pbxClient.post('/v1/targets/register', values)).data,
        onSuccess: (data: any) => {
            setRegResult(data);
            if (data.registered) {
                queryClient.invalidateQueries({ queryKey: ['pbx_fleet_status'] });
            }
        },
        onError: (e: any) => {
            const detail = e?.response?.data?.detail;
            const status = e?.response?.status;
            let msg = 'Registration failed';
            if (typeof detail === 'string') {
                msg = detail;
            } else if (Array.isArray(detail)) {
                msg = detail.map((d: any) => `${d.loc?.join('.')}: ${d.msg}`).join('; ');
            } else if (status) {
                msg = `Server returned ${status}${e?.response?.statusText ? ` (${e.response.statusText})` : ''}`;
            } else if (e?.code === 'ERR_NETWORK' || e?.message?.includes('Network')) {
                msg = 'Cannot reach PBX agent — check if the service is running';
            } else if (e?.message) {
                msg = e.message;
            }
            message.error(msg, 6);
        },
    });

    // Verify existing PBX target via SSE stream
    const startVerifyStream = async (targetId: string, targetName: string) => {
        setVerifyingNodeId(targetId);
        setVerifyResult({ target_name: targetName, target_id: targetId, checks: [] });
        setVerifyStreaming(true);
        try {
            const resp = await fetch(`/pbx/v1/targets/${targetId}/verify-stream?tenant_id=acme&env=prod`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Service-ID': 'nexus',
                    'X-Agent-Key': import.meta.env.VITE_PBX_AGENT_KEY || 'nexus-pbx-key-change-me',
                },
            });
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            const reader = resp.body!.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                // Process complete SSE events from buffer
                const parts = buffer.split('\n\n');
                buffer = parts.pop() || '';
                for (const part of parts) {
                    if (!part.trim()) continue;
                    const lines = part.split('\n');
                    let eventType = '';
                    let data = '';
                    for (const line of lines) {
                        if (line.startsWith('event: ')) eventType = line.slice(7);
                        if (line.startsWith('data: ')) data = line.slice(6);
                    }
                    if (eventType === 'check' && data) {
                        const check = JSON.parse(data);
                        setVerifyResult((prev: any) => ({
                            ...prev,
                            checks: [...(prev?.checks || []), check],
                        }));
                    }
                    if (eventType === 'done') {
                        setVerifyStreaming(false);
                    }
                }
            }
        } catch (e: any) {
            message.error(e?.message || 'Verify stream failed');
        } finally {
            setVerifyingNodeId(null);
            setVerifyStreaming(false);
        }
    };

    // Edit existing PBX target
    const openEditModal = async (node: FleetNode) => {
        try {
            const resp = await pbxClient.get(`/v1/targets/${node.target_id}?tenant_id=acme&env=prod`);
            const t = resp.data;
            setEditTarget(t);
            editForm.setFieldsValue({
                name: t.name, host: t.host, ssh_port: t.ssh_port,
                ssh_username: t.ssh_username, ami_port: t.ami_port,
                ami_username: t.ami_username,
            });
        } catch {
            message.error('Failed to load target details');
        }
    };

    const editMutation = useMutation({
        mutationFn: async (values: any) => {
            // Strip empty credential fields so we don't overwrite existing secrets
            const cleaned = { ...values };
            for (const key of ['ami_secret', 'ssh_key_pem', 'ssh_password']) {
                if (!cleaned[key] || !cleaned[key].trim()) {
                    delete cleaned[key];
                }
            }
            return (await pbxClient.put(
                `/v1/targets/${editTarget.id}/edit?tenant_id=${editTarget.tenant_id}&env=${editTarget.env}`,
                cleaned,
            )).data;
        },
        onSuccess: () => {
            message.success('Target updated successfully');
            setEditTarget(null);
            setDetailNode(null);
            editForm.resetFields();
            queryClient.invalidateQueries({ queryKey: ['pbx-fleet'] });
        },
        onError: (e: any) => {
            message.error(e?.response?.data?.detail || 'Update failed');
        },
    });

    const nodes = fleet?.nodes || [];
    const summary = fleet?.summary || {} as FleetSummary;

    const collectedAt = fleet?.collected_at;
    const ageSeconds = collectedAt ? Math.round((Date.now() - new Date(collectedAt).getTime()) / 1000) : null;
    const ageLabel = ageSeconds !== null ? (ageSeconds < 60 ? `${ageSeconds}s ago` : `${Math.round(ageSeconds / 60)}m ago`) : 'never';

    // ─── Panel styles ────────────────────────────────────────────────
    const panelCard: React.CSSProperties = {
        borderRadius: 14,
        border: '1px solid #1e293b',
        background: 'linear-gradient(145deg, #161d2e 0%, #111827 100%)',
        boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
        transition: 'transform 0.2s, box-shadow 0.2s',
        height: '100%',
    };

    // ─── Table columns ───────────────────────────────────────────────
    const columns = [
        {
            title: 'PBX',
            key: 'name',
            width: 180,
            sorter: (a: FleetNode, b: FleetNode) => a.name.localeCompare(b.name),
            render: (_: any, r: FleetNode) => (
                <Space>
                    <span className={`health-dot ${r.online ? 'health-dot-ok' : 'health-dot-err'}`} />
                    <Text strong style={{ color: '#e2e8f0', cursor: 'pointer' }}
                        onClick={() => setDetailNode(r)}>{r.name}</Text>
                </Space>
            ),
        },
        {
            title: 'Host',
            dataIndex: 'host',
            key: 'host',
            width: 150,
            sorter: (a: FleetNode, b: FleetNode) => (a.host || '').localeCompare(b.host || ''),
            render: (h: string) => <Text style={{ color: '#94a3b8', fontSize: 12 }}>{h}</Text>,
        },
        {
            title: 'Status',
            key: 'status',
            width: 90,
            sorter: (a: FleetNode, b: FleetNode) => {
                const rank = (n: FleetNode) => !n.online ? 0 : !n.ami_ok ? 1 : 2;
                return rank(a) - rank(b);
            },
            render: (_: any, r: FleetNode) => {
                if (!r.online) return <Tag style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 4 }}>Offline</Tag>;
                if (!r.ami_ok) return <Tag style={{ background: 'rgba(34,197,94,0.15)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.3)', borderRadius: 4 }}>No-AMI</Tag>;
                return <Tag style={{ background: 'rgba(34,197,94,0.15)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.3)', borderRadius: 4 }}>Online</Tag>;
            },
        },
        {
            title: 'Asterisk',
            key: 'asterisk',
            width: 120,
            render: (_: any, r: FleetNode) => {
                if (!r.online) return <Text style={{ color: '#475569' }}>—</Text>;
                return (
                    <Tooltip title={r.asterisk_version || 'Unknown version'}>
                        <Space size={4}>
                            {r.asterisk_up
                                ? <CheckCircleOutlined style={{ color: '#22c55e' }} />
                                : <CloseCircleOutlined style={{ color: '#ef4444' }} />}
                            <Text style={{ color: r.asterisk_up ? '#4ade80' : '#f87171', fontSize: 12 }}>
                                {r.asterisk_up ? (r.asterisk_version || 'Running') : 'Down'}
                            </Text>
                        </Space>
                    </Tooltip>
                );
            },
        },
        {
            title: 'SIP Regs',
            key: 'sip_regs',
            width: 80,
            sorter: (a: FleetNode, b: FleetNode) => a.sip_registrations - b.sip_registrations,
            render: (_: any, r: FleetNode) => {
                if (!r.online) return <Text style={{ color: '#475569' }}>—</Text>;
                return <Text strong style={{ color: r.sip_registrations > 0 ? '#60a5fa' : '#475569' }}>{r.sip_registrations}</Text>;
            },
        },
        {
            title: 'Calls',
            key: 'calls',
            width: 90,
            sorter: (a: FleetNode, b: FleetNode) => a.active_calls - b.active_calls,
            render: (_: any, r: FleetNode) => {
                if (!r.online) return <Text style={{ color: '#475569' }}>—</Text>;
                return (
                    <Tooltip title={`Active: ${r.active_calls} | 24h: ${r.calls_24h}`}>
                        <Space size={4}>
                            <PhoneOutlined style={{ color: r.active_calls > 0 ? '#22c55e' : '#334155', fontSize: 12 }} />
                            <Text strong style={{ color: r.active_calls > 0 ? '#4ade80' : '#475569' }}>{r.active_calls}</Text>
                            {r.calls_24h > 0 && <Text style={{ color: '#64748b', fontSize: 11 }}>({r.calls_24h})</Text>}
                        </Space>
                    </Tooltip>
                );
            },
        },
        {
            title: 'CPU',
            key: 'cpu',
            width: 80,
            sorter: (a: FleetNode, b: FleetNode) => (a.cpu_pct ?? 0) - (b.cpu_pct ?? 0),
            render: (_: any, r: FleetNode) => {
                if (r.cpu_pct === null) return <Text style={{ color: '#475569' }}>—</Text>;
                return (
                    <Tooltip title={`CPU: ${r.cpu_pct}%`}>
                        <Progress percent={r.cpu_pct} size="small" strokeColor={pctColor(r.cpu_pct)}
                            trailColor="#1e293b" format={() => <span style={{ color: '#94a3b8', fontSize: 11 }}>{r.cpu_pct}%</span>} />
                    </Tooltip>
                );
            },
        },
        {
            title: 'RAM',
            key: 'ram',
            width: 90,
            sorter: (a: FleetNode, b: FleetNode) => (a.ram_pct ?? 0) - (b.ram_pct ?? 0),
            render: (_: any, r: FleetNode) => {
                if (r.ram_pct === null) return <Text style={{ color: '#475569' }}>—</Text>;
                return (
                    <Tooltip title={`${r.ram_used_mb ?? 0} / ${r.ram_total_mb ?? 0} MB`}>
                        <Progress percent={r.ram_pct} size="small" strokeColor={pctColor(r.ram_pct)}
                            trailColor="#1e293b" format={() => <span style={{ color: '#94a3b8', fontSize: 11 }}>{r.ram_pct}%</span>} />
                    </Tooltip>
                );
            },
        },
        {
            title: 'Disk',
            key: 'disk',
            width: 90,
            sorter: (a: FleetNode, b: FleetNode) => (a.disk_pct ?? 0) - (b.disk_pct ?? 0),
            render: (_: any, r: FleetNode) => {
                if (r.disk_pct === null) return <Text style={{ color: '#475569' }}>—</Text>;
                return (
                    <Tooltip title={`${r.disk_used_gb ?? 0} / ${r.disk_total_gb ?? 0} GB`}>
                        <Progress percent={r.disk_pct} size="small" strokeColor={pctColor(r.disk_pct)}
                            trailColor="#1e293b" format={() => <span style={{ color: '#94a3b8', fontSize: 11 }}>{r.disk_pct}%</span>} />
                    </Tooltip>
                );
            },
        },
        {
            title: 'Uptime',
            key: 'uptime',
            width: 80,
            render: (_: any, r: FleetNode) => {
                if (!r.online || r.uptime_seconds <= 0) return <Text style={{ color: '#475569' }}>—</Text>;
                return <Text style={{ color: '#94a3b8', fontSize: 12 }}>{formatUptime(r.uptime_seconds)}</Text>;
            },
        },
        {
            title: '',
            key: 'actions',
            width: 140,
            render: (_: any, r: FleetNode) => (
                <Space size={4}>
                    <Tooltip title="Verify Connectivity">
                        <Button size="small" icon={<SafetyCertificateOutlined />}
                            loading={verifyingNodeId === r.target_id}
                            style={{ background: 'rgba(34,197,94,0.15)', borderColor: 'rgba(34,197,94,0.3)', color: '#4ade80' }}
                            onClick={() => startVerifyStream(r.target_id, r.name)} />
                    </Tooltip>
                    <Tooltip title="View Details">
                        <Button size="small" icon={<DashboardOutlined />}
                            style={{ background: 'rgba(59,130,246,0.15)', borderColor: 'rgba(59,130,246,0.3)', color: '#60a5fa' }}
                            onClick={() => setDetailNode(r)} />
                    </Tooltip>
                    <Popconfirm
                        title={<span style={{ color: '#e2e8f0' }}>Remove {r.name}?</span>}
                        description={<span style={{ color: '#94a3b8' }}>This removes it from the fleet list only — the server itself is not affected.</span>}
                        onConfirm={async () => {
                            try {
                                await pbxClient.delete(`/v1/targets/${r.target_id}`);
                                message.success(`${r.name} removed from fleet`);
                                // Immediately remove from local cache so UI updates instantly
                                queryClient.setQueryData(['pbx_fleet_status'], (old: any) => {
                                    if (!old) return old;
                                    return {
                                        ...old,
                                        nodes: old.nodes?.filter((n: any) => n.target_id !== r.target_id) || [],
                                    };
                                });
                                refetch();
                            } catch (e: any) {
                                message.error(e?.response?.data?.detail || 'Delete failed');
                            }
                        }}
                        okText="Remove"
                        okButtonProps={{ danger: true }}
                        placement="left"
                    >
                        <Tooltip title="Remove from Fleet">
                            <Button size="small" icon={<DeleteOutlined />}
                                style={{ background: 'rgba(239,68,68,0.15)', borderColor: 'rgba(239,68,68,0.3)', color: '#f87171' }} />
                        </Tooltip>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div style={pageContainer(t)}>
            <style>{`
                .health-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
                .health-dot-ok { background: #22c55e; box-shadow: 0 0 10px rgba(34,197,94,0.6); }
                .health-dot-err { background: #ef4444; box-shadow: 0 0 10px rgba(239,68,68,0.6); }
                .nx-card-hover:hover { transform: translateY(-4px); box-shadow: 0 10px 32px rgba(0,0,0,0.5) !important; }
                .stat-mini { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
                .stat-mini-value { font-size: 18px; font-weight: 700; line-height: 1.2; }
                .stat-mini-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
                .panel-title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; }
                /* Midnight table */
                .pbx-table .ant-table { background: transparent !important; color: #cbd5e1 !important; }
                .pbx-table .ant-table-container { border: none !important; }
                .pbx-table .ant-table-thead > tr > th { background: #1a2235 !important; color: #94a3b8 !important; border-bottom: 1px solid #1e293b !important; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
                .pbx-table .ant-table-thead > tr > th::before { background: #1e293b !important; }
                .pbx-table .ant-table-tbody > tr > td { border-bottom: 1px solid #1e293b !important; color: #cbd5e1 !important; background: transparent !important; }
                .pbx-table .ant-table-tbody > tr:hover > td { background: #1a2640 !important; }
                .pbx-table .ant-typography { color: #cbd5e1 !important; }
                .pbx-table .ant-typography strong { color: #e2e8f0 !important; }
                .pbx-table .ant-progress-text { color: #94a3b8 !important; }
                .pbx-table .ant-progress-inner { background: #1e293b !important; }
                .pbx-table .ant-pagination { color: #94a3b8; }
                .pbx-table .ant-pagination .ant-pagination-item { background: #161d2e; border-color: #1e293b; }
                .pbx-table .ant-pagination .ant-pagination-item a { color: #94a3b8; }
                .pbx-table .ant-pagination .ant-pagination-item-active { border-color: #3b82f6; }
                .pbx-table .ant-pagination .ant-pagination-item-active a { color: #3b82f6; }
                .pbx-table .ant-select-selector { background: #161d2e !important; border-color: #1e293b !important; color: #94a3b8 !important; }
                .pbx-table .ant-table-column-sorter { color: #475569 !important; }
                .pbx-table .ant-empty-description { color: #475569 !important; }
                .pbx-table .ant-btn { border-color: #334155 !important; }
                .pbx-table .ant-btn:hover { border-color: #475569 !important; }
                .midnight-header .ant-btn-default { background: #161d2e; border-color: #1e293b; color: #94a3b8; }
                .midnight-header .ant-btn-default:hover { border-color: #334155; color: #e2e8f0; background: #1a2235; }
                .midnight-header .ant-btn-primary { background: linear-gradient(135deg, #3b82f6, #2563eb); border: none; }
                .midnight-header .ant-btn-primary:hover { background: linear-gradient(135deg, #60a5fa, #3b82f6); }
            `}</style>

            {/* Header */}
            <div className="midnight-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: '#e2e8f0' }}>
                        <PhoneOutlined style={{ marginRight: 10, color: '#a78bfa' }} />PBX Fleet Management
                    </Title>
                    <Text style={{ color: '#64748b', fontSize: 12 }}>
                        {fleet?.refreshing ? <><SyncOutlined spin style={{ marginRight: 4 }} />Refreshing...</>
                            : <>Updated: {ageLabel}</>}
                    </Text>
                </div>
                <Space>
                    <Button icon={<ReloadOutlined />}
                        loading={refreshMutation.isPending}
                        onClick={() => { refreshMutation.mutate(); refetch(); }}>
                        Refresh Fleet
                    </Button>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
                        Add PBX
                    </Button>
                </Space>
            </div>

            {/* Summary Cards */}
            <Row gutter={[20, 20]} style={{ marginBottom: 28 }}>
                {/* Panel 1: Fleet Overview */}
                <Col xs={24} sm={12} lg={6}>
                    <Card size="small" className="nx-card-hover" style={panelCard}>
                        <div className="panel-title"><span><PhoneOutlined style={{ marginRight: 6 }} />PBX Fleet</span></div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                            <Progress
                                type="circle"
                                percent={summary.total_targets > 0 ? Math.round((summary.online / summary.total_targets) * 100) : 0}
                                size={90}
                                strokeColor={{ '0%': '#22c55e', '100%': '#14b8a6' }}
                                trailColor="#1e293b"
                                format={() => (
                                    <div style={{ textAlign: 'center' }}>
                                        <div style={{ fontSize: 28, fontWeight: 800, color: '#e2e8f0', lineHeight: 1 }}>{summary.total_targets || 0}</div>
                                        <div style={{ fontSize: 10, color: '#64748b' }}>Total</div>
                                    </div>
                                )}
                            />
                            <div>
                                <div className="stat-mini">
                                    <CheckCircleOutlined style={{ color: '#22c55e', fontSize: 14 }} />
                                    <span className="stat-mini-value" style={{ color: '#22c55e' }}>{summary.online || 0}</span>
                                    <span className="stat-mini-label">Online</span>
                                </div>
                                <div className="stat-mini">
                                    <CloseCircleOutlined style={{ color: (summary.offline || 0) > 0 ? '#ef4444' : '#334155', fontSize: 14 }} />
                                    <span className="stat-mini-value" style={{ color: (summary.offline || 0) > 0 ? '#ef4444' : '#475569' }}>{summary.offline || 0}</span>
                                    <span className="stat-mini-label">Offline</span>
                                </div>
                            </div>
                        </div>
                    </Card>
                </Col>

                {/* Panel 2: Call Activity */}
                <Col xs={24} sm={12} lg={6}>
                    <Card size="small" className="nx-card-hover" style={panelCard}>
                        <div className="panel-title"><span><PhoneOutlined style={{ marginRight: 6 }} />Call Activity</span></div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 20, paddingTop: 4 }}>
                            <div style={{
                                width: 90, height: 90, minWidth: 90, minHeight: 90,
                                flexShrink: 0, aspectRatio: '1 / 1', borderRadius: '50%',
                                background: (summary.total_active_calls || 0) > 0
                                    ? 'linear-gradient(135deg, #065f4633, #22c55e44)'
                                    : 'linear-gradient(135deg, #1e293b, #0f172a)',
                                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                                border: `3px solid ${(summary.total_active_calls || 0) > 0 ? '#22c55e' : '#1e293b'}`,
                                boxShadow: (summary.total_active_calls || 0) > 0 ? '0 0 16px rgba(34,197,94,0.3)' : 'none',
                            }}>
                                <div style={{ fontSize: 26, fontWeight: 800, color: (summary.total_active_calls || 0) > 0 ? '#4ade80' : '#475569', lineHeight: 1 }}>{summary.total_active_calls || 0}</div>
                                <div style={{ fontSize: 10, color: '#64748b' }}>Active</div>
                            </div>
                            <div>
                                <div className="stat-mini">
                                    <ClockCircleOutlined style={{ color: '#3b82f6', fontSize: 14 }} />
                                    <span className="stat-mini-value" style={{ color: '#60a5fa' }}>{(summary.total_calls_24h || 0).toLocaleString()}</span>
                                    <span className="stat-mini-label">24h Volume</span>
                                </div>
                                <div className="stat-mini">
                                    <ApiOutlined style={{ color: (summary.asterisk_up || 0) === summary.total_targets ? '#22c55e' : '#f59e0b', fontSize: 14 }} />
                                    <span className="stat-mini-value">{summary.asterisk_up || 0}/{summary.total_targets || 0}</span>
                                    <span className="stat-mini-label">Asterisk Up</span>
                                </div>
                            </div>
                        </div>
                    </Card>
                </Col>

                {/* Panel 3: Registrations */}
                <Col xs={24} sm={12} lg={6}>
                    <Card size="small" className="nx-card-hover" style={panelCard}>
                        <div className="panel-title"><span><ApiOutlined style={{ marginRight: 6 }} />SIP Registrations</span></div>
                        <div style={{ paddingTop: 8 }}>
                            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 16 }}>
                                <span style={{ fontSize: 36, fontWeight: 800, color: '#e2e8f0' }}>{(summary.total_registrations || 0).toLocaleString()}</span>
                                <span style={{ fontSize: 13, color: '#64748b' }}>Active</span>
                            </div>
                            <div style={{ display: 'flex', gap: 16 }}>
                                {nodes.filter(n => n.online).slice(0, 4).map(n => (
                                    <Tooltip key={n.target_id} title={`${n.name}: ${n.sip_registrations} regs`}>
                                        <div style={{ textAlign: 'center' }}>
                                            <div style={{ fontSize: 16, fontWeight: 700, color: '#60a5fa' }}>{n.sip_registrations}</div>
                                            <div style={{ fontSize: 9, color: '#475569', maxWidth: 50, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.name}</div>
                                        </div>
                                    </Tooltip>
                                ))}
                            </div>
                        </div>
                    </Card>
                </Col>

                {/* Panel 4: System Health */}
                <Col xs={24} sm={12} lg={6}>
                    <Card size="small" className="nx-card-hover" style={panelCard}>
                        <div className="panel-title"><span><HddOutlined style={{ marginRight: 6 }} />System Health</span></div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingTop: 4 }}>
                            {[
                                { label: 'Avg CPU', pct: summary.avg_cpu_pct },
                                { label: 'Avg RAM', pct: summary.avg_ram_pct },
                                { label: 'Avg Disk', pct: summary.avg_disk_pct },
                            ].map(m => (
                                <div key={m.label}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                                        <span style={{ fontSize: 11, color: '#94a3b8' }}>{m.label}</span>
                                        <span style={{ fontSize: 12, fontWeight: 600, color: pctColor(m.pct) }}>
                                            {m.pct !== null && m.pct !== undefined ? `${m.pct}%` : '—'}
                                        </span>
                                    </div>
                                    <Progress
                                        percent={m.pct ?? 0}
                                        showInfo={false}
                                        size="small"
                                        strokeColor={pctColor(m.pct)}
                                        trailColor="#1e293b"
                                    />
                                </div>
                            ))}
                        </div>
                    </Card>
                </Col>
            </Row>

            {/* Fleet Table */}
            <div className="pbx-table">
                <Table
                    dataSource={nodes}
                    columns={columns}
                    rowKey="target_id"
                    loading={isLoading}
                    size="middle"
                    pagination={{ defaultPageSize: 25, pageSizeOptions: ['10', '25', '50', '100'], showSizeChanger: true, showTotal: (total) => `${total} PBX systems` }}
                    locale={{
                        emptyText: (
                            <Empty
                                image={Empty.PRESENTED_IMAGE_SIMPLE}
                                description={<span style={{ color: '#475569' }}>No PBX targets registered. Click "Add PBX" to get started.</span>}
                            />
                        )
                    }}
                />
            </div>

            {/* Detail Drawer */}
            <Drawer
                title={
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                        <span style={{ color: '#e2e8f0' }}><PhoneOutlined style={{ marginRight: 8, color: '#a78bfa' }} />{detailNode?.name}</span>
                        {detailNode && (
                            <Button size="small" icon={<EditOutlined />}
                                style={{ background: 'rgba(59,130,246,0.15)', borderColor: 'rgba(59,130,246,0.3)', color: '#60a5fa', marginRight: 24 }}
                                onClick={() => { openEditModal(detailNode); }}
                            >Edit</Button>
                        )}
                    </div>
                }
                open={!!detailNode}
                onClose={() => setDetailNode(null)}
                width={520}
                styles={{
                    header: { background: '#0f1729', borderBottom: '1px solid #1e293b' },
                    body: { background: '#111827', padding: 24 },
                }}
            >
                {detailNode && (
                    <Space direction="vertical" style={{ width: '100%' }} size={20}>
                        {/* Connection Status */}
                        <Card size="small" style={{ background: '#161d2e', border: '1px solid #1e293b', borderRadius: 10 }}>
                            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: '#94a3b8', marginBottom: 12 }}>Connection</div>
                            <Row gutter={16}>
                                <Col span={8}>
                                    <div style={{ textAlign: 'center' }}>
                                        <span className={`health-dot ${detailNode.online ? 'health-dot-ok' : 'health-dot-err'}`} />
                                        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>Network</div>
                                    </div>
                                </Col>
                                <Col span={8}>
                                    <div style={{ textAlign: 'center' }}>
                                        <span className={`health-dot ${detailNode.ssh_ok ? 'health-dot-ok' : 'health-dot-err'}`} />
                                        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>SSH</div>
                                    </div>
                                </Col>
                                <Col span={8}>
                                    <div style={{ textAlign: 'center' }}>
                                        <span className={`health-dot ${detailNode.asterisk_up ? 'health-dot-ok' : 'health-dot-err'}`} />
                                        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>Asterisk</div>
                                    </div>
                                </Col>
                            </Row>
                            {detailNode.poll_error && (
                                <div style={{ marginTop: 12, padding: 8, background: 'rgba(239,68,68,0.1)', borderRadius: 6, border: '1px solid rgba(239,68,68,0.2)' }}>
                                    <Text style={{ color: '#f87171', fontSize: 12 }}><WarningOutlined style={{ marginRight: 4 }} />{detailNode.poll_error}</Text>
                                </div>
                            )}
                        </Card>

                        {/* Asterisk Details */}
                        <Card size="small" style={{ background: '#161d2e', border: '1px solid #1e293b', borderRadius: 10 }}>
                            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: '#94a3b8', marginBottom: 12 }}>Asterisk</div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                                <div><div style={{ color: '#64748b', fontSize: 11 }}>Version</div><div style={{ color: '#e2e8f0', fontWeight: 600 }}>{detailNode.asterisk_version || '—'}</div></div>
                                <div><div style={{ color: '#64748b', fontSize: 11 }}>Uptime</div><div style={{ color: '#e2e8f0', fontWeight: 600 }}>{formatUptime(detailNode.uptime_seconds)}</div></div>
                                <div><div style={{ color: '#64748b', fontSize: 11 }}>Active Calls</div><div style={{ color: '#4ade80', fontSize: 22, fontWeight: 800 }}>{detailNode.active_calls}</div></div>
                                <div><div style={{ color: '#64748b', fontSize: 11 }}>Calls (24h)</div><div style={{ color: '#60a5fa', fontSize: 22, fontWeight: 800 }}>{detailNode.calls_24h.toLocaleString()}</div></div>
                                <div><div style={{ color: '#64748b', fontSize: 11 }}>SIP Registrations</div><div style={{ color: '#e2e8f0', fontSize: 18, fontWeight: 700 }}>{detailNode.sip_registrations}</div></div>
                            </div>
                        </Card>

                        {/* System Resources */}
                        <Card size="small" style={{ background: '#161d2e', border: '1px solid #1e293b', borderRadius: 10 }}>
                            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: '#94a3b8', marginBottom: 12 }}>System Resources</div>
                            {[
                                { label: 'CPU', pct: detailNode.cpu_pct, detail: detailNode.cpu_pct !== null ? `${detailNode.cpu_pct}%` : null },
                                { label: 'RAM', pct: detailNode.ram_pct, detail: detailNode.ram_used_mb !== null ? `${detailNode.ram_used_mb} / ${detailNode.ram_total_mb} MB` : null },
                                { label: 'Disk', pct: detailNode.disk_pct, detail: detailNode.disk_used_gb !== null ? `${detailNode.disk_used_gb} / ${detailNode.disk_total_gb} GB` : null },
                            ].map(m => (
                                <div key={m.label} style={{ marginBottom: 12 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                        <span style={{ color: '#94a3b8', fontSize: 12 }}>{m.label}</span>
                                        <span style={{ color: pctColor(m.pct), fontSize: 13, fontWeight: 700 }}>{m.pct !== null ? `${m.pct}%` : '—'}</span>
                                    </div>
                                    <Progress percent={m.pct ?? 0} showInfo={false} strokeColor={pctColor(m.pct)} trailColor="#1e293b" />
                                    {m.detail && <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{m.detail}</div>}
                                </div>
                            ))}
                        </Card>

                        {/* Metadata */}
                        <Card size="small" style={{ background: '#161d2e', border: '1px solid #1e293b', borderRadius: 10 }}>
                            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: '#94a3b8', marginBottom: 12 }}>Info</div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                                <div><span style={{ color: '#64748b', fontSize: 11 }}>Host: </span><span style={{ color: '#e2e8f0', fontSize: 12 }}>{detailNode.host}</span></div>
                                <div><span style={{ color: '#64748b', fontSize: 11 }}>Target ID: </span><span style={{ color: '#94a3b8', fontSize: 11 }}>{detailNode.target_id.slice(0, 8)}…</span></div>
                                <div><span style={{ color: '#64748b', fontSize: 11 }}>Last Poll: </span><span style={{ color: '#94a3b8', fontSize: 11 }}>{detailNode.last_polled_at ? new Date(detailNode.last_polled_at).toLocaleTimeString() : '—'}</span></div>
                            </div>
                        </Card>
                    </Space>
                )}
            </Drawer>

            {/* Add PBX Modal */}
            <Modal
                title={<span style={{ color: '#e2e8f0' }}><PlusOutlined style={{ marginRight: 8 }} />Register PBX Target</span>}
                open={addOpen}
                onCancel={() => { setAddOpen(false); setRegResult(null); }}
                onOk={() => regResult ? (() => { setAddOpen(false); setRegResult(null); addForm.resetFields(); })() : addForm.submit()}
                confirmLoading={addMutation.isPending}
                okText={regResult ? 'Done' : 'Register & Verify'}
                width={600}
                styles={{
                    header: { background: '#0f1729', borderBottom: '1px solid #1e293b' },
                    body: { background: '#111827', maxHeight: '70vh', overflowY: 'auto' },
                    footer: { background: '#0f1729', borderTop: '1px solid #1e293b' },
                }}
            >
                {!regResult ? (
                <Form form={addForm} layout="vertical" onFinish={(values: any) => addMutation.mutate(values)}
                    initialValues={{ tenant_id: 'acme', env: 'prod', ami_port: 5038, ssh_port: 22, ssh_username: 'root' }}>
                    <Form.Item name="name" label={<span style={{ color: '#94a3b8' }}>PBX Name</span>} rules={[{ required: true }]}>
                        <Input placeholder="e.g. PBX-Residential" style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                    </Form.Item>
                    <Row gutter={12}>
                        <Col span={16}>
                            <Form.Item name="host" label={<span style={{ color: '#94a3b8' }}>Host / IP</span>} rules={[{ required: true }]}>
                                <Input placeholder="192.168.1.10 or residential.gsmcall.com" style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                            </Form.Item>
                        </Col>
                        <Col span={8}>
                            <Form.Item name="ssh_port" label={<span style={{ color: '#94a3b8' }}>SSH Port</span>}>
                                <InputNumber style={{ width: '100%', background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Row gutter={12}>
                        <Col span={8}>
                            <Form.Item name="ami_port" label={<span style={{ color: '#94a3b8' }}>AMI Port</span>}>
                                <InputNumber style={{ width: '100%', background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                            </Form.Item>
                        </Col>
                        <Col span={16}>
                            <Form.Item name="ami_username" label={<span style={{ color: '#94a3b8' }}>AMI Username</span>} rules={[{ required: true }]}>
                                <Input placeholder="nexus-monitor" style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Form.Item name="ami_secret" label={<span style={{ color: '#94a3b8' }}><KeyOutlined style={{ marginRight: 4 }} />AMI Secret / Password</span>} rules={[{ required: true }]}>
                        <Input.Password placeholder="AMI password from manager.conf" style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                    </Form.Item>
                    <Form.Item name="ssh_username" label={<span style={{ color: '#94a3b8' }}>SSH Username</span>}>
                        <Input placeholder="root" style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                    </Form.Item>
                    <Form.Item name="ssh_key_pem" label={<span style={{ color: '#94a3b8' }}><KeyOutlined style={{ marginRight: 4 }} />SSH Private Key (optional)</span>}>
                        <Input.TextArea
                            rows={4}
                            placeholder={'Paste key, or use Upload below for .ppk / .pem files'}
                            style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0', fontFamily: 'monospace', fontSize: 11 }}
                        />
                    </Form.Item>
                    <Upload accept=".ppk,.pem,.key,.id_rsa" beforeUpload={(file: any) => { const reader = new FileReader(); reader.onload = (e) => { addForm.setFieldValue('ssh_key_pem', e.target?.result as string); message.success(`Loaded ${file.name}`); }; reader.readAsText(file); return false; }} showUploadList={false} maxCount={1}>
                        <Button icon={<UploadOutlined />} size="small" style={{ marginTop: -8, marginBottom: 8 }}>Upload .ppk / .pem Key File</Button>
                    </Upload>
                    <Form.Item name="ssh_password" label={<span style={{ color: '#94a3b8' }}><KeyOutlined style={{ marginRight: 4 }} />SSH Password (optional, fallback)</span>}>
                        <Input.Password placeholder="SSH password" style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                    </Form.Item>
                    <Form.Item name="tenant_id" hidden><Input /></Form.Item>
                    <Form.Item name="env" hidden><Input /></Form.Item>
                </Form>
                ) : (
                <div>
                    {regResult.registered ? (
                        <Alert message={`${regResult.target_name} registered successfully`} type="success" showIcon style={{ marginBottom: 16 }} />
                    ) : (
                        <Alert message={regResult.error || 'Registration failed'} type="error" showIcon style={{ marginBottom: 16 }} />
                    )}
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#94a3b8', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Verification Results</div>
                    <Space direction="vertical" style={{ width: '100%' }} size={8}>
                        {regResult.checks?.map((c: any, i: number) => (
                            <div key={i} style={{
                                display: 'flex', alignItems: 'flex-start', gap: 10,
                                padding: '10px 14px', borderRadius: 8,
                                background: c.passed ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
                                border: `1px solid ${c.passed ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
                            }}>
                                {c.passed ? (
                                    <CheckCircleOutlined style={{ color: '#22c55e', fontSize: 16, marginTop: 2 }} />
                                ) : (
                                    <CloseCircleOutlined style={{ color: '#ef4444', fontSize: 16, marginTop: 2 }} />
                                )}
                                <div style={{ flex: 1 }}>
                                    <div style={{ color: '#e2e8f0', fontWeight: 600, fontSize: 13 }}>{c.check}</div>
                                    {c.detail && <div style={{ color: '#94a3b8', fontSize: 11, marginTop: 2, wordBreak: 'break-all' }}>{c.detail}</div>}
                                </div>
                            </div>
                        ))}
                    </Space>
                </div>
                )}
            </Modal>

            {/* Verify Results Modal */}
            <Modal
                title={<span style={{ color: '#e2e8f0', cursor: 'move' }}><SafetyCertificateOutlined style={{ marginRight: 8, color: '#4ade80' }} />Verify: {verifyResult?.target_name}</span>}
                open={!!verifyResult}
                onCancel={() => { setVerifyResult(null); setVerifyStreaming(false); }}
                onOk={() => setVerifyResult(null)}
                okText="Done"
                okButtonProps={{ disabled: verifyStreaming }}
                cancelButtonProps={{ style: { display: 'none' } }}
                width={550}
                modalRender={(modal) => {
                    const dragRef = React.useRef({ x: 0, y: 0, dragging: false });
                    const [offset, setOffset] = React.useState({ x: 0, y: 0 });
                    return (
                        <div
                            style={{ transform: `translate(${offset.x}px, ${offset.y}px)` }}
                            onMouseDown={(e) => {
                                // Only drag from header area
                                if ((e.target as HTMLElement).closest('.ant-modal-header')) {
                                    dragRef.current = { x: e.clientX - offset.x, y: e.clientY - offset.y, dragging: true };
                                    const onMove = (ev: MouseEvent) => {
                                        if (dragRef.current.dragging) {
                                            setOffset({ x: ev.clientX - dragRef.current.x, y: ev.clientY - dragRef.current.y });
                                        }
                                    };
                                    const onUp = () => { dragRef.current.dragging = false; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
                                    document.addEventListener('mousemove', onMove);
                                    document.addEventListener('mouseup', onUp);
                                }
                            }}
                        >
                            {modal}
                        </div>
                    );
                }}
                styles={{
                    header: { background: '#0f1729', borderBottom: '1px solid #1e293b', cursor: 'move' },
                    body: { background: '#111827', maxHeight: '70vh', overflowY: 'auto' },
                    footer: { background: '#0f1729', borderTop: '1px solid #1e293b' },
                }}
            >
                {verifyResult && (
                    <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#94a3b8', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Connectivity Checks</div>
                        <Space direction="vertical" style={{ width: '100%' }} size={8}>
                            {verifyResult.checks?.map((c: any, i: number) => (
                                <div key={i} style={{
                                    display: 'flex', alignItems: 'flex-start', gap: 10,
                                    padding: '10px 14px', borderRadius: 8,
                                    background: c.passed ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
                                    border: `1px solid ${c.passed ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
                                    animation: 'fadeIn 0.3s ease-in',
                                }}>
                                    {c.passed ? (
                                        <CheckCircleOutlined style={{ color: '#22c55e', fontSize: 16, marginTop: 2 }} />
                                    ) : (
                                        <CloseCircleOutlined style={{ color: '#ef4444', fontSize: 16, marginTop: 2 }} />
                                    )}
                                    <div style={{ flex: 1 }}>
                                        <div style={{ color: '#e2e8f0', fontWeight: 600, fontSize: 13 }}>{c.check}</div>
                                        {c.detail && <div style={{ color: '#94a3b8', fontSize: 11, marginTop: 2, wordBreak: 'break-all' }}>{c.detail}</div>}
                                    </div>
                                </div>
                            ))}
                            {verifyStreaming && (
                                <div style={{
                                    display: 'flex', alignItems: 'center', gap: 10,
                                    padding: '10px 14px', borderRadius: 8,
                                    background: 'rgba(59,130,246,0.08)',
                                    border: '1px solid rgba(59,130,246,0.25)',
                                    animation: 'pulse 1.5s ease-in-out infinite',
                                }}>
                                    <LoadingOutlined style={{ color: '#3b82f6', fontSize: 16 }} />
                                    <div style={{ color: '#93c5fd', fontWeight: 500, fontSize: 13 }}>Running checks…</div>
                                </div>
                            )}
                        </Space>
                    </div>
                )}
            </Modal>

            {/* Edit PBX Modal */}
            <Modal
                title={<span style={{ color: '#e2e8f0' }}><EditOutlined style={{ marginRight: 8, color: '#60a5fa' }} />Edit: {editTarget?.name}</span>}
                open={!!editTarget}
                onCancel={() => { setEditTarget(null); editForm.resetFields(); }}
                onOk={() => editForm.submit()}
                confirmLoading={editMutation.isPending}
                okText="Save Changes"
                width={600}
                styles={{
                    header: { background: '#0f1729', borderBottom: '1px solid #1e293b' },
                    body: { background: '#111827', maxHeight: '70vh', overflowY: 'auto' },
                    footer: { background: '#0f1729', borderTop: '1px solid #1e293b' },
                }}
            >
                <Form form={editForm} layout="vertical" onFinish={(values: any) => editMutation.mutate(values)}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#94a3b8', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Connection Settings</div>
                    <Form.Item name="name" label={<span style={{ color: '#94a3b8' }}>PBX Name</span>}>
                        <Input style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                    </Form.Item>
                    <Row gutter={12}>
                        <Col span={16}>
                            <Form.Item name="host" label={<span style={{ color: '#94a3b8' }}>Host / IP</span>}>
                                <Input style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                            </Form.Item>
                        </Col>
                        <Col span={8}>
                            <Form.Item name="ami_port" label={<span style={{ color: '#94a3b8' }}>AMI Port</span>}>
                                <Input type="number" style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                            </Form.Item>
                        </Col>
                    </Row>
                    <Form.Item name="ami_username" label={<span style={{ color: '#94a3b8' }}>AMI Username</span>}>
                        <Input style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                    </Form.Item>
                    <Row gutter={12}>
                        <Col span={12}>
                            <Form.Item name="ssh_port" label={<span style={{ color: '#94a3b8' }}>SSH Port</span>}>
                                <Input type="number" style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                            </Form.Item>
                        </Col>
                        <Col span={12}>
                            <Form.Item name="ssh_username" label={<span style={{ color: '#94a3b8' }}>SSH Username</span>}>
                                <Input style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                            </Form.Item>
                        </Col>
                    </Row>

                    <div style={{ fontSize: 13, fontWeight: 600, color: '#94a3b8', marginBottom: 12, marginTop: 20, textTransform: 'uppercase', letterSpacing: 1 }}>Credentials <span style={{ fontSize: 11, fontWeight: 400, color: '#64748b', textTransform: 'none' }}>(leave blank to keep existing)</span></div>
                    <Form.Item name="ami_secret" label={<span style={{ color: '#94a3b8' }}><KeyOutlined style={{ marginRight: 4 }} />AMI Secret</span>}>
                        <Input.Password placeholder="Enter new AMI secret..." style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                    </Form.Item>
                    <Form.Item name="ssh_key_pem" label={<span style={{ color: '#94a3b8' }}><KeyOutlined style={{ marginRight: 4 }} />SSH Private Key</span>}>
                        <Input.TextArea rows={3} placeholder="Paste SSH key or use Upload below..." style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0', fontFamily: 'monospace', fontSize: 11 }} />
                    </Form.Item>
                    <Upload accept=".ppk,.pem,.key,.id_rsa" beforeUpload={(file: any) => { const reader = new FileReader(); reader.onload = (e) => { editForm.setFieldValue('ssh_key_pem', e.target?.result as string); message.success(`Loaded ${file.name}`); }; reader.readAsText(file); return false; }} showUploadList={false} maxCount={1}>
                        <Button icon={<UploadOutlined />} size="small" style={{ marginTop: -8, marginBottom: 8 }}>Upload .ppk / .pem Key File</Button>
                    </Upload>
                    <Form.Item name="ssh_password" label={<span style={{ color: '#94a3b8' }}><KeyOutlined style={{ marginRight: 4 }} />SSH Password</span>}>
                        <Input.Password placeholder="Enter new SSH password..." style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }} />
                    </Form.Item>

                    {editTarget && (
                        <div style={{ padding: '10px 14px', borderRadius: 8, background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.25)', marginTop: 12 }}>
                            <div style={{ color: '#94a3b8', fontSize: 11 }}>Current vault aliases:</div>
                            <div style={{ color: '#60a5fa', fontSize: 11, fontFamily: 'monospace', marginTop: 4 }}>
                                AMI: {editTarget.ami_secret_alias || '—'}<br />
                                SSH Key: {editTarget.ssh_key_alias || '—'}<br />
                                SSH Pass: {editTarget.ssh_password_alias || '—'}
                            </div>
                        </div>
                    )}
                </Form>
            </Modal>
        </div>
    );
}
