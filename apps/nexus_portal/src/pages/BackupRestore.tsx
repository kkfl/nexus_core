/**
 * Backup & Restore — Settings → Backup & Restore
 *
 * Admin-only page for managing database backups and performing
 * break-glass restores. Uses the Midnight design system.
 */

import React, { useState } from 'react';
import {
    Card, Button, Table, Typography, Space, Tag, message,
    Modal, Input, Alert, Progress, Statistic, Row, Col,
    Popconfirm, InputNumber, Tooltip, Empty, Select,
} from 'antd';
import {
    CloudDownloadOutlined, CloudUploadOutlined, DeleteOutlined,
    DownloadOutlined, ExclamationCircleOutlined, ReloadOutlined,
    SafetyCertificateOutlined, WarningOutlined, DatabaseOutlined,
    CheckCircleOutlined, ClockCircleOutlined, SettingOutlined,
    ThunderboltOutlined, FolderOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useThemeStore } from '../stores/themeStore';
import { getTokens, pageContainer } from '../theme';
import { apiClient } from '../api/client';

const { Title, Text, Paragraph } = Typography;

const api = {
    list: () => apiClient.get('/settings/backup/list').then(r => r.data),
    config: () => apiClient.get('/settings/backup/config').then(r => r.data),
    run: (subdirectory?: string) => apiClient.post('/settings/backup/run', { subdirectory }).then(r => r.data),
    del: (fn: string, location?: string) => apiClient.delete(`/settings/backup/${fn}`, { params: { location } }).then(r => r.data),
    restore: (fn: string, confirm: string) =>
        apiClient.post(`/settings/backup/restore/${fn}`, { confirm }).then(r => r.data),
    updateConfig: (data: any) =>
        apiClient.put('/settings/backup/config', data).then(r => r.data),
};

