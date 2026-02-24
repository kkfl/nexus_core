import { Layout, Menu, Button, Dropdown, Space, Typography } from 'antd';
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
                { key: '/personas', label: 'Persona Registry' },
                { key: '/personas/defaults', label: 'Defaults & Overrides' },
            ],
        },
        {
            key: 'kb',
            icon: <DatabaseOutlined />,
            label: 'Knowledge Base',
            children: [
                { key: '/kb/sources', label: 'Sources ' },
                { key: '/kb/documents', label: 'Documents' },
                { key: '/kb/search', label: 'Search' },
            ],
        },
        {
            key: 'sor',
            icon: <CloudServerOutlined />,
            label: 'System of Record',
            children: [
                { key: '/entities', label: 'Entities' },
                { key: '/secrets', label: 'Secrets / Credentials', icon: <KeyOutlined /> },
                { key: '/audits', label: 'Audit Trail' },
            ],
        },
        {
            key: 'integrations',
            icon: <SettingOutlined />,
            label: 'Integrations',
            children: [
                { key: '/integrations/pbx', label: 'PBX Snapshots' },
                { key: '/integrations/monitoring', label: 'Monitoring Ingests' },
                { key: '/integrations/storage', label: 'Storage Jobs' },
                { key: '/integrations/carrier', label: 'Carrier Inventory' },
            ],
        },
        {
            key: '/docs',
            icon: <ReadOutlined />,
            label: 'Pilot Docs',
        },
    ];

    return (
        <Layout style={{ minHeight: '100vh' }}>
            <Sider width={250} theme="dark">
                <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#001529', color: '#fff', fontSize: 20, fontWeight: 'bold' }}>
                    Nexus Portal
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
            <Layout>
                <Header style={{ padding: '0 24px', background: '#fff', display: 'flex', justifyContent: 'flex-end', alignItems: 'center', borderBottom: '1px solid #f0f0f0' }}>
                    <Space size="large">
                        <Text type="secondary">{user?.role.toUpperCase()}</Text>
                        <Dropdown menu={{
                            items: [
                                { key: 'email', label: <Text disabled>{user?.email}</Text> },
                                { type: 'divider' },
                                { key: 'logout', label: 'Log Out', icon: <LogoutOutlined />, onClick: handleLogout }
                            ]
                        }} placement="bottomRight">
                            <Button type="text" icon={<UserOutlined />}>
                                {user?.email}
                            </Button>
                        </Dropdown>
                    </Space>
                </Header>
                <Content style={{ margin: '24px 16px', padding: 24, background: '#fff', minHeight: 280, borderRadius: 8 }}>
                    <Outlet />
                </Content>
                <Footer style={{ textAlign: 'center' }}>
                    Nexus Portal v{import.meta.env.VITE_APP_VERSION || '0.1.0'} ©{new Date().getFullYear()} Created by Nexus Core
                </Footer>
            </Layout>
        </Layout>
    );
}
