import { useState } from 'react';
import { Form, Input, Button, Typography, message, ConfigProvider } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { useAuthStore } from '../stores/authStore';
import { useThemeStore } from '../stores/themeStore';
import { getAntTheme, getTokens } from '../theme';
import NexusBrain from '../components/NexusBrain';

const { Title, Text } = Typography;

export default function Login() {
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();
    const setToken = useAuthStore((s) => s.setToken);
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const from = location.state?.from?.pathname || '/';

    const onFinish = async (values: any) => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            params.append('username', values.username);
            params.append('password', values.password);

            const res = await axios.post(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/auth/login`, params, {
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
            });

            setToken(res.data.access_token);
            message.success('Logged in successfully');
            navigate(from, { replace: true });
        } catch (err: any) {
            console.error(err);
            message.error(err.response?.data?.detail || 'Login failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <ConfigProvider theme={getAntTheme(mode)}>
            <div style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100vh',
                background: t.bg,
            }}>
                <div style={{
                    width: 400,
                    padding: 40,
                    borderRadius: 16,
                    background: t.cardBg,
                    border: `1px solid ${t.border}`,
                    boxShadow: mode === 'dark'
                        ? `0 0 40px rgba(59,130,246,0.08), 0 20px 60px rgba(0,0,0,0.4)`
                        : '0 4px 24px rgba(0,0,0,0.08)',
                }}>
                    <div style={{ textAlign: 'center', marginBottom: 32 }}>
                        <div style={{ marginBottom: 16 }}>
                            <NexusBrain size={80} />
                        </div>
                        <Title level={2} style={{
                            margin: 0,
                            color: t.text,
                            background: mode === 'dark'
                                ? `linear-gradient(135deg, ${t.accent}, ${t.cyan})`
                                : undefined,
                            WebkitBackgroundClip: mode === 'dark' ? 'text' : undefined,
                            WebkitTextFillColor: mode === 'dark' ? 'transparent' : undefined,
                        }}>
                            Nexus Portal
                        </Title>
                        <Text style={{ color: t.muted, fontSize: 13 }}>System Administration Console</Text>
                    </div>
                    <Form name="login" onFinish={onFinish} layout="vertical" size="large">
                        <Form.Item name="username" rules={[{ required: true, message: 'Provide email' }]}>
                            <Input
                                prefix={<UserOutlined style={{ color: t.muted }} />}
                                placeholder="Email"
                                style={{
                                    background: t.inputBg,
                                    borderColor: t.border,
                                    color: t.text,
                                    borderRadius: 10,
                                    height: 44,
                                }}
                            />
                        </Form.Item>
                        <Form.Item name="password" rules={[{ required: true, message: 'Provide password' }]}>
                            <Input.Password
                                prefix={<LockOutlined style={{ color: t.muted }} />}
                                placeholder="Password"
                                style={{
                                    background: t.inputBg,
                                    borderColor: t.border,
                                    color: t.text,
                                    borderRadius: 10,
                                    height: 44,
                                }}
                            />
                        </Form.Item>
                        <Form.Item style={{ marginBottom: 0 }}>
                            <Button
                                type="primary"
                                htmlType="submit"
                                loading={loading}
                                block
                                style={{
                                    height: 44,
                                    borderRadius: 10,
                                    fontWeight: 600,
                                    fontSize: 14,
                                }}
                            >
                                Log In
                            </Button>
                        </Form.Item>
                    </Form>
                </div>
            </div>
        </ConfigProvider>
    );
}
