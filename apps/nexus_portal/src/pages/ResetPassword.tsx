import { useState } from 'react';
import { Form, Input, Button, Typography, message, ConfigProvider } from 'antd';
import { LockOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { useThemeStore } from '../stores/themeStore';
import { getAntTheme, getTokens } from '../theme';
import NexusBrain from '../components/NexusBrain';

const { Title } = Typography;

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function ResetPassword() {
    const [loading, setLoading] = useState(false);
    const [done, setDone] = useState(false);
    const { token } = useParams<{ token: string }>();
    const navigate = useNavigate();
    const { mode } = useThemeStore();
    const t = getTokens(mode);

    const onFinish = async (values: any) => {
        if (values.password !== values.confirm) {
            message.error('Passwords do not match');
            return;
        }
        setLoading(true);
        try {
            await axios.post(`${API}/auth/reset-password`, {
                token,
                new_password: values.password,
            });
            setDone(true);
        } catch (err: any) {
            message.error(err.response?.data?.detail || 'Reset failed');
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
                        <span style={{ color: t.muted, fontSize: 13 }}>
                            {done ? 'Password Updated' : 'Set New Password'}
                        </span>
                    </div>

                    {/* ── Reset Form ──────────────── */}
                    {!done && (
                        <Form name="reset" onFinish={onFinish} layout="vertical" size="large">
                            <Form.Item name="password" rules={[
                                { required: true, message: 'Enter new password' },
                                { min: 8, message: 'Minimum 8 characters' },
                            ]}>
                                <Input.Password
                                    prefix={<LockOutlined style={{ color: t.muted }} />}
                                    placeholder="New password"
                                    style={{
                                        background: t.inputBg,
                                        borderColor: t.border,
                                        color: t.text,
                                        borderRadius: 10,
                                        height: 44,
                                    }}
                                />
                            </Form.Item>
                            <Form.Item name="confirm" rules={[
                                { required: true, message: 'Confirm your password' },
                            ]}>
                                <Input.Password
                                    prefix={<LockOutlined style={{ color: t.muted }} />}
                                    placeholder="Confirm new password"
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
                                    Reset Password
                                </Button>
                            </Form.Item>
                        </Form>
                    )}

                    {/* ── Success ──────────────── */}
                    {done && (
                        <div style={{ textAlign: 'center' }}>
                            <div style={{
                                width: 56, height: 56, borderRadius: '50%',
                                background: 'rgba(34,197,94,0.1)',
                                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                marginBottom: 16,
                            }}>
                                <CheckCircleOutlined style={{ fontSize: 24, color: '#22c55e' }} />
                            </div>
                            <Title level={4} style={{ color: t.text, margin: '0 0 8px' }}>
                                Password updated!
                            </Title>
                            <span style={{ color: t.muted, fontSize: 13, display: 'block', marginBottom: 24, lineHeight: '20px' }}>
                                Your password has been changed. You can now log in with your new credentials.
                            </span>
                            <Button
                                type="primary"
                                onClick={() => navigate('/login')}
                                style={{
                                    height: 40,
                                    borderRadius: 10,
                                    fontWeight: 600,
                                    paddingInline: 32,
                                }}
                            >
                                Go to Login
                            </Button>
                        </div>
                    )}
                </div>
            </div>
        </ConfigProvider>
    );
}
