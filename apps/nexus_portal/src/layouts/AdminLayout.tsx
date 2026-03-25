import { Layout, Menu, Button, Dropdown, Space, Typography, ConfigProvider, Tooltip } from 'antd';
import {
    DashboardOutlined,
    UserOutlined,
    SettingOutlined,
    ApiOutlined,
    DatabaseOutlined,
    BarsOutlined,
    CloudServerOutlined,
    RobotOutlined,
    ProfileOutlined,
    LogoutOutlined,
    ReadOutlined,
    KeyOutlined,
    IdcardOutlined,
    ControlOutlined,
    FileTextOutlined,
    SearchOutlined,
    AppstoreOutlined,
    SafetyOutlined,
    LineChartOutlined,
    AlertOutlined,
    HddOutlined,
    PhoneOutlined,
    MailOutlined,
    GlobalOutlined,
    QuestionCircleOutlined,
    TeamOutlined,
    SunOutlined,
    MoonOutlined,
    CloudDownloadOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore, hasModuleAccess } from '../stores/authStore';
import { useThemeStore } from '../stores/themeStore';
import { getAntTheme, getTokens } from '../theme';
import { useEffect, useMemo } from 'react';
import NexusBrain from '../components/NexusBrain';

const { Header, Content, Sider, Footer } = Layout;
const { Text } = Typography;

