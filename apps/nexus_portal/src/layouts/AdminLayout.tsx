import { Layout, Menu, Button, Dropdown, Space, Typography, ConfigProvider, theme } from 'antd';
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
    CameraOutlined,
    LineChartOutlined,
    HddOutlined,
    PhoneOutlined,
    MailOutlined,
    GlobalOutlined,
    QuestionCircleOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';

const { Header, Content, Sider, Footer } = Layout;
const { Text } = Typography;

export default function AdminLayout() {
    const { user, logout } = useAuthStore();
    const navigate = useNavigate();
    const location = useLocation();

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const navItems = [
        {
            key: '/',
            icon: <DashboardOutlined />,
            label: 'Dashboard',
        },
        {
            key: 'orchestration',
            icon: <ApiOutlined />,
            label: 'Orchestration',
            children: [
                { key: '/agents', label: 'Agents', icon: <RobotOutlined /> },
                { key: '/routes', label: 'Task Routes', icon: <BarsOutlined /> },
                { key: '/tasks', label: 'Tasks & Artifacts', icon: <ProfileOutlined /> },
            ],
        },
        {
            key: 'personas',
            icon: <UserOutlined />,
            label: 'Personas',
            children: [
                { key: '/personas', label: 'Persona Registry', icon: <IdcardOutlined /> },
                { key: '/personas/defaults', label: 'Defaults & Overrides', icon: <ControlOutlined /> },
            ],
        },
        {
            key: 'kb',
            icon: <DatabaseOutlined />,
            label: 'Knowledge Base',
            children: [
                { key: '/kb/sources', label: 'Sources', icon: <FileTextOutlined /> },
                { key: '/kb/documents', label: 'Documents', icon: <FileTextOutlined /> },
                { key: '/kb/search', label: 'Search', icon: <SearchOutlined /> },
                { key: '/kb/ask', label: 'Ask Nexus', icon: <QuestionCircleOutlined /> },
            ],
        },
        {
            key: 'sor',
            icon: <CloudServerOutlined />,
            label: 'System of Record',
            children: [
                { key: '/entities', label: 'Entities', icon: <AppstoreOutlined /> },
                { key: '/secrets', label: 'Secrets / Credentials', icon: <KeyOutlined /> },
                { key: '/audits', label: 'Audit Trail', icon: <SafetyOutlined /> },
            ],
        },
        {
            key: 'integrations',
            icon: <SettingOutlined />,
            label: 'Integrations',
            children: [
                { key: '/integrations/pbx', label: 'PBX Snapshots', icon: <CameraOutlined /> },
                { key: '/integrations/monitoring', label: 'Monitoring Ingests', icon: <LineChartOutlined /> },
                { key: '/integrations/storage', label: 'Storage Jobs', icon: <HddOutlined /> },
                { key: '/integrations/carrier', label: 'Carrier Inventory', icon: <PhoneOutlined /> },
                { key: '/integrations/email', label: 'Email Administration', icon: <MailOutlined /> },
                { key: '/integrations/dns', label: 'DNS Management', icon: <GlobalOutlined /> },
            ],
        },
        {
            key: '/docs',
            icon: <ReadOutlined />,
            label: 'Pilot Docs',
        },
    ];

    return (
        <ConfigProvider
            theme={{
                algorithm: theme.defaultAlgorithm,
                token: {
                    colorPrimary: '#1677ff',
                    borderRadius: 8,
                    fontFamily: 'Inter, system-ui, sans-serif',
                },
            }}
        >
            <Layout className="root-layout" style={{ minHeight: '100vh' }}>
                <Sider width={260} theme="dark" style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, top: 0, bottom: 0, zIndex: 10 }}>
                    <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#001529', color: '#fff', fontSize: 20, fontWeight: 700, letterSpacing: '-0.5px' }}>
                        Nexus Core
                    </div>
                    <Menu
                        theme="dark"
                        mode="inline"
                        selectedKeys={[location.pathname]}
                        defaultOpenKeys={['orchestration', 'personas', 'kb', 'sor', 'integrations']}
                        items={navItems}
                        onClick={(e) => navigate(e.key)}
                    />
                </Sider>
                <Layout className="main-layout" style={{ marginLeft: 260, minHeight: '100vh' }}>
                    <Header style={{ padding: '0 32px', background: '#fff', display: 'flex', justifyContent: 'flex-end', alignItems: 'center', borderBottom: '1px solid #f0f0f0', position: 'sticky', top: 0, zIndex: 1, width: '100%' }}>
                        <Space size="large">
                            <Text type="secondary" style={{ fontSize: '12px', fontWeight: 600 }}>{user?.role.toUpperCase()}</Text>
                            <Dropdown menu={{
                                items: [
                                    { key: 'email', label: <Text disabled>{user?.email}</Text> },
                                    { type: 'divider' },
                                    { key: 'logout', label: 'Log Out', icon: <LogoutOutlined />, onClick: handleLogout }
                                ]
                            }} placement="bottomRight">
                                <Button type="text" icon={<UserOutlined />} style={{ display: 'flex', alignItems: 'center' }}>
                                    {user?.email}
                                </Button>
                            </Dropdown>
                        </Space>
                    </Header>
                    <Content style={{ margin: '24px', padding: '32px', background: '#fff', borderRadius: 12 }}>
                        <Outlet />
                    </Content>
                    <Footer style={{ textAlign: 'center', color: '#8c8c8c', padding: '16px 50px' }}>
                        Nexus Portal v{import.meta.env.VITE_APP_VERSION || '0.1.0'} ©{new Date().getFullYear()} Created by Nexus Core • System of Record
                    </Footer>
                </Layout>
            </Layout>
        </ConfigProvider>
    );
}
