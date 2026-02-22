import { useState } from 'react';
import { Form, Input, Button, Card, Typography, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { useAuthStore } from '../stores/authStore';

const { Title, Text } = Typography;

export default function Login() {
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();
    const setToken = useAuthStore((s) => s.setToken);

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
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#f0f2f5' }}>
            <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
                <div style={{ textAlign: 'center', marginBottom: 24 }}>
                    <Title level={2} style={{ margin: 0 }}>Nexus Portal</Title>
                    <Text type="secondary">System Administration Console</Text>
                </div>
                <Form name="login" onFinish={onFinish} layout="vertical" size="large">
                    <Form.Item name="username" rules={[{ required: true, message: 'Provide email' }]}>
                        <Input prefix={<UserOutlined />} placeholder="Email" />
                    </Form.Item>
                    <Form.Item name="password" rules={[{ required: true, message: 'Provide password' }]}>
                        <Input.Password prefix={<LockOutlined />} placeholder="Password" />
                    </Form.Item>
                    <Form.Item>
                        <Button type="primary" htmlType="submit" loading={loading} block>Log In</Button>
                    </Form.Item>
                </Form>
            </Card>
        </div>
    );
}
