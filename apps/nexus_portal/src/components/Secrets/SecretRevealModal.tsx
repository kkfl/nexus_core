import { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Button, Alert, Space, Typography, message } from 'antd';
import { LockOutlined, WarningOutlined, EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';

const { Text, Title } = Typography;

interface Props {
    secret: any;
    open: boolean;
    onClose: () => void;
}

export default function SecretRevealModal({ secret, open, onClose }: Props) {
    const [step, setStep] = useState<'auth' | 'display'>('auth');
    const [revealedValue, setRevealedValue] = useState<string | null>(null);
    const [timeLeft, setTimeLeft] = useState(120);
    const [isMasked, setIsMasked] = useState(false);
    const [form] = Form.useForm();

    const revealMutation = useMutation({
        mutationFn: (values: any) => apiClient.post(`/portal/secrets/${secret.id}/reveal`, {
            ...values,
            tenant_id: secret.tenant_id,
            env: secret.env
        }),
        onSuccess: (resp) => {
            setRevealedValue(resp.data.value);
            setTimeLeft(resp.data.expires_in_seconds || 120);
            setStep('display');
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Re-authentication failed');
        }
    });

    const handleClose = useCallback(() => {
        setRevealedValue(null);
        setStep('auth');
        setTimeLeft(120);
        setIsMasked(false);
        form.resetFields();
        onClose();
    }, [form, onClose]);

    useEffect(() => {
        let timer: any;
        if (step === 'display' && timeLeft > 0) {
            timer = setInterval(() => {
                setTimeLeft((prev) => prev - 1);
            }, 1000);
        } else if (timeLeft === 0 && step === 'display') {
            setTimeout(() => {
                handleClose();
            }, 0);
        }
        return () => clearInterval(timer);
    }, [step, timeLeft, handleClose]);

    const handleAuthOk = () => {
        form.validateFields().then(values => {
            revealMutation.mutate(values);
        });
    };

    return (
        <Modal
            title={
                <span>
                    <LockOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
                    Break-Glass Reveal: {secret.alias}
                </span>
            }
            open={open}
            onCancel={handleClose}
            footer={step === 'auth' ? [
                <Button key="cancel" onClick={handleClose}>Cancel</Button>,
                <Button key="reveal" type="primary" danger loading={revealMutation.isPending} onClick={handleAuthOk}>
                    Confirm Reveal
                </Button>
            ] : [
                <Button key="close" onClick={handleClose}>Hide Now</Button>
            ]}
            maskClosable={false}
        >
            {step === 'auth' ? (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                    <Alert
                        message="Sensitive Action Required"
                        description="Revealing a secret is a break-glass action. It will be logged in the audit trail. Please re-authenticate."
                        type="error"
                        showIcon
                        icon={<WarningOutlined />}
                    />
                    <Form form={form} layout="vertical" autoComplete="off">
                        <Form.Item
                            name="password"
                            label="Re-authenticate with Password"
                            rules={[{ required: true }]}
                        >
                            <Input.Password prefix={<LockOutlined />} placeholder="Enter your password" autoComplete="new-password" />
                        </Form.Item>
                        <Form.Item
                            name="reason"
                            label="Reason for Reveal"
                            rules={[{ required: true, message: 'Reason is required for auditing' }]}
                        >
                            <Input.TextArea rows={2} placeholder="e.g. Debugging production connection issue" />
                        </Form.Item>
                    </Form>
                </Space>
            ) : (
                <Space direction="vertical" style={{ width: '100%', textAlign: 'center' }} size="large">
                    <div>
                        <Text type="secondary">This value will auto-hide in:</Text>
                        <div style={{ fontSize: 24, fontWeight: 'bold', color: timeLeft < 10 ? '#ff4d4f' : '#1890ff' }}>
                            {timeLeft}s
                        </div>
                    </div>

                    <div style={{ background: '#f5f5f5', padding: '16px 24px', borderRadius: '8px', border: '1px solid #d9d9d9', position: 'relative' }}>
                        <Button
                            type="text"
                            icon={isMasked ? <EyeOutlined /> : <EyeInvisibleOutlined />}
                            onClick={() => setIsMasked(!isMasked)}
                            style={{ position: 'absolute', right: 8, top: 8, zIndex: 1 }}
                        />
                        {isMasked ? (
                            <Title level={4} style={{ margin: 0, fontFamily: 'monospace', letterSpacing: 4 }}>
                                ••••••••••••••••
                            </Title>
                        ) : (
                            <pre style={{
                                margin: 0,
                                fontFamily: 'monospace',
                                fontSize: 13,
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-all',
                                maxHeight: 300,
                                overflowY: 'auto',
                                paddingRight: 32,
                            }}>
                                {revealedValue}
                            </pre>
                        )}
                    </div>

                    <Text type="secondary" italic>
                        Wait 120 seconds or click "Hide Now" to clear this value from memory.
                    </Text>
                </Space>
            )}
        </Modal>
    );
}