export default function BackupRestore() {
    const mode = useThemeStore(s => s.mode);
    const t = getTokens(mode);
    const qc = useQueryClient();

    const [restoreModal, setRestoreModal] = useState<string | null>(null);
    const [restoreConfirm, setRestoreConfirm] = useState('');
    const [restoreStep, setRestoreStep] = useState<'confirm' | 'running' | 'done' | 'error'>('confirm');
    const [restoreResult, setRestoreResult] = useState<any>(null);
    const [backupModal, setBackupModal] = useState(false);
    const [backupLocation, setBackupLocation] = useState<string>('default');
    const [newLocationName, setNewLocationName] = useState('');

    const { data: backups = [], isLoading } = useQuery({
        queryKey: ['backups'],
        queryFn: api.list,
        refetchInterval: 30000,
    });

    const { data: config } = useQuery({
        queryKey: ['backup-config'],
        queryFn: api.config,
    });

    const backupMutation = useMutation({
        mutationFn: (subdirectory?: string) => api.run(subdirectory),
        onSuccess: (data: any) => {
            if (data.success) {
                message.success(`Backup created: ${data.filename} (${data.size_human})${data.location !== 'default' ? ` → ${data.location}` : ''}`);
            } else {
                message.error(`Backup failed: ${data.error}`);
            }
            qc.invalidateQueries({ queryKey: ['backups'] });
            qc.invalidateQueries({ queryKey: ['backup-config'] });
            setBackupModal(false);
            setBackupLocation('default');
            setNewLocationName('');
        },
    });

    const deleteMutation = useMutation({
        mutationFn: ({ fn, location }: { fn: string; location?: string }) => api.del(fn, location),
        onSuccess: () => {
            message.success('Backup deleted');
            qc.invalidateQueries({ queryKey: ['backups'] });
            qc.invalidateQueries({ queryKey: ['backup-config'] });
        },
    });

    const configMutation = useMutation({
        mutationFn: api.updateConfig,
        onSuccess: () => {
            message.success('Configuration updated');
            qc.invalidateQueries({ queryKey: ['backup-config'] });
        },
    });

    const handleRestore = async () => {
        if (!restoreModal || restoreConfirm !== 'RESTORE') return;
        setRestoreStep('running');
        try {
            const result = await api.restore(restoreModal, 'RESTORE');
            setRestoreResult(result);
            setRestoreStep(result.success ? 'done' : 'error');
            if (result.success) {
                message.success('Database restored successfully');
            } else {
                message.error(`Restore failed: ${result.error}`);
            }
            qc.invalidateQueries({ queryKey: ['backups'] });
        } catch {
            setRestoreStep('error');
            setRestoreResult({ success: false, error: 'Network error' });
        }
    };

    const closeRestoreModal = () => {
        setRestoreModal(null);
        setRestoreConfirm('');
        setRestoreStep('confirm');
        setRestoreResult(null);
    };

    const cardStyle: React.CSSProperties = {
        background: 'linear-gradient(145deg, #111827, #0f1729)',
        border: '1px solid #1e293b',
        borderRadius: 12,
    };

    const triggerBackup = () => {
        const loc = backupLocation === '__new__' ? newLocationName : backupLocation;
        backupMutation.mutate(loc === 'default' ? undefined : loc);
    };

    const columns = [
        {
            title: 'Filename',
            dataIndex: 'filename',
            key: 'filename',
            render: (fn: string) => (
                <Space>
                    <DatabaseOutlined style={{ color: '#a78bfa' }} />
                    <Text style={{ color: '#e2e8f0', fontFamily: 'monospace', fontSize: 12 }}>{fn}</Text>
                </Space>
            ),
        },
        {
            title: 'Size',
            dataIndex: 'size_human',
            key: 'size',
            width: 100,
            render: (s: string) => <Text style={{ color: '#94a3b8' }}>{s}</Text>,
        },
        {
            title: 'Created',
            dataIndex: 'created_at',
            key: 'created',
            width: 160,
            render: (d: string) => (
                <Space size={4}>
                    <ClockCircleOutlined style={{ color: '#64748b' }} />
                    <Text style={{ color: '#94a3b8', fontSize: 12 }}>{d}</Text>
                </Space>
            ),
        },
        {
            title: 'Location',
            dataIndex: 'location',
            key: 'location',
            width: 120,
            render: (loc: string) => (
                <Tag
                    icon={<FolderOutlined />}
                    color={loc === 'default' ? 'default' : 'blue'}
                    style={{ fontSize: 11 }}
                >
                    {loc}
                </Tag>
            ),
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 200,
            render: (_: any, record: any) => (
                <Space size={8}>
                    <Tooltip title="Download">
                        <Button
                            type="text" size="small"
                            icon={<DownloadOutlined style={{ color: '#60a5fa' }} />}
                            onClick={async () => {
                                const token = localStorage.getItem('nexus_access_token') || '';
                                try {
                                    const resp = await fetch(`/api/settings/backup/download/${record.filename}?token=${token}&location=${record.location || ''}`);
                                    if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
                                    const blob = await resp.blob();
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = record.filename;
                                    document.body.appendChild(a);
                                    a.click();
                                    a.remove();
                                    URL.revokeObjectURL(url);
                                } catch (err: any) {
                                    message.error(err.message || 'Download failed');
                                }
                            }}
                        />
                    </Tooltip>
                    <Tooltip title="Restore from this backup">
                        <Button
                            type="text" size="small"
                            icon={<CloudUploadOutlined style={{ color: '#f59e0b' }} />}
                            onClick={() => setRestoreModal(record.filename)}
                        />
                    </Tooltip>
                    <Popconfirm
                        title="Delete this backup?"
                        onConfirm={() => deleteMutation.mutate({ fn: record.filename, location: record.location })}
                        okText="Delete" cancelText="Cancel"
                    >
                        <Tooltip title="Delete">
                            <Button
                                type="text" size="small" danger
                                icon={<DeleteOutlined />}
                            />
                        </Tooltip>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div style={pageContainer(t)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={3} style={{ margin: 0, color: '#e2e8f0' }}>
                        <SafetyCertificateOutlined style={{ marginRight: 10, color: '#a78bfa' }} />
                        Backup & Restore
                    </Title>
                    <Text style={{ color: '#64748b', fontSize: 12 }}>
                        Manage database backups and restore from previous snapshots
                    </Text>
                </div>
                <Space>
                    <Button
                        icon={<ReloadOutlined />}
                        onClick={() => qc.invalidateQueries({ queryKey: ['backups'] })}
                    >
                        Refresh
                    </Button>
                    <Button
                        type="primary"
                        icon={<CloudDownloadOutlined />}
                        loading={backupMutation.isPending}
                        onClick={() => setBackupModal(true)}
                        style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}
                    >
                        Backup Now
                    </Button>
                </Space>
            </div>

            {/* Summary Cards */}
            <Row gutter={[20, 20]} style={{ marginBottom: 24 }}>
                <Col xs={24} sm={8}>
                    <Card size="small" style={cardStyle}>
                        <Statistic
                            title={<Text style={{ color: '#94a3b8' }}>Total Backups</Text>}
                            value={config?.backup_count || 0}
                            prefix={<DatabaseOutlined />}
                            valueStyle={{ color: '#a78bfa' }}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={8}>
                    <Card size="small" style={cardStyle}>
                        <Statistic
                            title={<Text style={{ color: '#94a3b8' }}>Max Retention</Text>}
                            value={config?.max_backups || 10}
                            suffix="backups"
                            prefix={<SettingOutlined />}
                            valueStyle={{ color: '#60a5fa' }}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={8}>
                    <Card size="small" style={cardStyle}>
                        <Statistic
                            title={<Text style={{ color: '#94a3b8' }}>Latest Backup</Text>}
                            value={backups.length > 0 ? backups[0].created_at : 'None'}
                            prefix={<ClockCircleOutlined />}
                            valueStyle={{ color: '#4ade80', fontSize: 16 }}
                        />
                    </Card>
                </Col>
            </Row>

            {/* Backups Table */}
            <Card style={{ ...cardStyle, marginBottom: 24 }} title={
                <span style={{ color: '#e2e8f0' }}>
                    <DatabaseOutlined style={{ marginRight: 8 }} />Available Backups
                </span>
            }>
                <Table
                    dataSource={backups}
                    columns={columns}
                    rowKey="filename"
                    loading={isLoading}
                    size="middle"
                    pagination={false}
                    locale={{
                        emptyText: (
                            <Empty
                                image={Empty.PRESENTED_IMAGE_SIMPLE}
                                description={<span style={{ color: '#475569' }}>No backups yet. Click "Backup Now" to create your first backup.</span>}
                            />
                        )
                    }}
                />
            </Card>

            {/* Configuration */}
            <Card style={cardStyle} title={
                <span style={{ color: '#e2e8f0' }}>
                    <SettingOutlined style={{ marginRight: 8 }} />Configuration
                </span>
            }>
                <Row gutter={[16, 16]}>
                    <Col span={24}>
                        <div style={{ padding: '12px 16px', background: '#0d1117', borderRadius: 8, border: '1px solid #1e293b' }}>
                            <Text style={{ color: '#94a3b8', fontSize: 12, display: 'block', marginBottom: 8 }}>
                                BACKUP DIRECTORY (HOST PATH)
                            </Text>
                            <Input.Search
                                defaultValue={config?.backup_host_dir || './backups'}
                                key={config?.backup_host_dir}
                                enterButton="Save"
                                placeholder="e.g. ./backups, S:/Nexus_Backups, /mnt/nas/backups"
                                onSearch={(value) => {
                                    if (!value.trim()) return;
                                    apiClient.put('/settings/backup/config/backup-dir', { backup_host_dir: value.trim() })
                                        .then(() => {
                                            message.success('Backup directory saved! Restart the nexus-api container to apply.');
                                            qc.invalidateQueries({ queryKey: ['backup-config'] });
                                        })
                                        .catch((err: any) => message.error(err.response?.data?.detail || 'Failed to save'));
                                }}
                                style={{ maxWidth: 500 }}
                                styles={{
                                    input: { background: '#161d2e', borderColor: '#1e293b', color: '#4ade80', fontFamily: 'monospace', fontSize: 14 },
                                }}
                            />
                            <Text style={{ color: '#475569', fontSize: 11, display: 'block', marginTop: 6 }}>
                                Use any local or network path (e.g. S:/ for Synology NAS). Changes require a container restart.
                            </Text>
                        </div>
                    </Col>
                    {config?.pending_restart && (
                        <Col span={24}>
                            <Alert
                                type="warning"
                                showIcon
                                message="Container restart required"
                                description={
                                    <div style={{ fontSize: 12 }}>
                                        <p style={{ margin: '4px 0' }}>
                                            The backup directory has been changed. Run this command to apply:
                                        </p>
                                        <code style={{ display: 'block', margin: '8px 0', padding: '6px 10px', background: '#0d1117', borderRadius: 4, color: '#f59e0b', cursor: 'pointer' }}
                                            onClick={() => { navigator.clipboard.writeText('docker compose up -d --build nexus-api'); message.success('Copied!'); }}
                                        >
                                            docker compose up -d --build nexus-api  📋
                                        </code>
                                    </div>
                                }
                                style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)' }}
                            />
                        </Col>
                    )}
                    <Col span={24}>
                        <Row gutter={16} align="middle" style={{ marginBottom: 16 }}>
                            <Col>
                                <Text style={{ color: '#94a3b8' }}>Default backup location:</Text>
                            </Col>
                            <Col>
                                <Select
                                    value={config?.default_location || 'default'}
                                    onChange={(val) => configMutation.mutate({ default_location: val })}
                                    style={{ width: 200, background: '#161d2e' }}
                                    options={[
                                        { value: 'default', label: '📁 default (root)' },
                                        ...(config?.locations || []).filter((l: string) => l !== 'default').map((l: string) => ({
                                            value: l,
                                            label: `📂 ${l}`,
                                        })),
                                    ]}
                                />
                            </Col>
                            <Col>
                                <Text style={{ color: '#475569', fontSize: 12 }}>
                                    New backups will be saved to this location by default
                                </Text>
                            </Col>
                        </Row>
                    </Col>
                    <Col span={24}>
                        <Row gutter={16} align="middle">
                            <Col>
                                <Text style={{ color: '#94a3b8' }}>Max backups to retain:</Text>
                            </Col>
                            <Col>
                                <InputNumber
                                    min={1} max={100}
                                    value={config?.max_backups || 10}
                                    onChange={(val) => { if (val) configMutation.mutate({ max_backups: val }); }}
                                    style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0', width: 80 }}
                                />
                            </Col>
                            <Col>
                                <Text style={{ color: '#475569', fontSize: 12 }}>
                                    Oldest backups are automatically deleted when this limit is exceeded
                                </Text>
                            </Col>
                        </Row>
                    </Col>
                </Row>
            </Card>

            {/* Backup Now Modal — location picker */}
            <Modal
                title={
                    <span style={{ color: '#e2e8f0' }}>
                        <CloudDownloadOutlined style={{ marginRight: 8, color: '#a78bfa' }} />
                        Create Backup
                    </span>
                }
                open={backupModal}
                onCancel={() => { setBackupModal(false); setBackupLocation('default'); setNewLocationName(''); }}
                footer={[
                    <Button key="cancel" onClick={() => { setBackupModal(false); setBackupLocation('default'); setNewLocationName(''); }}>
                        Cancel
                    </Button>,
                    <Button
                        key="backup" type="primary"
                        loading={backupMutation.isPending}
                        onClick={triggerBackup}
                        icon={<CloudDownloadOutlined />}
                        disabled={backupLocation === '__new__' && !newLocationName.trim()}
                        style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}
                    >
                        Start Backup
                    </Button>,
                ]}
                width={480}
                styles={{
                    header: { background: '#111827', borderBottom: '1px solid #1e293b' },
                    body: { background: '#111827' },
                    footer: { background: '#111827', borderTop: '1px solid #1e293b' },
                }}
            >
                <div style={{ marginBottom: 16 }}>
                    <Text style={{ color: '#94a3b8', display: 'block', marginBottom: 8 }}>
                        <FolderOutlined style={{ marginRight: 6 }} />
                        Save backup to:
                    </Text>
                    <Select
                        value={backupLocation}
                        onChange={setBackupLocation}
                        style={{ width: '100%' }}
                        options={[
                            { value: 'default', label: '📁 default (root backup directory)' },
                            ...(config?.locations || []).filter((l: string) => l !== 'default').map((l: string) => ({
                                value: l,
                                label: `📂 ${l}`,
                            })),
                            { value: '__new__', label: '➕ Create new location...' },
                        ]}
                    />
                </div>
                {backupLocation === '__new__' && (
                    <div style={{ marginBottom: 16 }}>
                        <Text style={{ color: '#94a3b8', display: 'block', marginBottom: 4, fontSize: 12 }}>
                            New location name:
                        </Text>
                        <Input
                            placeholder="e.g. weekly, synology-nas, archive"
                            value={newLocationName}
                            onChange={(e) => setNewLocationName(e.target.value)}
                            style={{ background: '#161d2e', borderColor: '#1e293b', color: '#e2e8f0' }}
                        />
                        <Text style={{ color: '#475569', fontSize: 11, display: 'block', marginTop: 4 }}>
                            Creates a subdirectory under {config?.backup_host_dir || './backups'}
                        </Text>
                    </div>
                )}
                <Alert
                    type="info" showIcon
                    message="A full database dump (pg_dump) will be created and gzipped."
                    style={{ background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)' }}
                />
            </Modal>

            {/* Restore Break-Glass Modal */}
            <Modal
                title={
                    <span style={{ color: '#f87171' }}>
                        <ExclamationCircleOutlined style={{ marginRight: 8, color: '#ef4444' }} />
                        Restore Database — BREAK GLASS
                    </span>
                }
                open={!!restoreModal}
                onCancel={closeRestoreModal}
                footer={restoreStep === 'confirm' ? [
                    <Button key="cancel" onClick={closeRestoreModal}>Cancel</Button>,
                    <Button
                        key="restore" danger type="primary"
                        disabled={restoreConfirm !== 'RESTORE'}
                        onClick={handleRestore}
                        icon={<ThunderboltOutlined />}
                    >
                        Execute Restore
                    </Button>,
                ] : [
                    <Button key="close" onClick={closeRestoreModal}>
                        {restoreStep === 'running' ? 'Please wait...' : 'Close'}
                    </Button>,
                ]}
                width={550}
                styles={{
                    header: { background: '#1a0a0a', borderBottom: '1px solid #7f1d1d' },
                    body: { background: '#111827' },
                    footer: { background: '#111827', borderTop: '1px solid #1e293b' },
                }}
            >
                {restoreStep === 'confirm' && (
                    <div>
                        <Alert
                            type="error"
                            showIcon
                            icon={<WarningOutlined />}
                            message="This action will overwrite ALL current data"
                            description={
                                <div>
                                    <p>Restoring from <strong style={{ color: '#f87171' }}>{restoreModal}</strong> will:</p>
                                    <ul style={{ color: '#94a3b8', paddingLeft: 20 }}>
                                        <li>Create a safety backup of the current database first</li>
                                        <li>Drop and recreate all tables with the backup data</li>
                                        <li>Overwrite all secrets, entities, audit trails, and configurations</li>
                                    </ul>
                                    <p style={{ marginTop: 12, fontWeight: 600, color: '#f87171' }}>
                                        Type <code>RESTORE</code> below to confirm:
                                    </p>
                                </div>
                            }
                            style={{ marginBottom: 16, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)' }}
                        />
                        <Input
                            placeholder="Type RESTORE to confirm"
                            value={restoreConfirm}
                            onChange={(e) => setRestoreConfirm(e.target.value)}
                            style={{
                                background: '#161d2e', borderColor: restoreConfirm === 'RESTORE' ? '#22c55e' : '#7f1d1d',
                                color: '#e2e8f0', fontFamily: 'monospace', fontSize: 16, textAlign: 'center',
                            }}
                            status={restoreConfirm.length > 0 && restoreConfirm !== 'RESTORE' ? 'error' : undefined}
                        />
                    </div>
                )}

                {restoreStep === 'running' && (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                        <Progress type="circle" percent={-1} status="active" size={80} />
                        <div style={{ marginTop: 16, color: '#94a3b8' }}>
                            Restoring database... Do not close this window.
                        </div>
                    </div>
                )}

                {restoreStep === 'done' && restoreResult && (
                    <div style={{ textAlign: 'center', padding: '20px 0' }}>
                        <CheckCircleOutlined style={{ fontSize: 48, color: '#22c55e', marginBottom: 16 }} />
                        <Title level={4} style={{ color: '#4ade80' }}>Restore Complete</Title>
                        <Paragraph style={{ color: '#94a3b8' }}>
                            Database restored from <strong>{restoreResult.backup_used}</strong>
                        </Paragraph>
                        {restoreResult.safety_backup && (
                            <Tag color="blue">Safety backup: {restoreResult.safety_backup}</Tag>
                        )}
                    </div>
                )}

                {restoreStep === 'error' && restoreResult && (
                    <div style={{ textAlign: 'center', padding: '20px 0' }}>
                        <ExclamationCircleOutlined style={{ fontSize: 48, color: '#ef4444', marginBottom: 16 }} />
                        <Title level={4} style={{ color: '#f87171' }}>Restore Failed</Title>
                        <Paragraph style={{ color: '#94a3b8' }}>
                            {restoreResult.error}
                        </Paragraph>
                        {restoreResult.safety_backup && (
                            <Alert type="info" message={`Your data is safe — a safety backup was created: ${restoreResult.safety_backup}`} />
                        )}
                    </div>
                )}
            </Modal>
        </div>
    );
}
