/**
 * Monitoring Dashboard — Nagios Integration
 *
 * Overview cards with Apple-like hover effects and click-to-filter.
 * Problems list sorted by severity and a host status grid.
 */
import { useState, useMemo } from 'react';
import { Typography, Card, Table, Tag, Button, Spin, message, Tooltip, Drawer, Modal, Form, Input, Select, Popconfirm, Space } from 'antd';
import { TiltCard } from '../components/TiltCard';
import {
    ReloadOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
    WarningOutlined,
    QuestionCircleOutlined,
    CloudServerOutlined,
    DesktopOutlined,
    AlertOutlined,
    FilterOutlined,
    PlusOutlined,
    EditOutlined,
    DeleteOutlined,
    MinusCircleOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useThemeStore } from '../stores/themeStore';
import { getTokens } from '../theme';

const { Title, Text } = Typography;

// ── Filter types ──
type FilterKey = 'hosts_up' | 'hosts_down' | 'services_ok' | 'services_warning' | 'services_critical' | 'services_unknown' | null;

// ── API helpers ──
const api = axios.create({ baseURL: '/monitor/v1/nagios' });

// ── Interactive Stat Card ──
function StatCard({
    label, value, color, icon, isActive, onClick,
}: {
    label: string; value: number; color: string; icon: React.ReactNode;
    isActive: boolean; onClick: () => void;
}) {
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    return (
        <TiltCard
            className={`nx-stat-card ${isActive ? 'nx-stat-card-active' : ''}`}
            onClick={onClick}
            style={{
                '--card-color': color,
                '--card-bg': t.cardBg,
                '--card-border': t.border,
            } as React.CSSProperties}
            intensity={12}
            scale={1.06}
        >
            <div className="nx-stat-card-label">
                {icon}
                {label}
            </div>
            <div className="nx-stat-card-value" style={{ color }}>
                {value}
            </div>
            {isActive && (
                <div className="nx-stat-card-indicator">
                    <FilterOutlined style={{ fontSize: 10, marginRight: 4 }} />
                    Filtered
                </div>
            )}
        </TiltCard>
    );
}

// ── Service definition for forms ──
interface ServiceFormItem {
    description: string;
    check_command: string;
    check_interval?: number;
}

