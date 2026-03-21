import { useState, useMemo } from 'react';
import {
    Table, Button, Space, Tag, Typography, Tooltip, Drawer, Modal, Form,
    Input, Select, InputNumber, Progress, Empty, Tabs, Badge, message, Popconfirm,
} from 'antd';
import {
    GlobalOutlined, PlusOutlined, SyncOutlined,
    FileTextOutlined, CheckCircleOutlined,
    CloseCircleOutlined, ClockCircleOutlined,
    ReloadOutlined, LoadingOutlined, SearchOutlined,
    ImportOutlined, DeleteOutlined, EditOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dnsClient } from '../api/dnsClient';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, cardStyle as centralCardStyle, pageContainer } from '../theme';

const { Title, Text } = Typography;

export default function IntegrationsDns() {
    const { mode } = useThemeStore();
    const MN = getTokens(mode);
    const cardStyle = (glow = MN.accent): React.CSSProperties => centralCardStyle(MN, glow);
    const qc = useQueryClient();
    const [selectedZone, setSelectedZone] = useState<any>(null);
    const [addZoneOpen, setAddZoneOpen] = useState(false);
    const [addRecordOpen, setAddRecordOpen] = useState(false);
    const [editingRecord, setEditingRecord] = useState<any>(null);
    const [recordSearch, setRecordSearch] = useState('');
    const [discoverOpen, setDiscoverOpen] = useState(false);
    const [discoverProvider, setDiscoverProvider] = useState('dnsmadeeasy');
    const [selectedImports, setSelectedImports] = useState<string[]>([]);
    const [zoneForm] = Form.useForm();
    const [recordForm] = Form.useForm();

    // ── Queries ──
    const { data: zones = [], isLoading: zonesLoading } = useQuery({
        queryKey: ['dns-zones'],
        queryFn: async () => {
            const r = await dnsClient.get('/dns/v1/zones');
            return r.data;
        },
    });

    const { data: jobs = [] } = useQuery({
        queryKey: ['dns-jobs'],
        queryFn: async () => {
            const r = await dnsClient.get('/dns/v1/jobs', { params: { limit: 50 } });
            return r.data;
        },
    });

    const { data: zoneRecords = [], isLoading: recordsLoading } = useQuery({
        queryKey: ['dns-records', selectedZone?.id],
        queryFn: async () => {
            if (!selectedZone) return [];
            const r = await dnsClient.get(`/dns/v1/zones/${selectedZone.id}/records`);
            return r.data;
        },
        enabled: !!selectedZone,
    });

    // ── Mutations ──
    const createZoneMut = useMutation({
        mutationFn: async (vals: any) => {
            const r = await dnsClient.post('/dns/v1/zones', vals);
            return r.data;
        },
        onSuccess: () => {
            message.success('Zone created');
            qc.invalidateQueries({ queryKey: ['dns-zones'] });
            setAddZoneOpen(false);
            zoneForm.resetFields();
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed to create zone'),
    });

    const upsertRecordMut = useMutation({
        mutationFn: async (vals: any) => {
            const r = await dnsClient.post('/dns/v1/records/upsert', {
                tenant_id: selectedZone.tenant_id,
                env: selectedZone.env,
                zone: selectedZone.zone_name,
                records: [vals],
            });
            return r.data;
        },
        onSuccess: () => {
            message.success('Record queued');
            qc.invalidateQueries({ queryKey: ['dns-records', selectedZone?.id] });
            qc.invalidateQueries({ queryKey: ['dns-jobs'] });
            setAddRecordOpen(false);
            recordForm.resetFields();
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Failed'),
    });

    const deleteRecordMut = useMutation({
        mutationFn: async (rec: any) => {
            const r = await dnsClient.post('/dns/v1/records/delete', {
                tenant_id: selectedZone.tenant_id,
                env: selectedZone.env,
                zone: selectedZone.zone_name,
                records: [{ name: rec.name, record_type: rec.record_type }],
            });
            return r.data;
        },
        onSuccess: () => {
            message.success('Delete job queued');
            qc.invalidateQueries({ queryKey: ['dns-records', selectedZone?.id] });
            qc.invalidateQueries({ queryKey: ['dns-jobs'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Delete failed'),
    });

    const syncMut = useMutation({
        mutationFn: async (zone: any) => {
            const r = await dnsClient.post('/dns/v1/sync', {
                tenant_id: zone.tenant_id, env: zone.env, zone: zone.zone_name,
            });
            return r.data;
        },
        onSuccess: (data) => {
            if (data.drift_count === 0) message.success('No drift detected');
            else message.warning(`${data.drift_count} drift(s) found`);
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Sync failed'),
    });

    const unregisterMut = useMutation({
        mutationFn: async (zone: any) => {
            const r = await dnsClient.delete(`/dns/v1/zones/${zone.id}`);
            return r.data;
        },
        onSuccess: (data) => {
            message.success(`${data.zone_name} removed from Nexus (provider untouched)`);
            qc.invalidateQueries({ queryKey: ['dns-zones'] });
            qc.invalidateQueries({ queryKey: ['dns-jobs'] });
            setSelectedZone(null);
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Unregister failed'),
    });

    // ── Discover ──
    const { data: discoveredZones = [], isLoading: discoverLoading, refetch: refetchDiscover } = useQuery({
        queryKey: ['dns-discover', discoverProvider],
        queryFn: async () => {
            const r = await dnsClient.get('/dns/v1/zones/discover', {
                params: { provider: discoverProvider, tenant_id: 'nexus', env: 'prod' },
            });
            return r.data;
        },
        enabled: discoverOpen,
    });

    const importMut = useMutation({
        mutationFn: async (zone_names: string[]) => {
            const r = await dnsClient.post('/dns/v1/zones/import', {
                provider: discoverProvider, tenant_id: 'nexus', env: 'prod', zone_names,
            });
            return r.data;
        },
        onSuccess: (data) => {
            message.success(`Imported ${data.length} zone(s)`);
            qc.invalidateQueries({ queryKey: ['dns-zones'] });
            refetchDiscover();
            setSelectedImports([]);
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Import failed'),
    });

    // ── Derived stats ──
    const stats = useMemo(() => {
        const active = zones.filter((z: any) => z.is_active).length;
        const providers: Record<string, number> = {};
        zones.forEach((z: any) => { providers[z.provider] = (providers[z.provider] || 0) + 1; });
        const jobPending = jobs.filter((j: any) => j.status === 'pending').length;
        const jobRunning = jobs.filter((j: any) => j.status === 'running').length;
        const jobOk = jobs.filter((j: any) => j.status === 'succeeded').length;
        const jobFail = jobs.filter((j: any) => j.status === 'failed').length;
        return { active, total: zones.length, providers, jobPending, jobRunning, jobOk, jobFail };
    }, [zones, jobs]);

    // ── Zone table columns ──
    const zoneCols = [
        {
            title: 'ZONE', dataIndex: 'zone_name', key: 'zone_name',
            render: (t: string) => <Text style={{ color: '#fff', fontWeight: 600 }}>{t}</Text>,
        },
        {
            title: 'PROVIDER', dataIndex: 'provider', key: 'provider',
            render: (t: string) => (
                <Tag style={{
                    background: t === 'cloudflare' ? 'rgba(251,146,60,0.15)' : 'rgba(167,139,250,0.15)',
                    color: t === 'cloudflare' ? MN.orange : MN.purple,
                    border: `1px solid ${t === 'cloudflare' ? 'rgba(251,146,60,0.3)' : 'rgba(167,139,250,0.3)'}`,
                }}>
                    {t === 'cloudflare' ? '☁ Cloudflare' : t}
                </Tag>
            ),
        },
        {
            title: 'ENV', dataIndex: 'env', key: 'env',
            render: (t: string) => (
                <Tag style={{
                    background: t === 'prod' ? 'rgba(239,68,68,0.15)' : t === 'stage' ? 'rgba(251,146,60,0.15)' : 'rgba(34,197,94,0.15)',
                    color: t === 'prod' ? MN.red : t === 'stage' ? MN.orange : MN.green,
                    border: `1px solid ${t === 'prod' ? 'rgba(239,68,68,0.3)' : t === 'stage' ? 'rgba(251,146,60,0.3)' : 'rgba(34,197,94,0.3)'}`,
                }}>
                    {t.toUpperCase()}
                </Tag>
            ),
        },
        {
            title: 'TENANT', dataIndex: 'tenant_id', key: 'tenant_id',
            render: (t: string) => <Text style={{ color: MN.muted, fontSize: 12 }}>{t}</Text>,
        },
        {
            title: 'STATUS', dataIndex: 'is_active', key: 'is_active',
            render: (v: boolean) => (
                <Tag style={{
                    background: v ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                    color: v ? MN.green : MN.red,
                    border: `1px solid ${v ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                }}>
                    {v ? 'Active' : 'Inactive'}
                </Tag>
            ),
        },
        {
            title: 'CREATED', dataIndex: 'created_at', key: 'created_at',
            render: (t: string) => <Text style={{ color: MN.muted, fontSize: 12 }}>{t ? new Date(t).toLocaleDateString() : '—'}</Text>,
        },
        {
            title: 'ACTIONS', key: 'actions',
            render: (_: any, rec: any) => (
                <Space size={4}>
                    <Tooltip title="View Records">
                        <Button size="small" onClick={() => setSelectedZone(rec)}
                            style={{ background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.3)', color: MN.accent }}>
                            <FileTextOutlined />
                        </Button>
                    </Tooltip>
                    <Tooltip title="Sync / Drift Check">
                        <Button size="small" onClick={() => syncMut.mutate(rec)}
                            loading={syncMut.isPending}
                            style={{ background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.3)', color: MN.green }}>
                            <SyncOutlined />
                        </Button>
                    </Tooltip>
                    <Tooltip title="Unregister from Nexus (does NOT delete from provider)">
                        <Button size="small" danger
                            onClick={() => {
                                Modal.confirm({
                                    title: <span style={{ color: MN.text }}>Unregister Zone</span>,
                                    icon: <DeleteOutlined style={{ color: MN.red }} />,
                                    content: (
                                        <div style={{ color: MN.muted }}>
                                            <p>Remove <strong style={{ color: '#fff' }}>{rec.zone_name}</strong> and all its records from Nexus?</p>
                                            <div style={{
                                                background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)',
                                                borderRadius: 8, padding: '10px 14px', marginTop: 8,
                                            }}>
                                                <span style={{ color: MN.green, fontWeight: 600 }}>✓ Safe:</span>
                                                <span style={{ color: MN.muted, marginLeft: 6 }}>
                                                    This will <strong style={{ color: '#fff' }}>NOT</strong> delete anything from DNS Made Easy or Cloudflare.
                                                    Records at the provider remain untouched.
                                                </span>
                                            </div>
                                        </div>
                                    ),
                                    okText: 'Unregister from Nexus',
                                    okButtonProps: { danger: true },
                                    cancelText: 'Cancel',
                                    styles: {
                                        header: { background: MN.bg },
                                        body: { background: MN.bg },
                                        mask: { background: 'rgba(0,0,0,0.6)' },
                                    },
                                    onOk: () => unregisterMut.mutate(rec),
                                });
                            }}
                            style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: MN.red }}>
                            <DeleteOutlined />
                        </Button>
                    </Tooltip>
                </Space>
            ),
        },
    ];

    // ── Filtered records ──
    const filteredRecords = useMemo(() => {
        if (!recordSearch.trim()) return zoneRecords;
        const q = recordSearch.toLowerCase();
        return zoneRecords.filter((r: any) =>
            r.name?.toLowerCase().includes(q) ||
            r.value?.toLowerCase().includes(q) ||
            r.record_type?.toLowerCase().includes(q)
        );
    }, [zoneRecords, recordSearch]);

    // ── Record table columns ──
    const recCols = [
        {
            title: 'TYPE', dataIndex: 'record_type', key: 'record_type', width: 80,
            render: (t: string) => (
                <Tag style={{
                    background: 'rgba(59,130,246,0.15)', color: MN.accent,
                    border: '1px solid rgba(59,130,246,0.3)', fontFamily: 'monospace',
                }}>
                    {t}
                </Tag>
            ),
        },
        {
            title: 'NAME', dataIndex: 'name', key: 'name',
            render: (t: string) => <Text style={{ color: '#fff', fontWeight: 600, fontFamily: 'monospace' }}>{t}</Text>,
        },
        {
            title: 'VALUE', dataIndex: 'value', key: 'value', ellipsis: true,
            render: (t: string) => <Text style={{ color: MN.muted, fontFamily: 'monospace', fontSize: 12 }}>{t}</Text>,
        },
        {
            title: 'TTL', dataIndex: 'ttl', key: 'ttl', width: 80,
            render: (t: number) => <Text style={{ color: MN.muted }}>{t}s</Text>,
        },
        {
            title: 'PRIORITY', dataIndex: 'priority', key: 'priority', width: 80,
            render: (t: number | null) => <Text style={{ color: MN.muted }}>{t ?? '—'}</Text>,
        },
        {
            title: 'SYNCED', dataIndex: 'last_synced_at', key: 'last_synced_at',
            render: (t: string | null) => t
                ? <Text style={{ color: MN.green, fontSize: 12 }}>{new Date(t).toLocaleString()}</Text>
                : <Text style={{ color: MN.muted, fontStyle: 'italic' }}>Never</Text>,
        },
        {
            title: 'ACTIONS', key: 'actions', width: 100,
            render: (_: any, rec: any) => (
                <Space size={4}>
                    <Tooltip title="Edit Record">
                        <Button size="small" onClick={() => {
                            setEditingRecord(rec);
                            recordForm.setFieldsValue({
                                record_type: rec.record_type,
                                name: rec.name,
                                value: rec.value,
                                ttl: rec.ttl,
                                priority: rec.priority,
                            });
                            setAddRecordOpen(true);
                        }}
                            style={{ background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.3)', color: MN.accent }}>
                            <EditOutlined />
                        </Button>
                    </Tooltip>
                    <Popconfirm
                        title={<span style={{ color: MN.text }}>Delete this record?</span>}
                        description={<span style={{ color: MN.muted }}>{rec.record_type} {rec.name} → {rec.value}</span>}
                        onConfirm={() => deleteRecordMut.mutate(rec)}
                        okText="Delete"
                        okButtonProps={{ danger: true }}
                        cancelText="Cancel"
                    >
                        <Tooltip title="Delete Record">
                            <Button size="small" danger
                                style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: MN.red }}>
                                <DeleteOutlined />
                            </Button>
                        </Tooltip>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    // ── Job status icon ──
    const jobIcon = (s: string) => {
        switch (s) {
            case 'succeeded': return <CheckCircleOutlined style={{ color: MN.green }} />;
            case 'failed': return <CloseCircleOutlined style={{ color: MN.red }} />;
            case 'running': return <LoadingOutlined style={{ color: MN.accent }} spin />;
            default: return <ClockCircleOutlined style={{ color: MN.orange }} />;
        }
    };

    return (
        <div style={pageContainer(MN)}>
            <style>{`
                .dns-table .ant-table { background: transparent !important; }
                .dns-table .ant-table-thead > tr > th { background: rgba(30,41,59,0.6) !important; color: ${MN.muted} !important; border-bottom: 1px solid ${MN.border} !important; font-size: 11px !important; letter-spacing: 0.5px; }
                .dns-table .ant-table-tbody > tr > td { border-bottom: 1px solid ${MN.border} !important; background: transparent !important; }
                .dns-table .ant-table-tbody > tr:hover > td { background: rgba(59,130,246,0.05) !important; }
                .dns-table .ant-table-cell { color: ${MN.text} !important; }
                .dns-table .ant-pagination .ant-pagination-item a { color: ${MN.muted} !important; }
                .dns-table .ant-pagination .ant-pagination-item-active { border-color: ${MN.accent} !important; }
                .dns-table .ant-pagination .ant-pagination-item-active a { color: ${MN.accent} !important; }
                .dns-table .ant-empty-description { color: ${MN.muted} !important; }
                .dns-table .ant-select-selector { background: ${MN.card} !important; border-color: ${MN.border} !important; color: ${MN.muted} !important; }
                .dns-table .ant-pagination-prev .ant-pagination-item-link,
                .dns-table .ant-pagination-next .ant-pagination-item-link { color: ${MN.muted} !important; }
                .ant-drawer .ant-drawer-close { color: ${MN.muted} !important; }
                .ant-drawer .ant-drawer-close:hover { color: ${MN.text} !important; }
            `}</style>

            {/* ═══ Header ═══ */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <Title level={2} style={{ margin: 0, color: MN.text }}>
                    <GlobalOutlined style={{ marginRight: 10, color: MN.accent }} />
                    DNS Administration
                </Title>
                <Space>
                    <Button icon={<ReloadOutlined />} onClick={() => { qc.invalidateQueries({ queryKey: ['dns-zones'] }); qc.invalidateQueries({ queryKey: ['dns-jobs'] }); }}
                        style={{ background: MN.card, borderColor: MN.border, color: MN.muted }}>
                        Refresh
                    </Button>
                    <Button icon={<SearchOutlined />} onClick={() => setDiscoverOpen(true)}
                        style={{ background: 'rgba(167,139,250,0.15)', borderColor: 'rgba(167,139,250,0.3)', color: MN.purple }}>
                        Discover Zones
                    </Button>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddZoneOpen(true)}>
                        Add Zone
                    </Button>
                </Space>
            </div>

            {/* ═══ Dashboard Panels ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
                {/* Zones Panel */}
                <div style={cardStyle()}>
                    <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                        <GlobalOutlined style={{ marginRight: 6 }} /> ZONES
                    </Text>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                        <div style={{ position: 'relative', width: 80, height: 80 }}>
                            <Progress type="circle" percent={stats.total > 0 ? Math.round((stats.active / stats.total) * 100) : 0}
                                size={80} strokeColor={MN.green} trailColor="rgba(30,41,59,0.8)"
                                format={() => <span style={{ color: '#fff', fontSize: 22, fontWeight: 700 }}>{stats.total}</span>} />
                        </div>
                        <div>
                            <div style={{ color: MN.green, fontSize: 14 }}>✓ {stats.active} Active</div>
                            <div style={{ color: MN.muted, fontSize: 12, marginTop: 4 }}>
                                {Object.entries(stats.providers).map(([p, c]) => (
                                    <div key={p}>{p}: {c as number}</div>
                                ))}
                                {Object.keys(stats.providers).length === 0 && <div>No zones</div>}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Records Panel */}
                <div style={cardStyle()}>
                    <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                        <FileTextOutlined style={{ marginRight: 6 }} /> RECORDS
                    </Text>
                    <div style={{ textAlign: 'center', paddingTop: 8 }}>
                        <div style={{ fontSize: 36, fontWeight: 700, color: '#fff' }}>
                            {zones.reduce((s: number, z: any) => s + (z.record_count || 0), 0) || '—'}
                        </div>
                        <Text style={{ color: MN.muted, fontSize: 12 }}>Total Records Managed</Text>
                    </div>
                </div>

                {/* Jobs Panel */}
                <div style={cardStyle()}>
                    <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                        <SyncOutlined style={{ marginRight: 6 }} /> RECENT JOBS
                    </Text>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <ClockCircleOutlined style={{ color: MN.orange }} />
                            <Text style={{ color: MN.text }}>{stats.jobPending}</Text>
                            <Text style={{ color: MN.muted, fontSize: 11 }}>Pending</Text>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <LoadingOutlined style={{ color: MN.accent }} />
                            <Text style={{ color: MN.text }}>{stats.jobRunning}</Text>
                            <Text style={{ color: MN.muted, fontSize: 11 }}>Running</Text>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <CheckCircleOutlined style={{ color: MN.green }} />
                            <Text style={{ color: MN.text }}>{stats.jobOk}</Text>
                            <Text style={{ color: MN.muted, fontSize: 11 }}>OK</Text>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <CloseCircleOutlined style={{ color: MN.red }} />
                            <Text style={{ color: MN.text }}>{stats.jobFail}</Text>
                            <Text style={{ color: MN.muted, fontSize: 11 }}>Failed</Text>
                        </div>
                    </div>
                </div>

                {/* Health Panel */}
                <div style={cardStyle()}>
                    <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                        <CheckCircleOutlined style={{ marginRight: 6 }} /> HEALTH
                    </Text>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
                        {[
                            { label: 'DNS Agent', ok: true },
                            { label: 'Job Queue', ok: stats.jobFail === 0 },
                            { label: 'Drift', ok: true },
                        ].map(svc => (
                            <div key={svc.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <span style={{
                                        width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
                                        background: svc.ok ? MN.green : MN.red,
                                        boxShadow: svc.ok ? `0 0 6px ${MN.green}` : `0 0 6px ${MN.red}`,
                                    }} />
                                    <Text style={{ color: MN.text, fontSize: 13 }}>{svc.label}</Text>
                                </div>
                                <Tag style={{
                                    margin: 0, fontSize: 11,
                                    background: svc.ok ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                                    color: svc.ok ? MN.green : MN.red,
                                    border: `1px solid ${svc.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                                    borderRadius: 4,
                                }}>
                                    {svc.ok ? 'Healthy' : 'Degraded'}
                                </Tag>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* ═══ Tabs: Zones + Jobs ═══ */}
            <Tabs
                defaultActiveKey="zones"
                style={{ marginBottom: 24 }}
                items={[
                    {
                        key: 'zones',
                        label: <span style={{ color: MN.text }}><GlobalOutlined style={{ marginRight: 6 }} />Zones ({zones.length})</span>,
                        children: (
                            <div className="dns-table" style={{ ...cardStyle(), padding: 0 }}>
                                <Table
                                    columns={zoneCols}
                                    dataSource={zones}
                                    rowKey="id"
                                    loading={zonesLoading}
                                    pagination={{ pageSize: 15, showTotal: (t) => <span style={{ color: MN.muted }}>{t} zones</span> }}
                                    locale={{ emptyText: <Empty description={<span style={{ color: MN.muted }}>No DNS zones registered</span>} /> }}
                                />
                            </div>
                        ),
                    },
                    {
                        key: 'jobs',
                        label: (
                            <span style={{ color: MN.text }}>
                                <SyncOutlined style={{ marginRight: 6 }} />
                                Jobs
                                {stats.jobPending + stats.jobRunning > 0 && (
                                    <Badge count={stats.jobPending + stats.jobRunning} size="small" style={{ marginLeft: 8 }} />
                                )}
                            </span>
                        ),
                        children: (
                            <div className="dns-table" style={{ ...cardStyle(), padding: 0 }}>
                                <Table
                                    columns={[
                                        {
                                            title: 'STATUS', dataIndex: 'status', key: 'status', width: 100,
                                            render: (s: string) => <Space>{jobIcon(s)}<Text style={{ color: MN.text }}>{s}</Text></Space>,
                                        },
                                        {
                                            title: 'ZONE', dataIndex: 'zone_name', key: 'zone_name',
                                            render: (t: string) => <Text style={{ color: '#fff', fontWeight: 600 }}>{t}</Text>,
                                        },
                                        {
                                            title: 'OPERATION', dataIndex: 'operation', key: 'operation',
                                            render: (t: string) => <Tag style={{ background: 'rgba(59,130,246,0.15)', color: MN.accent, border: '1px solid rgba(59,130,246,0.3)' }}>{t}</Tag>,
                                        },
                                        {
                                            title: 'ATTEMPTS', dataIndex: 'attempts', key: 'attempts', width: 90,
                                            render: (t: number) => <Text style={{ color: MN.muted }}>{t}</Text>,
                                        },
                                        {
                                            title: 'ERROR', dataIndex: 'last_error', key: 'last_error', ellipsis: true,
                                            render: (t: string | null) => t ? <Text style={{ color: MN.red, fontSize: 12 }}>{t}</Text> : <Text style={{ color: MN.muted }}>—</Text>,
                                        },
                                        {
                                            title: 'CREATED BY', dataIndex: 'created_by_service_id', key: 'created_by',
                                            render: (t: string) => <Text style={{ color: MN.muted, fontSize: 12 }}>{t}</Text>,
                                        },
                                        {
                                            title: 'CREATED', dataIndex: 'created_at', key: 'created_at',
                                            render: (t: string) => <Text style={{ color: MN.muted, fontSize: 12 }}>{new Date(t).toLocaleString()}</Text>,
                                        },
                                    ]}
                                    dataSource={jobs}
                                    rowKey="id"
                                    pagination={{ pageSize: 15, showTotal: (t) => <span style={{ color: MN.muted }}>{t} jobs</span> }}
                                    locale={{ emptyText: <Empty description={<span style={{ color: MN.muted }}>No jobs</span>} /> }}
                                />
                            </div>
                        ),
                    },
                ]}
                className="dns-tabs"
            />

            {/* ═══ Zone Records Drawer ═══ */}
            <Drawer
                title={
                    <span style={{ color: MN.text }}>
                        <GlobalOutlined style={{ marginRight: 8, color: MN.accent }} />
                        {selectedZone?.zone_name}
                        {selectedZone && (
                            <Tag style={{ marginLeft: 12, background: 'rgba(251,146,60,0.15)', color: MN.orange, border: '1px solid rgba(251,146,60,0.3)' }}>
                                {selectedZone.provider}
                            </Tag>
                        )}
                    </span>
                }
                open={!!selectedZone}
                onClose={() => setSelectedZone(null)}
                width={Math.min(1100, window.innerWidth - 40)}
                styles={{
                    header: { background: MN.bg, borderBottom: `1px solid ${MN.border}` },
                    body: { background: MN.bg, padding: 20 },
                }}
                extra={
                    <Space>
                        <Input
                            prefix={<SearchOutlined style={{ color: MN.muted }} />}
                            placeholder="Search records..."
                            value={recordSearch}
                            onChange={(e) => setRecordSearch(e.target.value)}
                            allowClear
                            style={{ width: 220, background: MN.card, borderColor: MN.border, color: MN.text }}
                            size="small"
                        />
                        <Button size="small" icon={<PlusOutlined />} type="primary" onClick={() => { setEditingRecord(null); recordForm.resetFields(); setAddRecordOpen(true); }}>
                            Add Record
                        </Button>
                        <Button size="small" icon={<SyncOutlined />}
                            onClick={() => selectedZone && syncMut.mutate(selectedZone)}
                            loading={syncMut.isPending}
                            style={{ background: MN.card, borderColor: MN.border, color: MN.muted }}>
                            Sync
                        </Button>
                    </Space>
                }
            >
                {selectedZone && (
                    <div>
                        {/* Mini info bar */}
                        <div style={{ display: 'flex', gap: 24, marginBottom: 20, flexWrap: 'wrap' }}>
                            {[
                                { label: 'Tenant', value: selectedZone.tenant_id },
                                { label: 'Env', value: selectedZone.env?.toUpperCase() },
                                { label: 'Records', value: zoneRecords.length },
                                { label: 'Provider Zone ID', value: selectedZone.provider_zone_id || '—' },
                            ].map(item => (
                                <div key={item.label} style={{ background: MN.card, border: `1px solid ${MN.border}`, borderRadius: 8, padding: '8px 16px' }}>
                                    <Text style={{ color: MN.muted, fontSize: 10, letterSpacing: 0.5, display: 'block' }}>{item.label}</Text>
                                    <Text style={{ color: MN.text, fontWeight: 600 }}>{item.value}</Text>
                                </div>
                            ))}
                        </div>

                        {/* Records table */}
                        <div className="dns-table">
                            <Table
                                columns={recCols}
                                dataSource={filteredRecords}
                                rowKey="id"
                                loading={recordsLoading}
                                pagination={{ pageSize: 20, showTotal: (t) => <span style={{ color: MN.muted }}>{t} records{recordSearch && ` (filtered)`}</span> }}
                                locale={{ emptyText: <Empty description={<span style={{ color: MN.muted }}>{recordSearch ? 'No matching records' : 'No records for this zone'}</span>} /> }}
                            />
                        </div>
                    </div>
                )}
            </Drawer>

            {/* ═══ Add Zone Modal ═══ */}
            <Modal
                title={<span style={{ color: MN.text }}><GlobalOutlined style={{ marginRight: 8, color: MN.accent }} />Add DNS Zone</span>}
                open={addZoneOpen}
                onCancel={() => setAddZoneOpen(false)}
                onOk={() => zoneForm.submit()}
                confirmLoading={createZoneMut.isPending}
                styles={{ header: { background: MN.bg, borderBottom: `1px solid ${MN.border}` }, body: { background: MN.bg }, footer: { background: MN.bg, borderTop: `1px solid ${MN.border}` } }}
            >
                <Form form={zoneForm} layout="vertical" onFinish={(vals) => createZoneMut.mutate(vals)}
                    initialValues={{ env: 'prod', provider: 'cloudflare', tenant_id: 'nexus' }}>
                    <Form.Item name="zone_name" label={<span style={{ color: MN.muted }}>Zone Name</span>} rules={[{ required: true, message: 'Required' }]}>
                        <Input placeholder="example.com" style={{ background: MN.card, borderColor: MN.border, color: MN.text }} />
                    </Form.Item>
                    <Form.Item name="tenant_id" label={<span style={{ color: MN.muted }}>Tenant ID</span>} rules={[{ required: true }]}>
                        <Input placeholder="gsm" style={{ background: MN.card, borderColor: MN.border, color: MN.text }} />
                    </Form.Item>
                    <Form.Item name="env" label={<span style={{ color: MN.muted }}>Environment</span>}>
                        <Select
                            options={[{ value: 'prod', label: 'Production' }, { value: 'stage', label: 'Staging' }, { value: 'dev', label: 'Development' }]}
                            style={{ width: '100%' }}
                        />
                    </Form.Item>
                    <Form.Item name="provider" label={<span style={{ color: MN.muted }}>DNS Provider</span>}>
                        <Select
                            options={[{ value: 'cloudflare', label: '☁ Cloudflare' }, { value: 'dnsmadeeasy', label: 'DNS Made Easy' }]}
                            style={{ width: '100%' }}
                        />
                    </Form.Item>
                </Form>
            </Modal>

            {/* ═══ Add/Edit Record Modal ═══ */}
            <Modal
                title={<span style={{ color: MN.text }}><FileTextOutlined style={{ marginRight: 8, color: MN.accent }} />{editingRecord ? 'Edit DNS Record' : 'Add DNS Record'}</span>}
                open={addRecordOpen}
                onCancel={() => { setAddRecordOpen(false); setEditingRecord(null); recordForm.resetFields(); }}
                onOk={() => recordForm.submit()}
                confirmLoading={upsertRecordMut.isPending}
                styles={{ header: { background: MN.bg, borderBottom: `1px solid ${MN.border}` }, body: { background: MN.bg }, footer: { background: MN.bg, borderTop: `1px solid ${MN.border}` } }}
            >
                <Form form={recordForm} layout="vertical" onFinish={(vals) => upsertRecordMut.mutate(vals)}
                    initialValues={{ record_type: 'A', ttl: 86400 }}>
                    <Form.Item name="record_type" label={<span style={{ color: MN.muted }}>Record Type</span>} rules={[{ required: true }]}>
                        <Select options={['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'SRV', 'PTR', 'NS', 'CAA'].map(t => ({ value: t, label: t }))} />
                    </Form.Item>
                    <Form.Item name="name" label={<span style={{ color: MN.muted }}>Name</span>} rules={[{ required: true }]}>
                        <Input placeholder="@ or subdomain" style={{ background: MN.card, borderColor: MN.border, color: MN.text }} />
                    </Form.Item>
                    <Form.Item name="value" label={<span style={{ color: MN.muted }}>Value</span>} rules={[{ required: true }]}>
                        <Input placeholder="IP address or hostname" style={{ background: MN.card, borderColor: MN.border, color: MN.text }} />
                    </Form.Item>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                        <Form.Item name="ttl" label={<span style={{ color: MN.muted }}>TTL</span>}>
                            <Select
                                options={[
                                    { value: 300, label: '5 minutes' },
                                    { value: 600, label: '10 minutes' },
                                    { value: 3600, label: '1 hour' },
                                    { value: 21600, label: '6 hours' },
                                    { value: 86400, label: '1 day' },
                                    { value: 259200, label: '3 days' },
                                ]}
                                style={{ width: '100%' }}
                            />
                        </Form.Item>
                        <Form.Item name="priority" label={<span style={{ color: MN.muted }}>Priority (MX/SRV)</span>}>
                            <InputNumber min={0} max={65535} style={{ width: '100%', background: MN.card, borderColor: MN.border, color: MN.text }} />
                        </Form.Item>
                    </div>
                </Form>
            </Modal>

            {/* ═══ Discover & Import Drawer ═══ */}
            <Drawer
                title={
                    <span style={{ color: MN.text }}>
                        <SearchOutlined style={{ marginRight: 8, color: MN.purple }} />
                        Discover Provider Zones
                    </span>
                }
                open={discoverOpen}
                onClose={() => { setDiscoverOpen(false); setSelectedImports([]); }}
                width={Math.min(800, window.innerWidth - 40)}
                styles={{
                    header: { background: MN.bg, borderBottom: `1px solid ${MN.border}` },
                    body: { background: MN.bg, padding: 20 },
                }}
                extra={
                    <Space>
                        <Select value={discoverProvider} onChange={(v) => { setDiscoverProvider(v); setSelectedImports([]); }}
                            style={{ width: 180 }}
                            options={[
                                { value: 'dnsmadeeasy', label: '🔵 DNS Made Easy' },
                                { value: 'cloudflare', label: '☁ Cloudflare' },
                            ]}
                        />
                        <Button icon={<ImportOutlined />} type="primary"
                            disabled={selectedImports.length === 0}
                            loading={importMut.isPending}
                            onClick={() => importMut.mutate(selectedImports)}>
                            Import Selected ({selectedImports.length})
                        </Button>
                    </Space>
                }
            >
                <div style={{ marginBottom: 12 }}>
                    <Text style={{ color: MN.muted, fontSize: 12 }}>
                        Zones are fetched live from {discoverProvider === 'dnsmadeeasy' ? 'DNS Made Easy' : 'Cloudflare'} using credentials from the Secrets Vault.
                        Select unregistered zones and click "Import" to add them to Nexus.
                    </Text>
                </div>
                <div className="dns-table">
                    <Table
                        columns={[
                            {
                                title: '', key: 'select', width: 40,
                                render: (_: any, rec: any) => rec.registered
                                    ? <CheckCircleOutlined style={{ color: MN.green }} />
                                    : <input type="checkbox"
                                        checked={selectedImports.includes(rec.zone_name)}
                                        onChange={(e) => {
                                            if (e.target.checked) setSelectedImports(prev => [...prev, rec.zone_name]);
                                            else setSelectedImports(prev => prev.filter(n => n !== rec.zone_name));
                                        }}
                                        style={{ accentColor: MN.accent, width: 16, height: 16, cursor: 'pointer' }}
                                    />,
                            },
                            {
                                title: 'ZONE NAME', dataIndex: 'zone_name', key: 'zone_name',
                                render: (t: string) => <Text style={{ color: '#fff', fontWeight: 600 }}>{t}</Text>,
                            },
                            {
                                title: 'PROVIDER ZONE ID', dataIndex: 'provider_zone_id', key: 'provider_zone_id',
                                render: (t: string) => <Text style={{ color: MN.muted, fontFamily: 'monospace', fontSize: 12 }}>{t}</Text>,
                            },
                            {
                                title: 'STATUS', key: 'registered',
                                render: (_: any, rec: any) => rec.registered
                                    ? <Tag style={{ background: 'rgba(34,197,94,0.15)', color: MN.green, border: '1px solid rgba(34,197,94,0.3)' }}>Imported</Tag>
                                    : <Tag style={{ background: 'rgba(251,146,60,0.15)', color: MN.orange, border: '1px solid rgba(251,146,60,0.3)' }}>Available</Tag>,
                            },
                        ]}
                        dataSource={discoveredZones}
                        rowKey="zone_name"
                        loading={discoverLoading}
                        pagination={{ pageSize: 20, showTotal: (t) => <span style={{ color: MN.muted }}>{t} zones found at provider</span> }}
                        locale={{ emptyText: <Empty description={<span style={{ color: MN.muted }}>No zones found — check provider credentials in Secrets</span>} /> }}
                    />
                </div>
            </Drawer>
        </div>
    );
}
