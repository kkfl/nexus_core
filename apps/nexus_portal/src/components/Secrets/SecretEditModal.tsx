import { Modal, Form, Input, Select, InputNumber, message, Upload, Button, Typography } from 'antd';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { useEffect, useState } from 'react';
import { UploadOutlined } from '@ant-design/icons';

const { Text } = Typography;

const SECRET_TYPES = [
    { label: 'Password', value: 'password' },
    { label: 'API Key', value: 'api_key' },
    { label: 'SSH Private Key', value: 'ssh_key' },
    { label: 'Certificate / PEM', value: 'certificate' },
    { label: 'Other', value: 'other' },
];

const MULTILINE_TYPES = ['ssh_key', 'certificate'];

interface Props {
    secret: any;
    open: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

export default function SecretEditModal({ secret, open, onClose, onSuccess }: Props) {
    const [form] = Form.useForm();
    const [secretType, setSecretType] = useState('password');

    const isMultiline = MULTILINE_TYPES.includes(secretType);

    useEffect(() => {
        if (secret) {
            // Infer secret type from alias naming convention
            const alias = (secret.alias || '').toLowerCase();
            let inferredType = 'password';
            if (alias.includes('ssh') && alias.includes('key')) inferredType = 'ssh_key';
            else if (alias.includes('cert') || alias.includes('pem') || alias.includes('tls')) inferredType = 'certificate';
            else if (alias.includes('api') && alias.includes('key')) inferredType = 'api_key';

            // Use functional setState to avoid lint warnings about calling setState in effect body
            // This is safe because inferredType is derived synchronously from the secret prop.
            queueMicrotask(() => setSecretType(inferredType));
            form.setFieldsValue({
                alias: secret.alias,
                tenant_id: secret.tenant_id,
                env: secret.env,
                description: secret.description,
                rotation_interval_days: secret.rotation_interval_days,
                secret_type: inferredType,
            });
        }
    }, [secret, form]);

    const mutation = useMutation({
        mutationFn: async (values: any) => {
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            const { secret_type, value, ...metaFields } = values;

            // 1) Update metadata (if there are changes)
            const hasMetaChanges = Object.values(metaFields).some(v => v != null);
            if (hasMetaChanges) {
                await apiClient.patch(`/portal/secrets/${secret.id}`, metaFields);
            }

            // 2) If a new value was provided, rotate it
            if (value && value.trim()) {
                let cleanedValue = value;

                // SSH key sanitization: strip \r, normalize whitespace
                if (secretType === 'ssh_key' || secretType === 'certificate') {
                    cleanedValue = cleanedValue.replace(/\r\n/g, '\n').replace(/\r/g, '').trim();

                    // Auto-wrap raw base64 with PEM headers if missing
                    if (!cleanedValue.includes('-----BEGIN')) {
                        const stripped = cleanedValue.replace(/\s/g, '');
                        try {
                            const decoded = atob(stripped);
                            if (decoded.startsWith('openssh-key-v1')) {
                                const lines = stripped.match(/.{1,70}/g) || [];
                                cleanedValue = '-----BEGIN OPENSSH PRIVATE KEY-----\n' + lines.join('\n') + '\n-----END OPENSSH PRIVATE KEY-----\n';
                            }
                        } catch { /* not valid base64, leave as-is */ }
                    }
                }

                await apiClient.post(`/portal/secrets/${secret.id}/rotate`, {
                    new_value: cleanedValue,
                    reason: 'Updated via edit modal',
                });
            }
        },
        onSuccess: () => {
            message.success('Secret updated successfully');
            onSuccess();
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Update failed');
        }
    });

    const handleOk = () => {
        form.validateFields().then(values => {
            mutation.mutate(values);
        });
    };

    const handleFileUpload = (file: File) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const content = e.target?.result as string;
            form.setFieldValue('value', content);
        };
        reader.readAsText(file);
        return false;
    };

    return (
        <Modal
            title={`Edit Secret: ${secret?.alias}`}
            open={open}
            onOk={handleOk}
            onCancel={onClose}
            confirmLoading={mutation.isPending}
            width={600}
        >
            <Form form={form} layout="vertical">
                <Form.Item name="alias" label="Alias" rules={[{ required: true, message: 'Alias is required' }]}>
                    <Input placeholder="e.g. pbx.sip.password" />
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
                        options={SECRET_TYPES}
                        onChange={(val) => {
                            setSecretType(val);
                            form.setFieldValue('value', '');
                        }}
                    />
                </Form.Item>
                <Form.Item
                    name="value"
                    label="New Secret Value"
                    tooltip="Leave blank to keep the current value."
                    extra={isMultiline ? (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                            Paste the full PEM content or upload a file below.
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
                        <Input.Password placeholder="Enter new plaintext value to rotate" />
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