// ── Component ──
export default function MonitoringDashboard() {
    const { mode } = useThemeStore();
    const t = getTokens(mode);
    const queryClient = useQueryClient();
    const [selectedHost, setSelectedHost] = useState<string | null>(null);
    const [activeFilter, setActiveFilter] = useState<FilterKey>(null);
    const [addModalOpen, setAddModalOpen] = useState(false);
    const [editModalOpen, setEditModalOpen] = useState(false);
    const [addForm] = Form.useForm();
    const [editForm] = Form.useForm();

    // ── Queries ──
    const { data: overview, isLoading: overviewLoading, refetch: refetchOverview } = useQuery({
        queryKey: ['nagios-overview'],
        queryFn: () => api.get('/overview').then(r => r.data),
        refetchInterval: 60_000,
    });

    const { data: allProblems = [], isLoading: problemsLoading, refetch: refetchProblems } = useQuery({
        queryKey: ['nagios-problems'],
        queryFn: () => api.get('/problems').then(r => r.data),
        refetchInterval: 60_000,
    });

    const { data: allHosts = [], isLoading: hostsLoading, refetch: refetchHosts } = useQuery({
        queryKey: ['nagios-hosts'],
        queryFn: () => api.get('/hosts').then(r => r.data),
        refetchInterval: 60_000,
    });

    const { data: allServices = [], isLoading: servicesLoading, refetch: refetchServices } = useQuery({
        queryKey: ['nagios-all-services'],
        queryFn: () => api.get('/services').then(r => r.data),
        refetchInterval: 60_000,
    });

    const { data: hostServices = [], isLoading: hostServicesLoading } = useQuery({
        queryKey: ['nagios-host-services', selectedHost],
        queryFn: () => api.get(`/hosts/${selectedHost}/services`).then(r => r.data),
        enabled: !!selectedHost,
    });

    const handleRefresh = () => {
        api.get('/overview?refresh=true').then(() => {
            refetchOverview();
            refetchProblems();
            refetchHosts();
            refetchServices();
            message.success('Nagios data refreshed');
        }).catch(() => message.error('Refresh failed'));
    };

    // ── Click-to-filter toggle ──
    const handleCardClick = (key: FilterKey) => {
        setActiveFilter(prev => prev === key ? null : key);
    };

    // ── Invalidate all queries after CRUD ──
    const refreshAll = () => {
        queryClient.invalidateQueries({ queryKey: ['nagios-overview'] });
        queryClient.invalidateQueries({ queryKey: ['nagios-problems'] });
        queryClient.invalidateQueries({ queryKey: ['nagios-hosts'] });
        queryClient.invalidateQueries({ queryKey: ['nagios-all-services'] });
        if (selectedHost) {
            queryClient.invalidateQueries({ queryKey: ['nagios-host-services', selectedHost] });
        }
    };

    // ── CRUD mutations ──
    const createMutation = useMutation({
        mutationFn: (data: any) => api.post('/hosts', data),
        onSuccess: () => {
            message.success('Host created and Nagios reloaded');
            setAddModalOpen(false);
            addForm.resetFields();
            // Wait a few seconds for Nagios to pick up the new host
            setTimeout(refreshAll, 3000);
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Failed to create host');
        },
    });

    const updateMutation = useMutation({
        mutationFn: ({ hostname, data }: { hostname: string; data: any }) =>
            api.put(`/hosts/${hostname}`, data),
        onSuccess: () => {
            message.success('Host updated and Nagios reloaded');
            setEditModalOpen(false);
            editForm.resetFields();
            setTimeout(refreshAll, 3000);
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Failed to update host');
        },
    });

    const deleteMutation = useMutation({
        mutationFn: (hostname: string) => api.delete(`/hosts/${hostname}`),
        onSuccess: () => {
            message.success('Host deleted and Nagios reloaded');
            setSelectedHost(null);
            setTimeout(refreshAll, 3000);
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Failed to delete host');
        },
    });

    // ── Open edit modal with pre-filled data ──
    const openEditModal = () => {
        if (!selectedHost) return;
        const host = allHosts.find((h: any) => h.host_name === selectedHost);
        editForm.setFieldsValue({
            alias: host?.alias || '',
            address: host?.address || '',
            hostgroup: 'pbx',
            services: hostServices.map((s: any) => ({
                description: s.service_description,
                check_command: s.check_command || '',
            })),
        });
        setEditModalOpen(true);
    };

    // ── Derive what to show based on active filter ──
    const filterConfig = useMemo(() => {
        switch (activeFilter) {
            case 'hosts_up':
                return {
                    mode: 'hosts' as const,
                    title: 'Hosts — UP',
                    data: allHosts.filter((h: any) => h.status === 0),
                };
            case 'hosts_down':
                return {
                    mode: 'hosts' as const,
                    title: 'Hosts — DOWN',
                    data: allHosts.filter((h: any) => h.status !== 0),
                };
            case 'services_ok':
                return {
                    mode: 'services' as const,
                    title: 'Services — OK',
                    data: allServices.filter((s: any) => s.status === 0),
                };
            case 'services_warning':
                return {
                    mode: 'services' as const,
                    title: 'Services — WARNING',
                    data: allServices.filter((s: any) => s.status === 1),
                };
            case 'services_critical':
                return {
                    mode: 'services' as const,
                    title: 'Services — CRITICAL',
                    data: allServices.filter((s: any) => s.status === 2),
                };
            case 'services_unknown':
                return {
                    mode: 'services' as const,
                    title: 'Services — UNKNOWN',
                    data: allServices.filter((s: any) => s.status === 3),
                };
            default:
                return {
                    mode: 'problems' as const,
                    title: `All Problems (${allProblems.length})`,
                    data: allProblems,
                };
        }
    }, [activeFilter, allHosts, allServices, allProblems]);

    // ── Styles ──
    const tableCardStyle: React.CSSProperties = {
        background: t.cardBg,
        border: `1px solid ${t.border}`,
        borderRadius: 12,
    };

    // ── Status tag helper ──
    const statusTag = (status: string) => {
        const map: Record<string, { color: string; icon: React.ReactNode }> = {
            UP: { color: 'green', icon: <CheckCircleOutlined /> },
            OK: { color: 'green', icon: <CheckCircleOutlined /> },
            DOWN: { color: 'red', icon: <CloseCircleOutlined /> },
            CRITICAL: { color: 'red', icon: <CloseCircleOutlined /> },
            WARNING: { color: 'orange', icon: <WarningOutlined /> },
            UNREACHABLE: { color: 'volcano', icon: <QuestionCircleOutlined /> },
            UNKNOWN: { color: 'default', icon: <QuestionCircleOutlined /> },
        };
        const s = map[status] || { color: 'default', icon: null };
        return <Tag color={s.color} icon={s.icon} style={{ fontWeight: 600 }}>{status}</Tag>;
    };

    // ── Problem columns ──
    const problemColumns = [
        {
            title: 'Type',
            dataIndex: 'type',
            key: 'type',
            width: 80,
            render: (val: string) => (
                <Tag color={val === 'host' ? 'purple' : 'blue'} style={{ fontWeight: 600, fontSize: 10 }}>
                    {val.toUpperCase()}
                </Tag>
            ),
        },
        {
            title: 'Host',
            dataIndex: 'host_name',
            key: 'host_name',
            width: 200,
            render: (name: string) => (
                <Text style={{ fontFamily: 'monospace', fontSize: 12, color: t.cyan, cursor: 'pointer' }}
                    onClick={() => setSelectedHost(name)}>
                    {name}
                </Text>
            ),
        },
        {
            title: 'Service',
            dataIndex: 'service',
            key: 'service',
            render: (s: string) => s || '—',
        },
        {
            title: 'Status',
            dataIndex: 'status',
            key: 'status',
            width: 120,
            render: (s: string) => statusTag(s),
        },
        {
            title: 'Output',
            dataIndex: 'output',
            key: 'output',
            ellipsis: true,
            render: (o: string) => (
                <Tooltip title={o}>
                    <Text style={{ color: t.muted, fontSize: 12 }}>{o}</Text>
                </Tooltip>
            ),
        },
        {
            title: 'Since',
            dataIndex: 'last_state_change',
            key: 'since',
            width: 140,
            render: (ts: number) => {
                if (!ts) return '—';
                const d = new Date(ts * 1000);
                const diff = Math.floor((Date.now() - d.getTime()) / 1000);
                if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
                if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
                return `${Math.floor(diff / 86400)}d ago`;
            },
        },
    ];

    // ── Host columns ──
    const hostColumns = [
        {
            title: 'Host',
            dataIndex: 'host_name',
            key: 'host_name',
            render: (name: string) => (
                <Text style={{ fontFamily: 'monospace', fontSize: 12, color: t.cyan, cursor: 'pointer' }}
                    onClick={() => setSelectedHost(name)}>
                    {name}
                </Text>
            ),
        },
        {
            title: 'Status',
            dataIndex: 'status_text',
            key: 'status',
            width: 100,
            render: (s: string) => statusTag(s),
        },
        {
            title: 'Output',
            dataIndex: 'plugin_output',
            key: 'output',
            ellipsis: true,
            render: (o: string) => <Text style={{ color: t.muted, fontSize: 12 }}>{o}</Text>,
        },
        {
            title: 'Last Check',
            dataIndex: 'last_check',
            key: 'last_check',
            width: 160,
            render: (ts: number) => ts ? new Date(ts * 1000).toLocaleString() : '—',
        },
    ];

    // ── Service columns (for filtered view and drawer) ──
    const serviceColumns = [
        {
            title: 'Host',
            dataIndex: 'host_name',
            key: 'host_name',
            width: 200,
            render: (name: string) => (
                <Text style={{ fontFamily: 'monospace', fontSize: 12, color: t.cyan, cursor: 'pointer' }}
                    onClick={() => setSelectedHost(name)}>
                    {name}
                </Text>
            ),
        },
        {
            title: 'Service',
            dataIndex: 'service_description',
            key: 'service',
            ellipsis: true,
        },
        {
            title: 'Status',
            dataIndex: 'status_text',
            key: 'status',
            width: 100,
            render: (s: string) => statusTag(s),
        },
        {
            title: 'Output',
            dataIndex: 'plugin_output',
            key: 'output',
            ellipsis: true,
            render: (o: string) => (
                <Tooltip title={o}>
                    <Text style={{ color: t.muted, fontSize: 11 }}>{o}</Text>
                </Tooltip>
            ),
        },
    ];

    // ── Drawer service columns (no host column) ──
    const drawerServiceColumns = [
        {
            title: 'Service',
            dataIndex: 'service_description',
            key: 'service',
            ellipsis: true,
        },
        {
            title: 'Status',
            dataIndex: 'status_text',
            key: 'status',
            width: 100,
            render: (s: string) => statusTag(s),
        },
        {
            title: 'Output',
            dataIndex: 'plugin_output',
            key: 'output',
            ellipsis: true,
            render: (o: string) => (
                <Tooltip title={o}>
                    <Text style={{ color: t.muted, fontSize: 11 }}>{o}</Text>
                </Tooltip>
            ),
        },
    ];

    return (
        <div style={{ padding: 28 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={3} style={{ color: t.text, margin: 0, fontWeight: 800 }}>
                        <AlertOutlined style={{ color: t.cyan, marginRight: 10 }} />
                        Monitoring Dashboard
                    </Title>
                    <Text style={{ color: t.muted, fontSize: 13 }}>
                        Real-time Nagios monitoring — {overview?.hosts?.total || 0} hosts, {overview?.services?.total || 0} services
                        {activeFilter && <span style={{ color: t.cyan, marginLeft: 8 }}>• Click a card again to clear filter</span>}
                    </Text>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    {activeFilter && (
                        <Button
                            onClick={() => setActiveFilter(null)}
                            style={{
                                background: 'rgba(248,113,113,0.1)',
                                border: '1px solid rgba(248,113,113,0.3)',
                                color: '#F87171',
                            }}
                        >
                            Clear Filter
                        </Button>
                    )}
                    <Button
                        icon={<PlusOutlined />}
                        onClick={() => setAddModalOpen(true)}
                        style={{
                            background: 'rgba(52,211,153,0.1)',
                            border: '1px solid rgba(52,211,153,0.3)',
                            color: '#34D399',
                        }}
                    >
                        Add Host
                    </Button>
                    <Button
                        icon={<ReloadOutlined />}
                        onClick={handleRefresh}
                        style={{
                            background: 'rgba(34,211,238,0.1)',
                            border: '1px solid rgba(34,211,238,0.3)',
                            color: t.cyan,
                        }}
                    >
                        Refresh
                    </Button>
                </div>
            </div>

            {/* Overview Cards */}
            {overviewLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
            ) : overview ? (
                <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
                    <StatCard label="Hosts UP" value={overview.hosts.up} color="#34D399"
                        icon={<CloudServerOutlined />}
                        isActive={activeFilter === 'hosts_up'}
                        onClick={() => handleCardClick('hosts_up')} />
                    <StatCard label="Hosts DOWN" value={overview.hosts.down} color="#F87171"
                        icon={<CloseCircleOutlined />}
                        isActive={activeFilter === 'hosts_down'}
                        onClick={() => handleCardClick('hosts_down')} />
                    <StatCard label="Services OK" value={overview.services.ok} color="#34D399"
                        icon={<CheckCircleOutlined />}
                        isActive={activeFilter === 'services_ok'}
                        onClick={() => handleCardClick('services_ok')} />
                    <StatCard label="Warning" value={overview.services.warning} color="#FBBF24"
                        icon={<WarningOutlined />}
                        isActive={activeFilter === 'services_warning'}
                        onClick={() => handleCardClick('services_warning')} />
                    <StatCard label="Critical" value={overview.services.critical} color="#F87171"
                        icon={<CloseCircleOutlined />}
                        isActive={activeFilter === 'services_critical'}
                        onClick={() => handleCardClick('services_critical')} />
                    <StatCard label="Unknown" value={overview.services.unknown} color="#94A3B8"
                        icon={<QuestionCircleOutlined />}
                        isActive={activeFilter === 'services_unknown'}
                        onClick={() => handleCardClick('services_unknown')} />
                </div>
            ) : null}

            {/* Table Header */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
                color: t.muted, fontSize: 13, fontWeight: 600,
            }}>
                {activeFilter ? (
                    <>
                        <FilterOutlined style={{ color: t.cyan }} />
                        <span>{filterConfig.title}</span>
                        <Tag style={{
                            marginLeft: 4,
                            background: 'rgba(34,211,238,0.1)',
                            border: '1px solid rgba(34,211,238,0.2)',
                            color: t.cyan,
                            fontSize: 11,
                        }}>
                            {filterConfig.data.length} items
                        </Tag>
                    </>
                ) : (
                    <>
                        <AlertOutlined style={{ color: '#F87171' }} />
                        <span>All Problems</span>
                        <Tag style={{
                            marginLeft: 4,
                            background: 'rgba(248,113,113,0.1)',
                            border: '1px solid rgba(248,113,113,0.2)',
                            color: '#F87171',
                            fontSize: 11,
                        }}>
                            {allProblems.length} items
                        </Tag>
                    </>
                )}
            </div>

            {/* Dynamic Table */}
            <Card style={tableCardStyle} styles={{ body: { padding: 0 } }}>
                {filterConfig.mode === 'hosts' && (
                    <Table
                        dataSource={filterConfig.data}
                        columns={hostColumns}
                        loading={hostsLoading}
                        rowKey="host_name"
                        size="small"
                        pagination={filterConfig.data.length > 25 ? { pageSize: 25, showSizeChanger: true } : false}
                        style={{ background: 'transparent' }}
                        rowClassName={(record: any) => record.status !== 0 ? 'nagios-row-critical' : ''}
                    />
                )}
                {filterConfig.mode === 'services' && (
                    <Table
                        dataSource={filterConfig.data}
                        columns={serviceColumns}
                        loading={servicesLoading}
                        rowKey={(r: any, i?: number) => `${r.host_name}-${r.service_description}-${i}`}
                        size="small"
                        pagination={{ pageSize: 25, showSizeChanger: true, showTotal: (total) => `${total} services` }}
                        style={{ background: 'transparent' }}
                        rowClassName={(record: any) =>
                            record.status === 2 ? 'nagios-row-critical'
                                : record.status === 1 ? 'nagios-row-warning' : ''
                        }
                    />
                )}
                {filterConfig.mode === 'problems' && (
                    <Table
                        dataSource={filterConfig.data}
                        columns={problemColumns}
                        loading={problemsLoading}
                        rowKey={(r: any, i?: number) => `${r.host_name}-${r.service || ''}-${i}`}
                        size="small"
                        pagination={{ pageSize: 25, showSizeChanger: true, showTotal: (total) => `${total} problems` }}
                        style={{ background: 'transparent' }}
                        rowClassName={(record: any) =>
                            record.status === 'CRITICAL' || record.status === 'DOWN'
                                ? 'nagios-row-critical'
                                : record.status === 'WARNING' ? 'nagios-row-warning' : ''
                        }
                    />
                )}
            </Card>

            {/* Host Services Drawer */}
            <Drawer
                title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <DesktopOutlined style={{ color: t.cyan }} />
                        <span style={{ color: t.text }}>{selectedHost}</span>
                    </div>
                }
                open={!!selectedHost}
                onClose={() => setSelectedHost(null)}
                width={700}
                styles={{
                    body: { padding: 16, background: t.bg },
                    header: { background: t.cardBg, borderBottom: `1px solid ${t.border}` },
                }}
                extra={
                    <Space>
                        <Button
                            icon={<EditOutlined />}
                            size="small"
                            onClick={openEditModal}
                            style={{
                                background: 'rgba(34,211,238,0.1)',
                                border: '1px solid rgba(34,211,238,0.3)',
                                color: t.cyan,
                            }}
                        >
                            Edit
                        </Button>
                        <Popconfirm
                            title="Delete this host?"
                            description={`This will remove ${selectedHost} from Nagios monitoring.`}
                            onConfirm={() => selectedHost && deleteMutation.mutate(selectedHost)}
                            okText="Delete"
                            okButtonProps={{ danger: true }}
                        >
                            <Button
                                icon={<DeleteOutlined />}
                                size="small"
                                loading={deleteMutation.isPending}
                                style={{
                                    background: 'rgba(248,113,113,0.1)',
                                    border: '1px solid rgba(248,113,113,0.3)',
                                    color: '#F87171',
                                }}
                            >
                                Delete
                            </Button>
                        </Popconfirm>
                    </Space>
                }
            >
                {hostServicesLoading ? (
                    <Spin style={{ display: 'block', margin: '40px auto' }} />
                ) : (
                    <Table
                        dataSource={hostServices}
                        columns={drawerServiceColumns}
                        rowKey="service_description"
                        size="small"
                        pagination={false}
                        rowClassName={(record: any) =>
                            record.status === 2 ? 'nagios-row-critical'
                                : record.status === 1 ? 'nagios-row-warning' : ''
                        }
                    />
                )}
            </Drawer>

            {/* Add Host Modal */}
            <Modal
                title={<><PlusOutlined style={{ color: '#34D399', marginRight: 8 }} />Add Host to Nagios</>}
                open={addModalOpen}
                onCancel={() => { setAddModalOpen(false); addForm.resetFields(); }}
                onOk={() => addForm.submit()}
                okText="Create Host"
                confirmLoading={createMutation.isPending}
                width={640}
                styles={{
                    body: { background: t.bg },
                    header: { background: t.cardBg, borderBottom: `1px solid ${t.border}` },
                }}
            >
                <Form
                    form={addForm}
                    layout="vertical"
                    initialValues={{ hostgroup: 'pbx', services: [{ description: 'PING', check_command: 'check_ping!100.0,20%!500.0,60%' }] }}
                    onFinish={(values: any) => {
                        createMutation.mutate({
                            hostname: values.hostname,
                            alias: values.alias,
                            address: values.address,
                            hostgroup: values.hostgroup,
                            services: values.services?.filter((s: ServiceFormItem) => s?.description && s?.check_command) || [],
                        });
                    }}
                >
                    <Form.Item name="hostname" label="Hostname" rules={[{ required: true, message: 'Enter hostname' }]}>
                        <Input placeholder="e.g. newserver.gsmcall.com" />
                    </Form.Item>
                    <Form.Item name="alias" label="Alias" rules={[{ required: true, message: 'Enter alias' }]}>
                        <Input placeholder="e.g. New Server" />
                    </Form.Item>
                    <Form.Item name="address" label="Address" rules={[{ required: true, message: 'Enter address' }]}>
                        <Input placeholder="IP address or DNS name" />
                    </Form.Item>
                    <Form.Item name="hostgroup" label="Host Group">
                        <Select options={[
                            { label: 'PBX Servers', value: 'pbx' },
                            { label: 'Endpoints', value: 'endpoint' },
                        ]} />
                    </Form.Item>
                    <div style={{ marginBottom: 8, fontWeight: 600, color: t.muted, fontSize: 13 }}>Service Checks</div>
                    <Form.List name="services">
                        {(fields, { add, remove }) => (
                            <>
                                {fields.map(({ key, name, ...rest }) => (
                                    <div key={key} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                                        <Form.Item {...rest} name={[name, 'description']} style={{ flex: 1, marginBottom: 0 }}>
                                            <Input placeholder="Service name" />
                                        </Form.Item>
                                        <Form.Item {...rest} name={[name, 'check_command']} style={{ flex: 2, marginBottom: 0 }}>
                                            <Input placeholder="Check command" />
                                        </Form.Item>
                                        <Button icon={<MinusCircleOutlined />} onClick={() => remove(name)} type="text" danger />
                                    </div>
                                ))}
                                <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />} style={{ color: t.muted }}>
                                    Add Service Check
                                </Button>
                            </>
                        )}
                    </Form.List>
                </Form>
            </Modal>

            {/* Edit Host Modal */}
            <Modal
                title={<><EditOutlined style={{ color: t.cyan, marginRight: 8 }} />Edit Host: {selectedHost}</>}
                open={editModalOpen}
                onCancel={() => { setEditModalOpen(false); editForm.resetFields(); }}
                onOk={() => editForm.submit()}
                okText="Save Changes"
                confirmLoading={updateMutation.isPending}
                width={640}
                styles={{
                    body: { background: t.bg },
                    header: { background: t.cardBg, borderBottom: `1px solid ${t.border}` },
                }}
            >
                <Form
                    form={editForm}
                    layout="vertical"
                    onFinish={(values: any) => {
                        if (!selectedHost) return;
                        updateMutation.mutate({
                            hostname: selectedHost,
                            data: {
                                alias: values.alias || undefined,
                                address: values.address || undefined,
                                hostgroup: values.hostgroup || undefined,
                                services: values.services?.filter((s: ServiceFormItem) => s?.description && s?.check_command) || undefined,
                            },
                        });
                    }}
                >
                    <Form.Item name="alias" label="Alias">
                        <Input placeholder="Host alias" />
                    </Form.Item>
                    <Form.Item name="address" label="Address">
                        <Input placeholder="IP address or DNS name" />
                    </Form.Item>
                    <Form.Item name="hostgroup" label="Host Group">
                        <Select options={[
                            { label: 'PBX Servers', value: 'pbx' },
                            { label: 'Endpoints', value: 'endpoint' },
                        ]} />
                    </Form.Item>
                    <div style={{ marginBottom: 8, fontWeight: 600, color: t.muted, fontSize: 13 }}>Service Checks</div>
                    <Form.List name="services">
                        {(fields, { add, remove }) => (
                            <>
                                {fields.map(({ key, name, ...rest }) => (
                                    <div key={key} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                                        <Form.Item {...rest} name={[name, 'description']} style={{ flex: 1, marginBottom: 0 }}>
                                            <Input placeholder="Service name" />
                                        </Form.Item>
                                        <Form.Item {...rest} name={[name, 'check_command']} style={{ flex: 2, marginBottom: 0 }}>
                                            <Input placeholder="Check command" />
                                        </Form.Item>
                                        <Button icon={<MinusCircleOutlined />} onClick={() => remove(name)} type="text" danger />
                                    </div>
                                ))}
                                <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />} style={{ color: t.muted }}>
                                    Add Service Check
                                </Button>
                            </>
                        )}
                    </Form.List>
                </Form>
            </Modal>
        </div>
    );
}