export default function AdminLayout() {
    const { user, logout } = useAuthStore();
    const { mode, toggleMode } = useThemeStore();
    const navigate = useNavigate();
    const location = useLocation();
    const t = getTokens(mode);

    // Sync data-theme attribute on mount
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', mode);
    }, [mode]);

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const navItems = useMemo(() => {
        const can = (module: string) => hasModuleAccess(user, module);
        const items: any[] = [
            { key: '/', icon: <DashboardOutlined />, label: 'Dashboard' },
        ];

        if (can('orchestration')) {
            items.push({
                key: 'orchestration',
                icon: <ApiOutlined />,
                label: 'Orchestration',
                children: [
                    { key: '/agents', label: 'Agents', icon: <RobotOutlined /> },
                    { key: '/routes', label: 'Task Routes', icon: <BarsOutlined /> },
                    { key: '/tasks', label: 'Tasks & Artifacts', icon: <ProfileOutlined /> },
                ],
            });
        }

        if (can('personas')) {
            items.push({
                key: 'personas',
                icon: <UserOutlined />,
                label: 'Personas',
                children: [
                    { key: '/personas', label: 'Persona Registry', icon: <IdcardOutlined /> },
                    { key: '/personas/defaults', label: 'Defaults & Overrides', icon: <ControlOutlined /> },
                ],
            });
        }

        if (can('knowledge_base')) {
            items.push({
                key: 'kb',
                icon: <DatabaseOutlined />,
                label: 'Knowledge Base',
                children: [
                    { key: '/kb/sources', label: 'Sources', icon: <FileTextOutlined /> },
                    { key: '/kb/documents', label: 'Documents', icon: <FileTextOutlined /> },
                    { key: '/kb/search', label: 'Search', icon: <SearchOutlined /> },
                    { key: '/kb/ask', label: 'Ask Nexus', icon: <QuestionCircleOutlined /> },
                ],
            });
        }

        // System of Record sub-items (entities, secrets, audit are separate modules)
        const sorChildren: any[] = [];
        if (can('entities')) sorChildren.push({ key: '/entities', label: 'Entities', icon: <AppstoreOutlined /> });
        if (can('secrets')) sorChildren.push({ key: '/secrets', label: 'Secrets / Credentials', icon: <KeyOutlined /> });
        if (can('audit')) sorChildren.push({ key: '/audits', label: 'Audit Trail', icon: <SafetyOutlined /> });
        if (sorChildren.length > 0) {
            items.push({
                key: 'sor',
                icon: <CloudServerOutlined />,
                label: 'System of Record',
                children: sorChildren,
            });
        }

        // Integrations sub-items
        const intChildren: any[] = [];
        if (can('pbx')) intChildren.push({ key: '/integrations/pbx', label: 'PBX Fleet Management', icon: <PhoneOutlined /> });
        if (can('monitoring')) intChildren.push({ key: '/integrations/monitoring', label: 'Monitoring Ingests', icon: <LineChartOutlined /> });
        if (can('storage')) intChildren.push({ key: '/integrations/storage', label: 'Storage Jobs', icon: <HddOutlined /> });
        if (can('carrier')) intChildren.push({ key: '/integrations/carrier', label: 'Carrier Inventory', icon: <PhoneOutlined /> });
        if (can('email')) intChildren.push({ key: '/integrations/email', label: 'Email Administration', icon: <MailOutlined /> });
        if (can('dns')) intChildren.push({ key: '/integrations/dns', label: 'DNS Management', icon: <GlobalOutlined /> });
        if (can('integrations')) intChildren.push({ key: '/integrations/services', label: 'Service Integrations', icon: <ApiOutlined /> });
        if (intChildren.length > 0) {
            items.push({
                key: 'integrations',
                icon: <SettingOutlined />,
                label: 'Integrations',
                children: intChildren,
            });
        }

        if (can('servers')) {
            items.push({
                key: 'infrastructure',
                icon: <CloudServerOutlined />,
                label: 'Infrastructure',
                children: [
                    { key: '/infrastructure/servers', label: 'Servers', icon: <CloudServerOutlined /> },
                ],
            });
        }

        if (can('monitoring')) {
            items.push({
                key: 'monitoring',
                icon: <AlertOutlined />,
                label: 'Monitoring',
                children: [
                    { key: '/monitoring/dashboard', label: 'Dashboard', icon: <LineChartOutlined /> },
                ],
            });
        }

        items.push({ key: '/docs', icon: <ReadOutlined />, label: 'Pilot Docs' });

        // Settings — only show items the user has access to
        const settingsChildren: any[] = [];
        if (can('users')) settingsChildren.push({ key: '/settings/users', label: 'User Management', icon: <TeamOutlined /> });
        if (can('api_keys')) settingsChildren.push({ key: '/settings/api-keys', label: 'API Keys', icon: <KeyOutlined /> });
        if (can('ip_allowlist')) settingsChildren.push({ key: '/settings/ip-allowlist', label: 'IP Allowlist', icon: <GlobalOutlined /> });
        if (can('audit')) settingsChildren.push({ key: '/settings/audit-log', label: 'Audit Log', icon: <SafetyOutlined /> });
        if (can('backup')) settingsChildren.push({ key: '/settings/backup', label: 'Backup & Restore', icon: <CloudDownloadOutlined /> });
        if (settingsChildren.length > 0) {
            items.push({
                key: 'settings',
                icon: <SettingOutlined />,
                label: 'Settings',
                children: settingsChildren,
            });
        }

        return items;
    }, [user]);

    return (
        <ConfigProvider theme={getAntTheme(mode)}>
            <Layout className="root-layout" style={{ minHeight: '100vh' }}>
                <Sider
                    width={260}
                    theme="dark"
                    style={{
                        overflow: 'auto',
                        height: '100vh',
                        position: 'fixed',
                        left: 0,
                        top: 0,
                        bottom: 0,
                        zIndex: 10,
                        background: t.siderBg,
                        borderRight: `1px solid ${t.border}`,
                    }}
                >
                    <div style={{
                        height: 64,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: 'rgba(0,0,0,0.2)',
                        borderBottom: `1px solid ${t.border}`,
                    }}>
                        <NexusBrain size={36} />
                        <span style={{
                            color: '#fff',
                            fontSize: 22,
                            fontWeight: 800,
                            letterSpacing: '3px',
                            background: `linear-gradient(135deg, #00CED1, #4169E1)`,
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent',
                            marginLeft: 10,
                            textTransform: 'uppercase' as const,
                        }}>
                            NEXUS
                        </span>
                    </div>
                    <Menu
                        theme="dark"
                        mode="inline"
                        selectedKeys={[location.pathname]}
                        defaultOpenKeys={['orchestration', 'personas', 'kb', 'sor', 'integrations']}
                        items={navItems}
                        onClick={(e) => navigate(e.key)}
                        style={{ background: 'transparent', borderRight: 0 }}
                    />
                </Sider>
                <Layout className="main-layout" style={{ marginLeft: 260, minHeight: '100vh', background: t.bg }}>
                    <Header style={{
                        padding: '0 28px',
                        background: t.headerBg,
                        display: 'flex',
                        justifyContent: 'flex-end',
                        alignItems: 'center',
                        borderBottom: `1px solid ${t.border}`,
                        position: 'sticky',
                        top: 0,
                        zIndex: 1,
                        width: '100%',
                        backdropFilter: 'blur(12px)',
                    }}>
                        <Space size="middle">
                            <Tooltip title={mode === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}>
                                <Button
                                    type="text"
                                    icon={mode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
                                    onClick={toggleMode}
                                    style={{
                                        color: t.muted,
                                        fontSize: 16,
                                        width: 36,
                                        height: 36,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        borderRadius: 8,
                                        border: `1px solid ${t.border}`,
                                        transition: 'all 0.2s ease',
                                    }}
                                />
                            </Tooltip>
                            <Text style={{ fontSize: 11, fontWeight: 600, color: t.muted, letterSpacing: 0.5 }}>
                                {user?.role.toUpperCase()}
                            </Text>
                            <Dropdown menu={{
                                items: [
                                    { key: 'email', label: <Text style={{ color: t.muted }}>{user?.email}</Text>, disabled: true },
                                    { type: 'divider' },
                                    { key: 'logout', label: 'Log Out', icon: <LogoutOutlined />, onClick: handleLogout }
                                ]
                            }} placement="bottomRight">
                                <Button
                                    type="text"
                                    icon={<UserOutlined />}
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        color: t.text,
                                        border: `1px solid ${t.border}`,
                                        borderRadius: 8,
                                        height: 36,
                                        gap: 6,
                                    }}
                                >
                                    {user?.email}
                                </Button>
                            </Dropdown>
                        </Space>
                    </Header>
                    <Content style={{
                        margin: 0,
                        padding: 0,
                        background: t.bg,
                        minHeight: 'calc(100vh - 64px - 52px)',
                    }}>
                        <Outlet />
                    </Content>
                    <Footer style={{
                        textAlign: 'center',
                        color: t.muted,
                        padding: '14px 50px',
                        background: 'transparent',
                        fontSize: 12,
                        borderTop: `1px solid ${t.border}`,
                    }}>
                        Nexus Portal v0.5.0 ©{new Date().getFullYear()} Created by Nexus Core • System of Record
                    </Footer>
                </Layout>
            </Layout>
        </ConfigProvider>
    );
}
