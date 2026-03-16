import { useState, useMemo } from 'react';
import {
    Table, Button, Space, Tag, Typography, Tooltip, Drawer, Modal,
    Progress, Empty, Tabs, Badge, message, Input,
} from 'antd';
import {
    CloudServerOutlined, SyncOutlined,
    CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
    ReloadOutlined, LoadingOutlined, PoweroffOutlined,
    PlayCircleOutlined, PauseCircleOutlined, DesktopOutlined,
    InfoCircleOutlined, DeleteOutlined, ExclamationCircleOutlined,
    SearchOutlined, ThunderboltOutlined, HddOutlined, LockOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { serverClient } from '../api/serverClient';
import { apiClient } from '../api/client';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, cardStyle as centralCardStyle, pageContainer } from '../theme';

const { Title, Text } = Typography;

export default function InfrastructureServers() {
    const { mode } = useThemeStore();
    const MN = getTokens(mode);
    const cardStyle = (glow = MN.accent): React.CSSProperties => centralCardStyle(MN, glow);
    const qc = useQueryClient();
    const [selectedServer, setSelectedServer] = useState<any>(null);
    const [searchText, setSearchText] = useState('');
    const [selectedHostId, setSelectedHostId] = useState<string | null>(null);
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
    const [deletePassword, setDeletePassword] = useState('');
    const [deleteVerifying, setDeleteVerifying] = useState(false);
    const [deleteError, setDeleteError] = useState('');

    // ── Queries ──
    const { data: servers = [], isLoading: serversLoading } = useQuery({
        queryKey: ['servers'],
        queryFn: async () => {
            const r = await serverClient.get('/servers/v1/servers');
            return r.data;
        },
    });

    const { data: hosts = [] } = useQuery({
        queryKey: ['server-hosts'],
        queryFn: async () => {
            const r = await serverClient.get('/servers/v1/hosts');
            return r.data;
        },
    });

    const { data: jobs = [] } = useQuery({
        queryKey: ['server-jobs'],
        queryFn: async () => {
            const r = await serverClient.get('/servers/v1/jobs');
            return r.data;
        },
        refetchInterval: 10000,
    });

    // ── Host resources (Proxmox only) ──
    const selectedHost = hosts.find((h: any) => h.id === selectedHostId);
    const isProxmoxHost = selectedHost?.provider === 'proxmox';
    const { data: hostResources } = useQuery({
        queryKey: ['host-resources', selectedHostId],
        queryFn: async () => {
            const r = await serverClient.get(`/servers/v1/hosts/${selectedHostId}/resources`);
            return r.data;
        },
        enabled: !!selectedHostId && isProxmoxHost,
        refetchInterval: 30000,
    });

    // ── Per-server live resources ──
    const { data: serverResources, isLoading: serverResourcesLoading } = useQuery({
        queryKey: ['server-resources', selectedServer?.id],
        queryFn: async () => {
            const r = await serverClient.get(`/servers/v1/servers/${selectedServer.id}/resources`);
            return r.data;
        },
        enabled: !!selectedServer?.id && selectedServer?.power_status === 'running',
        refetchInterval: 15000,
    });

    // ── MeshCentral device enrichment ──
    const { data: meshDevice } = useQuery({
        queryKey: ['meshcentral-device', selectedServer?.label, selectedServer?.ip_v4],
        queryFn: async () => {
            const params = selectedServer.ip_v4 ? `?ip=${selectedServer.ip_v4}` : '';
            const r = await serverClient.get(`/servers/v1/meshcentral/devices/${encodeURIComponent(selectedServer.label)}${params}`);
            return r.data;
        },
        enabled: !!selectedServer?.label,
        retry: false,
        staleTime: 120000,
    });

    // ── Mutations ──
    const syncMut = useMutation({
        mutationFn: async (hostId?: string) => {
            const params = hostId ? `?host_id=${hostId}` : '';
            const r = await serverClient.post(`/servers/v1/servers/sync${params}`);
            return r.data;
        },
        onSuccess: () => {
            message.success('Sync job queued — inventory will update shortly');
            qc.invalidateQueries({ queryKey: ['server-jobs'] });
            setTimeout(() => qc.invalidateQueries({ queryKey: ['servers'] }), 3000);
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Sync failed'),
    });

    const powerMut = useMutation({
        mutationFn: async ({ id, action }: { id: string; action: string }) => {
            const r = await serverClient.post(`/servers/v1/servers/${id}/${action}`);
            return r.data;
        },
        onSuccess: (_data, vars) => {
            message.success(`${vars.action} queued`);
            qc.invalidateQueries({ queryKey: ['server-jobs'] });
            setTimeout(() => qc.invalidateQueries({ queryKey: ['servers'] }), 3000);
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Action failed'),
    });

    const consoleMut = useMutation({
        mutationFn: async (id: string) => {
            const r = await serverClient.get(`/servers/v1/servers/${id}/console`);
            return r.data;
        },
        onSuccess: (data) => {
            if (data.url) {
                window.open(data.url, '_blank');
                const hint = data.type === 'proxmox_ui' ? ' (log into Proxmox if prompted)' :
                             data.type === 'vultr_portal' ? ' (log into Vultr if prompted)' : '';
                message.success(`Console opened in new tab${hint}`);
            } else {
                message.info('No console URL available from provider');
            }
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Console unavailable'),
    });

    const deleteMut = useMutation({
        mutationFn: async (id: string) => {
            const r = await serverClient.delete(`/servers/v1/servers/${id}`);
            return r.data;
        },
        onSuccess: () => {
            message.success('Server delete job queued — it will be destroyed shortly');
            setSelectedServer(null);
            setDeleteModalOpen(false);
            setDeletePassword('');
            setDeleteError('');
            qc.invalidateQueries({ queryKey: ['servers'] });
            qc.invalidateQueries({ queryKey: ['server-jobs'] });
        },
        onError: (e: any) => message.error(e?.response?.data?.detail || 'Delete failed'),
    });

    const handleDeleteConfirm = async () => {
        if (!selectedServer || !deletePassword) return;
        setDeleteVerifying(true);
        setDeleteError('');
        try {
            await apiClient.post('/auth/verify-password', { password: deletePassword });
            deleteMut.mutate(selectedServer.id);
        } catch (e: any) {
            setDeleteError(e?.response?.data?.detail || 'Invalid password');
        } finally {
            setDeleteVerifying(false);
        }
    };

    // ── Host-filtered base set ──
    const hostFilteredServers = useMemo(() => {
        if (!selectedHostId) return servers;
        return servers.filter((s: any) => s.host_id === selectedHostId);
    }, [servers, selectedHostId]);

    // ── Selected host label ──
    const selectedHostLabel = useMemo(() => {
        if (!selectedHostId) return null;
        const h = hosts.find((h: any) => h.id === selectedHostId);
        return h?.label || null;
    }, [selectedHostId, hosts]);

    // ── Derived stats (from host-filtered set) ──
    const stats = useMemo(() => {
        const src = hostFilteredServers;
        const running = src.filter((s: any) => s.power_status === 'running').length;
        const stopped = src.filter((s: any) => s.power_status === 'stopped').length;
        const other = src.length - running - stopped;
        const totalVcpu = src.reduce((s: number, sv: any) => s + (sv.vcpu_count || 0), 0);
        const totalRam = src.reduce((s: number, sv: any) => s + (sv.ram_mb || 0), 0);
        const totalDisk = src.reduce((s: number, sv: any) => s + (sv.disk_gb || 0), 0);
        // Provider breakdown (only meaningful when viewing all)
        const byProvider: Record<string, number> = {};
        servers.forEach((s: any) => {
            const prov = s.provider || 'unknown';
            byProvider[prov] = (byProvider[prov] || 0) + 1;
        });
        const jobPending = jobs.filter((j: any) => j.status === 'pending').length;
        const jobRunning = jobs.filter((j: any) => j.status === 'running').length;
        const jobOk = jobs.filter((j: any) => j.status === 'succeeded').length;
        const jobFail = jobs.filter((j: any) => j.status === 'failed').length;
        return { running, stopped, other, total: src.length, byProvider, totalVcpu, totalRam: Math.round(totalRam / 1024), totalDisk, jobPending, jobRunning, jobOk, jobFail };
    }, [hostFilteredServers, servers, jobs]);

    // ── Filtered servers (host + search) ──
    const filteredServers = useMemo(() => {
        if (!searchText) return hostFilteredServers;
        const q = searchText.toLowerCase();
        return hostFilteredServers.filter((s: any) =>
            s.label?.toLowerCase().includes(q) ||
            s.ip_v4?.includes(q) ||
            s.hostname?.toLowerCase().includes(q) ||
            s.region?.toLowerCase().includes(q) ||
            s.os?.toLowerCase().includes(q)
        );
    }, [hostFilteredServers, searchText]);

    // ── Power status badge ──
    const powerBadge = (status: string) => {
        const map: Record<string, { color: string; bg: string; border: string }> = {
            running: { color: MN.green, bg: 'rgba(34,197,94,0.15)', border: 'rgba(34,197,94,0.3)' },
            stopped: { color: MN.red, bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.3)' },
            paused: { color: MN.orange, bg: 'rgba(251,146,60,0.15)', border: 'rgba(251,146,60,0.3)' },
        };
        const s = map[status] || { color: MN.muted, bg: 'rgba(148,163,184,0.15)', border: 'rgba(148,163,184,0.3)' };
        return (
            <Tag style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>
                <span style={{
                    width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
                    background: s.color, boxShadow: `0 0 6px ${s.color}`, marginRight: 6,
                }} />
                {status}
            </Tag>
        );
    };

    // ── Job status icon ──
    const jobIcon = (s: string) => {
        switch (s) {
            case 'succeeded': return <CheckCircleOutlined style={{ color: MN.green }} />;
            case 'failed': return <CloseCircleOutlined style={{ color: MN.red }} />;
            case 'running': return <LoadingOutlined style={{ color: MN.accent }} spin />;
            default: return <ClockCircleOutlined style={{ color: MN.orange }} />;
        }
    };

    // ── Server table columns ──
    const serverCols = [
        {
            title: 'SERVER', dataIndex: 'label', key: 'label',
            sorter: (a: any, b: any) => (a.label || '').localeCompare(b.label || ''),
            render: (t: string, rec: any) => (
                <div>
                    <Text style={{ color: '#fff', fontWeight: 600, cursor: 'pointer' }}
                        onClick={() => setSelectedServer(rec)}>{t}</Text>
                    {rec.hostname && <div><Text style={{ color: MN.muted, fontSize: 11, fontFamily: 'monospace' }}>{rec.hostname}</Text></div>}
                </div>
            ),
        },
        {
            title: 'IP', dataIndex: 'ip_v4', key: 'ip_v4',
            render: (t: string) => (
                <Tooltip title="Click to copy">
                    <Text style={{ color: MN.cyan, fontFamily: 'monospace', cursor: 'pointer' }}
                        onClick={() => { navigator.clipboard.writeText(t); message.success('IP copied'); }}>
                        {t}
                    </Text>
                </Tooltip>
            ),
        },
        {
            title: 'POWER', dataIndex: 'power_status', key: 'power_status',
            filters: [
                { text: 'Running', value: 'running' },
                { text: 'Stopped', value: 'stopped' },
            ],
            onFilter: (value: any, record: any) => record.power_status === value,
            render: (t: string) => powerBadge(t),
        },
        {
            title: 'PLAN', dataIndex: 'plan', key: 'plan',
            render: (t: string) => (
                <Tag style={{ background: 'rgba(59,130,246,0.15)', color: MN.accent, border: '1px solid rgba(59,130,246,0.3)', fontFamily: 'monospace', fontSize: 11 }}>
                    {t || '—'}
                </Tag>
            ),
        },
        {
            title: 'REGION', dataIndex: 'region', key: 'region',
            render: (t: string) => <Text style={{ color: MN.muted, fontSize: 12 }}>{t || '—'}</Text>,
        },
        {
            title: 'OS', dataIndex: 'os', key: 'os', ellipsis: true,
            render: (t: string) => <Text style={{ color: MN.muted, fontSize: 12 }}>{t || '—'}</Text>,
        },
        {
            title: 'SPEC', key: 'spec',
            render: (_: any, rec: any) => (
                <Text style={{ color: MN.muted, fontSize: 11, fontFamily: 'monospace' }}>
                    {rec.vcpu_count || '?'}c / {rec.ram_mb ? Math.round(rec.ram_mb / 1024) : '?'}G / {rec.disk_gb || '?'}G
                </Text>
            ),
        },
        {
            title: 'ACTIONS', key: 'actions', width: 190,
            render: (_: any, rec: any) => (
                <Space size={4}>
                    <Tooltip title="Details">
                        <Button size="small" onClick={() => setSelectedServer(rec)}
                            style={{ background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.3)', color: MN.accent }}>
                            <InfoCircleOutlined />
                        </Button>
                    </Tooltip>
                    <Tooltip title="Console">
                        <Button size="small" onClick={() => consoleMut.mutate(rec.id)}
                            style={{ background: 'rgba(167,139,250,0.15)', border: '1px solid rgba(167,139,250,0.3)', color: MN.purple }}>
                            <DesktopOutlined />
                        </Button>
                    </Tooltip>
                    {rec.power_status === 'running' ? (
                        <Tooltip title="Stop">
                            <Button size="small" onClick={() => powerMut.mutate({ id: rec.id, action: 'stop' })}
                                style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: MN.red }}>
                                <PauseCircleOutlined />
                            </Button>
                        </Tooltip>
                    ) : (
                        <Tooltip title="Start">
                            <Button size="small" onClick={() => powerMut.mutate({ id: rec.id, action: 'start' })}
                                style={{ background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.3)', color: MN.green }}>
                                <PlayCircleOutlined />
                            </Button>
                        </Tooltip>
                    )}
                    <Tooltip title="Reboot">
                        <Button size="small" onClick={() => {
                            Modal.confirm({
                                title: <span style={{ color: MN.text }}>Reboot Server</span>,
                                icon: <ThunderboltOutlined style={{ color: MN.orange }} />,
                                content: <div style={{ color: MN.muted }}>Reboot <strong style={{ color: '#fff' }}>{rec.label}</strong>?</div>,
                                okText: 'Reboot',
                                okButtonProps: { danger: true },
                                styles: { header: { background: MN.bg }, body: { background: MN.bg }, mask: { background: 'rgba(0,0,0,0.6)' } },
                                onOk: () => powerMut.mutate({ id: rec.id, action: 'reboot' }),
                            });
                        }}
                            style={{ background: 'rgba(251,146,60,0.15)', border: '1px solid rgba(251,146,60,0.3)', color: MN.orange }}>
                            <ReloadOutlined />
                        </Button>
                    </Tooltip>
                </Space>
            ),
        },
    ];

    return (
        <div style={pageContainer(MN)}>
            <style>{`
                .srv-table .ant-table { background: transparent !important; }
                .srv-table .ant-table-thead > tr > th { background: rgba(30,41,59,0.6) !important; color: ${MN.muted} !important; border-bottom: 1px solid ${MN.border} !important; font-size: 11px !important; letter-spacing: 0.5px; }
                .srv-table .ant-table-tbody > tr > td { border-bottom: 1px solid ${MN.border} !important; background: transparent !important; }
                .srv-table .ant-table-tbody > tr:hover > td { background: rgba(59,130,246,0.05) !important; }
                .srv-table .ant-table-cell { color: ${MN.text} !important; }
                .srv-table .ant-pagination .ant-pagination-item a { color: ${MN.muted} !important; }
                .srv-table .ant-pagination .ant-pagination-item-active { border-color: ${MN.accent} !important; }
                .srv-table .ant-pagination .ant-pagination-item-active a { color: ${MN.accent} !important; }
                .srv-table .ant-empty-description { color: ${MN.muted} !important; }
                .srv-table .ant-select-selector { background: ${MN.card} !important; border-color: ${MN.border} !important; color: ${MN.muted} !important; }
                .srv-table .ant-pagination-prev .ant-pagination-item-link,
                .srv-table .ant-pagination-next .ant-pagination-item-link { color: ${MN.muted} !important; }
                .srv-table .ant-table-filter-trigger { color: ${MN.muted} !important; }
                .ant-drawer .ant-drawer-close { color: ${MN.muted} !important; }
                .ant-drawer .ant-drawer-close:hover { color: ${MN.text} !important; }
            `}</style>

            {/* ═══ Header ═══ */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <Title level={2} style={{ margin: 0, color: MN.text }}>
                    <CloudServerOutlined style={{ marginRight: 10, color: MN.accent }} />
                    Server Administration
                </Title>
                <Space>
                    <Input
                        prefix={<SearchOutlined style={{ color: MN.muted }} />}
                        placeholder="Search servers..."
                        value={searchText}
                        onChange={e => setSearchText(e.target.value)}
                        style={{ width: 240, background: MN.card, borderColor: MN.border, color: MN.text }}
                        allowClear
                    />
                    <Button icon={<ReloadOutlined />}
                        onClick={() => { qc.invalidateQueries({ queryKey: ['servers'] }); qc.invalidateQueries({ queryKey: ['server-jobs'] }); }}
                        style={{ background: MN.card, borderColor: MN.border, color: MN.muted }}>
                        Refresh
                    </Button>
                    <Button type="primary" icon={<SyncOutlined />} onClick={() => syncMut.mutate(undefined)} loading={syncMut.isPending}>
                        Sync All
                    </Button>
                </Space>
            </div>

            {/* ═══ Dashboard Panels ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
                {/* Fleet Panel */}
                <div style={cardStyle()}>
                    <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                        <CloudServerOutlined style={{ marginRight: 6 }} /> {selectedHostLabel ? selectedHostLabel.toUpperCase() : 'FLEET'}
                    </Text>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                        <div style={{ position: 'relative', width: 80, height: 80 }}>
                            <Progress type="circle" percent={stats.total > 0 ? Math.round((stats.running / stats.total) * 100) : 0}
                                size={80} strokeColor={MN.green} trailColor="rgba(30,41,59,0.8)"
                                format={() => <span style={{ color: '#fff', fontSize: 22, fontWeight: 700 }}>{stats.total}</span>} />
                        </div>
                        <div>
                            {selectedHostId ? (
                                <>
                                    <div style={{ color: MN.green, fontSize: 14 }}>▲ {stats.running} Running</div>
                                    <div style={{ color: MN.red, fontSize: 13 }}>■ {stats.stopped} Stopped</div>
                                    {stats.other > 0 && <div style={{ color: MN.muted, fontSize: 12 }}>◌ {stats.other} Other</div>}
                                </>
                            ) : (
                                Object.entries(stats.byProvider).map(([prov, count]) => (
                                    <div key={prov} style={{ color: prov === 'vultr' ? MN.cyan : MN.purple, fontSize: 13 }}>
                                        {prov === 'vultr' ? '▸' : '◆'} {count} {prov.charAt(0).toUpperCase() + prov.slice(1)}
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>

                {/* Resources Panel */}
                <div style={cardStyle()}>
                    <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                        <ThunderboltOutlined style={{ marginRight: 6 }} />
                        {isProxmoxHost && hostResources ? 'HOST RESOURCES' : 'RESOURCES'}
                    </Text>
                    {isProxmoxHost && hostResources ? (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12, marginTop: 4 }}>
                            {[
                                {
                                    label: 'CPU',
                                    icon: '⚡',
                                    pct: hostResources.cpu_usage_pct,
                                    detail: `${hostResources.cpu_cores} cores`,
                                    color: hostResources.cpu_usage_pct > 80 ? MN.red : hostResources.cpu_usage_pct > 50 ? MN.orange : MN.green,
                                },
                                {
                                    label: 'RAM',
                                    icon: '💾',
                                    pct: hostResources.ram_usage_pct,
                                    detail: `${hostResources.ram_free_gb} GB free / ${hostResources.ram_total_gb} GB`,
                                    color: hostResources.ram_usage_pct > 85 ? MN.red : hostResources.ram_usage_pct > 60 ? MN.orange : MN.green,
                                },
                                {
                                    label: 'Disk (rootfs)',
                                    icon: '💿',
                                    pct: hostResources.disk_usage_pct,
                                    detail: `${hostResources.disk_free_gb} GB free / ${hostResources.disk_total_gb} GB`,
                                    color: hostResources.disk_usage_pct > 85 ? MN.red : hostResources.disk_usage_pct > 60 ? MN.orange : MN.green,
                                },
                                // Append storage pools as additional disk bars
                                ...(hostResources.storage_pools || []).map((pool: any) => ({
                                    label: `${pool.name}`,
                                    icon: '🗄️',
                                    pct: pool.usage_pct,
                                    detail: `${pool.free_gb} GB free / ${pool.total_gb} GB  ·  ${pool.type}`,
                                    color: pool.usage_pct > 85 ? MN.red : pool.usage_pct > 60 ? MN.orange : MN.green,
                                })),
                            ].map(item => (
                                <div key={item.label}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                        <Text style={{ color: MN.muted, fontSize: 12 }}>{item.icon} {item.label}</Text>
                                        <Text style={{ color: '#fff', fontWeight: 600, fontSize: 12 }}>{item.pct}%</Text>
                                    </div>
                                    <div style={{ background: 'rgba(30,41,59,0.8)', borderRadius: 4, height: 8, overflow: 'hidden' }}>
                                        <div style={{
                                            width: `${Math.min(item.pct, 100)}%`,
                                            height: '100%',
                                            background: `linear-gradient(90deg, ${item.color}, ${item.color}88)`,
                                            borderRadius: 4,
                                            transition: 'width 0.6s ease',
                                            boxShadow: `0 0 8px ${item.color}44`,
                                        }} />
                                    </div>
                                    <Text style={{ color: MN.muted, fontSize: 10, marginTop: 2, display: 'block' }}>{item.detail}</Text>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10, marginTop: 4 }}>
                            {[
                                { label: 'vCPUs', value: stats.totalVcpu, icon: '⚡' },
                                { label: 'RAM', value: `${stats.totalRam} GB`, icon: '💾' },
                                { label: 'Disk', value: `${stats.totalDisk} GB`, icon: '💿' },
                            ].map(item => (
                                <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <Text style={{ color: MN.muted, fontSize: 12 }}>{item.icon} {item.label}</Text>
                                    <Text style={{ color: '#fff', fontWeight: 700, fontSize: 16 }}>{item.value}</Text>
                                </div>
                            ))}
                        </div>
                    )}
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

                {/* Health / Hosts Panel */}
                <div style={cardStyle()}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1 }}>
                            <HddOutlined style={{ marginRight: 6 }} /> HOSTS
                        </Text>
                        {selectedHostId && (
                            <Tag style={{ cursor: 'pointer', background: 'rgba(59,130,246,0.15)', color: MN.accent, border: '1px solid rgba(59,130,246,0.3)', fontSize: 10, margin: 0 }}
                                onClick={() => setSelectedHostId(null)}>Show All ✕</Tag>
                        )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
                        {hosts.length === 0 && <Text style={{ color: MN.muted, fontStyle: 'italic' }}>No hosts registered</Text>}
                        {hosts.map((h: any) => {
                            const isSelected = selectedHostId === h.id;
                            const hostCount = servers.filter((s: any) => s.host_id === h.id).length;
                            return (
                                <div key={h.id}
                                    onClick={() => setSelectedHostId(isSelected ? null : h.id)}
                                    style={{
                                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                        cursor: 'pointer', padding: '6px 10px', borderRadius: 8,
                                        background: isSelected ? 'rgba(59,130,246,0.15)' : 'transparent',
                                        border: isSelected ? `1px solid ${MN.accent}` : '1px solid transparent',
                                        transition: 'all 0.2s',
                                    }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <span style={{
                                            width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
                                            background: h.is_active ? MN.green : MN.red,
                                            boxShadow: h.is_active ? `0 0 6px ${MN.green}` : `0 0 6px ${MN.red}`,
                                        }} />
                                        <Text style={{ color: isSelected ? '#fff' : MN.text, fontSize: 13, fontWeight: isSelected ? 600 : 400 }}>{h.label}</Text>
                                    </div>
                                    <Space size={6}>
                                        <Text style={{ color: MN.muted, fontSize: 11 }}>{hostCount}</Text>
                                        <Tag style={{
                                            margin: 0, fontSize: 10,
                                            background: 'rgba(59,130,246,0.15)', color: MN.accent,
                                            border: '1px solid rgba(59,130,246,0.3)', borderRadius: 4,
                                        }}>
                                            {h.provider}
                                        </Tag>
                                    </Space>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* ═══ Tabs: Servers + Jobs ═══ */}
            <Tabs
                defaultActiveKey="servers"
                style={{ marginBottom: 24 }}
                items={[
                    {
                        key: 'servers',
                        label: <span style={{ color: MN.text }}><CloudServerOutlined style={{ marginRight: 6 }} />Servers ({filteredServers.length})</span>,
                        children: (
                            <div className="srv-table" style={{ ...cardStyle(), padding: 0 }}>
                                <Table
                                    columns={serverCols}
                                    dataSource={filteredServers}
                                    rowKey="id"
                                    loading={serversLoading}
                                    pagination={{ pageSize: 20, showTotal: (t) => <span style={{ color: MN.muted }}>{t} servers</span> }}
                                    locale={{ emptyText: <Empty description={<span style={{ color: MN.muted }}>No servers found</span>} /> }}
                                    scroll={{ x: 1100 }}
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
                            <div className="srv-table" style={{ ...cardStyle(), padding: 0 }}>
                                <Table
                                    columns={[
                                        {
                                            title: 'STATUS', dataIndex: 'status', key: 'status', width: 110,
                                            render: (s: string) => <Space>{jobIcon(s)}<Text style={{ color: MN.text }}>{s}</Text></Space>,
                                        },
                                        {
                                            title: 'OPERATION', dataIndex: 'operation', key: 'op',
                                            render: (t: string) => <Tag style={{ background: 'rgba(59,130,246,0.15)', color: MN.accent, border: '1px solid rgba(59,130,246,0.3)' }}>{t}</Tag>,
                                        },
                                        {
                                            title: 'ATTEMPTS', dataIndex: 'attempts', key: 'attempts', width: 90,
                                            render: (t: number) => <Text style={{ color: MN.muted }}>{t}</Text>,
                                        },
                                        {
                                            title: 'ERROR', dataIndex: 'last_error', key: 'error', ellipsis: true,
                                            render: (t: string | null) => t ? <Text style={{ color: MN.red, fontSize: 12 }}>{t}</Text> : <Text style={{ color: MN.muted }}>—</Text>,
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
                className="srv-tabs"
            />

            {/* ═══ Server Detail Drawer ═══ */}
            <Drawer
                title={
                    <span style={{ color: MN.text }}>
                        <CloudServerOutlined style={{ marginRight: 8, color: MN.accent }} />
                        {selectedServer?.label}
                        {selectedServer && (
                            <span style={{ marginLeft: 12 }}>
                                {powerBadge(selectedServer.power_status)}
                            </span>
                        )}
                    </span>
                }
                open={!!selectedServer}
                onClose={() => setSelectedServer(null)}
                width={Math.min(700, window.innerWidth - 40)}
                styles={{
                    header: { background: MN.bg, borderBottom: `1px solid ${MN.border}` },
                    body: { background: MN.bg, padding: 20 },
                }}
                extra={
                    selectedServer && (
                        <Space>
                            {selectedServer.power_status !== 'running' && (
                                <Tooltip title="Permanently destroy this server">
                                    <Button size="small" icon={<DeleteOutlined />}
                                        onClick={() => { setDeleteModalOpen(true); setDeletePassword(''); setDeleteError(''); }}
                                        style={{ background: 'rgba(239,68,68,0.10)', border: '1px solid rgba(239,68,68,0.25)', color: MN.red }}>
                                        Delete
                                    </Button>
                                </Tooltip>
                            )}
                            <Button size="small" icon={<DesktopOutlined />} onClick={() => consoleMut.mutate(selectedServer.id)}
                                style={{ background: 'rgba(167,139,250,0.15)', border: '1px solid rgba(167,139,250,0.3)', color: MN.purple }}>
                                Console
                            </Button>
                            {selectedServer.power_status === 'running' ? (
                                <Button size="small" icon={<PoweroffOutlined />}
                                    onClick={() => powerMut.mutate({ id: selectedServer.id, action: 'stop' })}
                                    style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: MN.red }}>
                                    Stop
                                </Button>
                            ) : (
                                <Button size="small" icon={<PlayCircleOutlined />}
                                    onClick={() => powerMut.mutate({ id: selectedServer.id, action: 'start' })}
                                    style={{ background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.3)', color: MN.green }}>
                                    Start
                                </Button>
                            )}
                        </Space>
                    )
                }
            >
                {selectedServer && (
                    <div>
                        {/* Quick info cards */}
                        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
                            {[
                                { label: 'IPv4', value: selectedServer.ip_v4 || meshDevice?.ip || '—', mono: true },
                                { label: 'IPv6', value: selectedServer.ip_v6 ? `${selectedServer.ip_v6.substring(0, 20)}…` : '—', mono: true },
                                { label: 'Region', value: selectedServer.region || '—' },
                                { label: 'Plan', value: selectedServer.plan || '—' },
                            ].map(item => (
                                <div key={item.label} style={{ background: MN.card, border: `1px solid ${MN.border}`, borderRadius: 8, padding: '8px 16px', minWidth: 120 }}>
                                    <Text style={{ color: MN.muted, fontSize: 10, letterSpacing: 0.5, display: 'block' }}>{item.label}</Text>
                                    <Text style={{ color: MN.text, fontWeight: 600, fontFamily: item.mono ? 'monospace' : 'inherit', fontSize: 13 }}>{item.value}</Text>
                                </div>
                            ))}
                        </div>

                        {/* Live Resources */}
                        {selectedServer.power_status === 'running' && (
                            <div style={{ ...cardStyle(), marginBottom: 16 }}>
                                <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                                    <ThunderboltOutlined style={{ marginRight: 6 }} />
                                    LIVE RESOURCES
                                    {serverResourcesLoading && <LoadingOutlined style={{ marginLeft: 8, fontSize: 10 }} spin />}
                                </Text>
                                {serverResources ? (
                                    <div>
                                        {/* Proxmox: CPU + RAM gauges */}
                                        {serverResources.provider === 'proxmox' && (
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12 }}>
                                                {[
                                                    {
                                                        label: 'CPU',
                                                        icon: '⚡',
                                                        pct: serverResources.cpu_usage_pct,
                                                        detail: `${serverResources.cpu_cores} cores`,
                                                        color: (serverResources.cpu_usage_pct ?? 0) > 80 ? MN.red : (serverResources.cpu_usage_pct ?? 0) > 50 ? MN.orange : MN.green,
                                                    },
                                                    {
                                                        label: 'RAM',
                                                        icon: '💾',
                                                        pct: serverResources.ram_usage_pct,
                                                        detail: `${Math.round((serverResources.ram_used_mb || 0) / 1024 * 10) / 10} GB / ${Math.round((serverResources.ram_total_mb || 0) / 1024 * 10) / 10} GB`,
                                                        color: (serverResources.ram_usage_pct ?? 0) > 85 ? MN.red : (serverResources.ram_usage_pct ?? 0) > 60 ? MN.orange : MN.green,
                                                    },
                                                ].map(item => (
                                                    <div key={item.label}>
                                                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                                            <Text style={{ color: MN.muted, fontSize: 12 }}>{item.icon} {item.label}</Text>
                                                            <Text style={{ color: '#fff', fontWeight: 600, fontSize: 12 }}>{item.pct != null ? `${item.pct}%` : '—'}</Text>
                                                        </div>
                                                        <div style={{ background: 'rgba(30,41,59,0.8)', borderRadius: 4, height: 8, overflow: 'hidden' }}>
                                                            <div style={{
                                                                width: `${Math.min(item.pct ?? 0, 100)}%`,
                                                                height: '100%',
                                                                background: `linear-gradient(90deg, ${item.color}, ${item.color}88)`,
                                                                borderRadius: 4,
                                                                transition: 'width 0.6s ease',
                                                                boxShadow: `0 0 8px ${item.color}44`,
                                                            }} />
                                                        </div>
                                                        <Text style={{ color: MN.muted, fontSize: 10, marginTop: 2, display: 'block' }}>{item.detail}</Text>
                                                    </div>
                                                ))}
                                                {serverResources.uptime_seconds > 0 && (
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                                                        <Text style={{ color: MN.muted, fontSize: 11 }}>⏱ Uptime</Text>
                                                        <Text style={{ color: MN.text, fontSize: 11 }}>
                                                            {Math.floor(serverResources.uptime_seconds / 86400)}d {Math.floor((serverResources.uptime_seconds % 86400) / 3600)}h
                                                        </Text>
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {/* Vultr: Bandwidth */}
                                        {serverResources.provider === 'vultr' && (
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                                                {[
                                                    { label: 'Bandwidth In', value: serverResources.bandwidth_in_gb, icon: '📥', color: MN.cyan },
                                                    { label: 'Bandwidth Out', value: serverResources.bandwidth_out_gb, icon: '📤', color: MN.purple },
                                                ].map(item => (
                                                    <div key={item.label} style={{ textAlign: 'center' }}>
                                                        <div style={{ fontSize: 11, color: MN.muted }}>{item.icon} {item.label}</div>
                                                        <div style={{ fontSize: 22, fontWeight: 700, color: item.color, marginTop: 4 }}>
                                                            {item.value != null ? `${item.value} GB` : '—'}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {/* GPU: Utilization, VRAM, Temp, Power + LLM + Voice */}
                                        {serverResources.provider === 'gpu' && (
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12 }}>
                                                {/* GPU Name + Count header */}
                                                {serverResources.gpu_name && (
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <Text style={{ color: MN.accent, fontSize: 13, fontWeight: 600 }}>
                                                            🎮 {serverResources.gpu_name}
                                                        </Text>
                                                        {serverResources.gpu_count != null && serverResources.gpu_count > 1 && (
                                                            <Tag color="purple" style={{ fontSize: 10 }}>×{serverResources.gpu_count}</Tag>
                                                        )}
                                                    </div>
                                                )}

                                                {/* GPU Utilization + VRAM bars */}
                                                {[
                                                    {
                                                        label: 'GPU',
                                                        icon: '⚡',
                                                        pct: serverResources.gpu_usage_pct,
                                                        detail: serverResources.gpu_temp_c != null ? `${serverResources.gpu_temp_c}°C` : '',
                                                        color: (serverResources.gpu_usage_pct ?? 0) > 90 ? MN.red : (serverResources.gpu_usage_pct ?? 0) > 60 ? MN.orange : MN.green,
                                                    },
                                                    {
                                                        label: 'VRAM',
                                                        icon: '💾',
                                                        pct: serverResources.gpu_vram_usage_pct,
                                                        detail: serverResources.gpu_vram_used_mb != null && serverResources.gpu_vram_total_mb
                                                            ? `${Math.round(serverResources.gpu_vram_used_mb / 1024 * 10) / 10} / ${Math.round(serverResources.gpu_vram_total_mb / 1024 * 10) / 10} GB`
                                                            : '',
                                                        color: (serverResources.gpu_vram_usage_pct ?? 0) > 90 ? MN.red : (serverResources.gpu_vram_usage_pct ?? 0) > 70 ? MN.orange : MN.green,
                                                    },
                                                ].filter(item => item.pct != null).map(item => (
                                                    <div key={item.label}>
                                                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                                            <Text style={{ color: MN.muted, fontSize: 12 }}>{item.icon} {item.label}</Text>
                                                            <Text style={{ color: '#fff', fontWeight: 600, fontSize: 12 }}>{item.pct != null ? `${item.pct}%` : '—'}</Text>
                                                        </div>
                                                        <div style={{ background: 'rgba(30,41,59,0.8)', borderRadius: 4, height: 8, overflow: 'hidden' }}>
                                                            <div style={{
                                                                width: `${Math.min(item.pct ?? 0, 100)}%`,
                                                                height: '100%',
                                                                background: `linear-gradient(90deg, ${item.color}, ${item.color}88)`,
                                                                borderRadius: 4,
                                                                transition: 'width 0.6s ease',
                                                                boxShadow: `0 0 8px ${item.color}44`,
                                                            }} />
                                                        </div>
                                                        {item.detail && <Text style={{ color: MN.muted, fontSize: 10, marginTop: 2, display: 'block' }}>{item.detail}</Text>}
                                                    </div>
                                                ))}

                                                {/* Power draw */}
                                                {serverResources.gpu_power_draw_w != null && (
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <Text style={{ color: MN.muted, fontSize: 11 }}>🔌 Power Draw</Text>
                                                        <Text style={{ color: MN.text, fontSize: 11, fontWeight: 600 }}>{serverResources.gpu_power_draw_w} W</Text>
                                                    </div>
                                                )}

                                                {/* LLM Inference section */}
                                                {serverResources.llm_model_loaded && (
                                                    <>
                                                        <div style={{ borderTop: `1px solid ${MN.border}`, paddingTop: 8, marginTop: 4 }}>
                                                            <Text style={{ color: MN.muted, fontSize: 10, letterSpacing: 0.8, display: 'block', marginBottom: 8 }}>
                                                                🧠 LLM INFERENCE
                                                            </Text>
                                                        </div>
                                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                                                            <div><Text style={{ color: MN.muted, fontSize: 10 }}>Model</Text><br /><Text style={{ color: MN.accent, fontSize: 12, fontWeight: 600 }}>{serverResources.llm_model_loaded}</Text></div>
                                                            <div><Text style={{ color: MN.muted, fontSize: 10 }}>Active Requests</Text><br /><Text style={{ color: MN.text, fontSize: 18, fontWeight: 700 }}>{serverResources.llm_requests_active ?? '—'}</Text></div>
                                                            <div><Text style={{ color: MN.muted, fontSize: 10 }}>Avg Latency</Text><br /><Text style={{ color: MN.text, fontSize: 14, fontWeight: 600 }}>{serverResources.llm_avg_latency_ms != null ? `${serverResources.llm_avg_latency_ms} ms` : '—'}</Text></div>
                                                            <div><Text style={{ color: MN.muted, fontSize: 10 }}>Throughput</Text><br /><Text style={{ color: MN.green, fontSize: 14, fontWeight: 600 }}>{serverResources.llm_tokens_per_sec != null ? `${serverResources.llm_tokens_per_sec} tok/s` : '—'}</Text></div>
                                                        </div>
                                                    </>
                                                )}

                                                {/* Voice Agent section */}
                                                {serverResources.voice_concurrent_calls != null && (
                                                    <>
                                                        <div style={{ borderTop: `1px solid ${MN.border}`, paddingTop: 8, marginTop: 4 }}>
                                                            <Text style={{ color: MN.muted, fontSize: 10, letterSpacing: 0.8, display: 'block', marginBottom: 8 }}>
                                                                🎙 VOICE AGENT
                                                            </Text>
                                                        </div>
                                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                                                            <div style={{ textAlign: 'center' }}>
                                                                <Text style={{ color: MN.muted, fontSize: 10 }}>Calls</Text>
                                                                <div style={{ fontSize: 22, fontWeight: 700, color: MN.cyan }}>
                                                                    {serverResources.voice_concurrent_calls}
                                                                    {serverResources.voice_max_concurrent != null && <span style={{ fontSize: 11, color: MN.muted, fontWeight: 400 }}> / {serverResources.voice_max_concurrent}</span>}
                                                                </div>
                                                            </div>
                                                            <div style={{ textAlign: 'center' }}>
                                                                <Text style={{ color: MN.muted, fontSize: 10 }}>Latency</Text>
                                                                <div style={{ fontSize: 18, fontWeight: 700, color: (serverResources.voice_avg_latency_ms ?? 0) > 500 ? MN.red : (serverResources.voice_avg_latency_ms ?? 0) > 200 ? MN.orange : MN.green }}>
                                                                    {serverResources.voice_avg_latency_ms != null ? `${serverResources.voice_avg_latency_ms}ms` : '—'}
                                                                </div>
                                                            </div>
                                                            <div style={{ textAlign: 'center' }}>
                                                                <Text style={{ color: MN.muted, fontSize: 10 }}>Today</Text>
                                                                <div style={{ fontSize: 18, fontWeight: 700, color: MN.text }}>
                                                                    {serverResources.voice_total_calls_today ?? '—'}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <Text style={{ color: MN.muted, fontStyle: 'italic', fontSize: 12 }}>Loading resources…</Text>
                                )}
                            </div>
                        )}

                        {/* MeshCentral Agent Info */}
                        {meshDevice && (
                            <div style={{ ...cardStyle(), marginBottom: 16 }}>
                                <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                                    🌐 MESHCENTRAL AGENT
                                </Text>
                                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
                                    {[
                                        { label: 'Public IP', value: meshDevice.ip || '—', mono: true },
                                        { label: 'Status', value: meshDevice.connected ? '🟢 Connected' : '🔴 Offline' },
                                        { label: 'OS', value: meshDevice.os_desc || '—' },
                                        { label: 'Group', value: meshDevice.group_name || '—' },
                                        ...(meshDevice.last_boot ? [{
                                            label: 'Last Boot',
                                            value: new Date(meshDevice.last_boot).toLocaleDateString() + ' ' + new Date(meshDevice.last_boot).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                                        }] : []),
                                    ].map(item => (
                                        <div key={item.label} style={{ background: 'rgba(17,24,39,0.5)', border: `1px solid ${MN.border}`, borderRadius: 6, padding: '6px 12px', minWidth: 110 }}>
                                            <Text style={{ color: MN.muted, fontSize: 9, letterSpacing: 0.5, display: 'block' }}>{item.label}</Text>
                                            <Text style={{ color: MN.text, fontWeight: 600, fontFamily: (item as any).mono ? 'monospace' : 'inherit', fontSize: 12 }}>{item.value}</Text>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Specs */}
                        <div style={{ ...cardStyle(), marginBottom: 16 }}>
                            <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                                SPECIFICATIONS
                            </Text>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
                                {[
                                    { label: 'vCPU', value: selectedServer.vcpu_count || '—', suffix: 'cores' },
                                    { label: 'RAM', value: selectedServer.ram_mb ? `${Math.round(selectedServer.ram_mb / 1024)}` : '—', suffix: 'GB' },
                                    { label: 'Disk', value: selectedServer.disk_gb || '—', suffix: 'GB' },
                                ].map(s => (
                                    <div key={s.label} style={{ textAlign: 'center' }}>
                                        <div style={{ color: '#fff', fontSize: 24, fontWeight: 700 }}>{s.value}</div>
                                        <div style={{ color: MN.muted, fontSize: 11 }}>{s.suffix}</div>
                                        <div style={{ color: MN.accent, fontSize: 12, marginTop: 4 }}>{s.label}</div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Metadata */}
                        <div style={{ ...cardStyle() }}>
                            <Text style={{ color: MN.muted, fontSize: 11, letterSpacing: 1, display: 'block', marginBottom: 12 }}>
                                METADATA
                            </Text>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                                {[
                                    { label: 'OS', value: selectedServer.os },
                                    { label: 'Hostname', value: selectedServer.hostname },
                                    { label: 'Provider', value: selectedServer.provider },
                                    { label: 'Provider ID', value: selectedServer.provider_instance_id },
                                    { label: 'Status', value: selectedServer.status },
                                    { label: 'Last Synced', value: selectedServer.last_synced_at ? new Date(selectedServer.last_synced_at).toLocaleString() : 'Never' },
                                ].map(item => (
                                    <div key={item.label}>
                                        <Text style={{ color: MN.muted, fontSize: 10, display: 'block' }}>{item.label}</Text>
                                        <Text style={{ color: MN.text, fontSize: 13, fontFamily: 'monospace' }}>{item.value || '—'}</Text>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}
            </Drawer>

            {/* ═══ Break-Glass Delete Confirmation Modal ═══ */}
            <Modal
                title={
                    <span style={{ color: MN.red }}>
                        <ExclamationCircleOutlined style={{ marginRight: 8 }} />
                        Delete Server — Break Glass
                    </span>
                }
                open={deleteModalOpen}
                onCancel={() => { setDeleteModalOpen(false); setDeletePassword(''); setDeleteError(''); }}
                onOk={handleDeleteConfirm}
                okText={deleteVerifying ? 'Verifying…' : 'Permanently Delete'}
                okButtonProps={{ danger: true, disabled: !deletePassword || deleteVerifying, loading: deleteVerifying }}
                cancelButtonProps={{ style: { borderColor: MN.border, color: MN.muted } }}
                styles={{
                    header: { background: MN.bg, borderBottom: `1px solid ${MN.border}` },
                    body: { background: MN.bg, padding: '20px 24px' },
                    footer: { background: MN.bg, borderTop: `1px solid ${MN.border}` },
                }}
                destroyOnClose
            >
                <div style={{ marginBottom: 16 }}>
                    <Text style={{ color: MN.text, fontSize: 14 }}>
                        You are about to permanently destroy{' '}
                        <strong style={{ color: '#fff' }}>{selectedServer?.label}</strong>.
                    </Text>
                    <div style={{
                        marginTop: 12, padding: '10px 14px', borderRadius: 8,
                        background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                        wordBreak: 'break-word', overflow: 'hidden',
                    }}>
                        <Text style={{ color: MN.red, fontSize: 12 }}>
                            ⚠ This action cannot be undone. The server will be destroyed at the provider level.
                        </Text>
                    </div>
                </div>
                <div>
                    <Text style={{ color: MN.muted, fontSize: 12, display: 'block', marginBottom: 8 }}>
                        <LockOutlined style={{ marginRight: 4 }} /> Enter your password to confirm:
                    </Text>
                    <Input.Password
                        value={deletePassword}
                        onChange={(e) => { setDeletePassword(e.target.value); setDeleteError(''); }}
                        onPressEnter={handleDeleteConfirm}
                        placeholder="Your portal password"
                        status={deleteError ? 'error' : undefined}
                        style={{ background: MN.card, borderColor: deleteError ? MN.red : MN.border, color: MN.text }}
                    />
                    {deleteError && (
                        <Text style={{ color: MN.red, fontSize: 12, marginTop: 4, display: 'block' }}>{deleteError}</Text>
                    )}
                </div>
            </Modal>
        </div>
    );
}
