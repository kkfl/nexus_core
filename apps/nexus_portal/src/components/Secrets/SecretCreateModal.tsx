import { Modal, Form, Input, Select, InputNumber, message, Upload, Button, Typography } from 'antd';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { useState } from 'react';
import { UploadOutlined, KeyOutlined, LockOutlined, ApiOutlined, SafetyCertificateOutlined } from '@ant-design/icons';

const { Text } = Typography;

const SECRET_TYPES = [
    { label: 'Password', value: 'password', icon: <LockOutlined /> },
    { label: 'API Key', value: 'api_key', icon: <ApiOutlined /> },
    { label: 'SSH Private Key', value: 'ssh_key', icon: <KeyOutlined /> },
    { label: 'Certificate / PEM', value: 'certificate', icon: <SafetyCertificateOutlined /> },
    { label: 'Other', value: 'other', icon: <LockOutlined /> },
];

const MULTILINE_TYPES = ['ssh_key', 'certificate'];

interface Props {
    open: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

export default function SecretCreateModal({ open, onClose, onSuccess }: Props) {
    const [form] = Form.useForm();
    const [secretType, setSecretType] = useState('password');

    const isMultiline = MULTILINE_TYPES.includes(secretType);

    const mutation = useMutation({
        mutationFn: (values: any) => apiClient.post('/portal/secrets', values),
        onSuccess: () => {
            message.success('Secret created successfully');
            form.resetFields();
            setSecretType('password');
            onSuccess();
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Failed to create secret');
        }
    });

    const handleOk = () => {
        form.validateFields().then(values => {
            // Strip the secret_type field — backend doesn't need it
            const { secret_type, ...rest } = values;
            mutation.mutate(rest);
        });
    };

    const handleCancel = () => {
        form.resetFields();
        setSecretType('password');
        onClose();
    };

    const handleFileUpload = (file: File) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const content = e.target?.result as string;
            form.setFieldValue('value', content);
        };
        reader.readAsText(file);
        return false; // Prevent default upload behavior
    };

    return (
        <Modal
            title="Add New Secret"
            open={open}
            onOk={handleOk}
            onCancel={handleCancel}
            confirmLoading={mutation.isPending}
            width={600}
        >
            <Form form={form} layout="vertical" initialValues={{ secret_type: 'password' }}>
                <Form.Item name="alias" label="Alias" rules={[{ required: true, message: 'Alias is required' }]}>
                    <Input placeholder={isMultiline ? 'e.g. pbx.dc1.ssh.key' : 'e.g. pbx.sip.password'} />
                </Form.Item>
                <Form.Item name="tenant_id" label="Tenant ID" rules={[{ required: true, message: 'Tenant ID is required' }]}>
                    <Input placeholder="e.g. AcmeCorp" />
                </Form.Item>
                <Form.Item name="env" label="Environment" rules={[{ required: true }]}>
                    <Select options={[
                        { label: 'Development', value: 'dev' },
                        { label: 'Staging', value: 'stage' },
                        { label: 'Production', value: 'prod' },
                    ]} />
                </Form.Item>
                <Form.Item name="secret_type" label="Secret Type">
                    <Select
                        options={SECRET_TYPES.map(t => ({ label: t.label, value: t.value }))}
                        onChange={(val) => {
                            setSecretType(val);
                            form.setFieldValue('value', '');
                        }}
                    />
                </Form.Item>
                <Form.Item
                    name="value"
                    label="Secret Value"
                    rules={[{ required: true }]}
                    extra={isMultiline ? (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                            Paste the full PEM content including -----BEGIN / -----END lines, or upload a file below.
                        </Text>
                    ) : undefined}
                >
                    {isMultiline ? (
                        <Input.TextArea
                            rows={8}
                            placeholder={secretType === 'ssh_key'
                                ? '-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----'
                                : '-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----'}
                            style={{ fontFamily: 'monospace', fontSize: 12 }}
                        />
                    ) : (
                        <Input.Password placeholder="Enter plaintext value" />
                    )}
                </Form.Item>
                {isMultiline && (
                    <Form.Item label="Or Upload File">
                        <Upload
                            accept=".pem,.key,.crt,.pub,.id_rsa,.id_ed25519"
                            beforeUpload={handleFileUpload}
                            showUploadList={false}
                            maxCount={1}
                        >
                            <Button icon={<UploadOutlined />}>
                                Upload {secretType === 'ssh_key' ? 'SSH Key' : 'Certificate'} File
                            </Button>
                        </Upload>
                    </Form.Item>
                )}
                <Form.Item name="description" label="Description">
                    <Input.TextArea rows={3} />
                </Form.Item>
                <Form.Item name="rotation_interval_days" label="Rotation Interval (Days)">
                    <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
            </Form>
        </Modal>
    );
}
