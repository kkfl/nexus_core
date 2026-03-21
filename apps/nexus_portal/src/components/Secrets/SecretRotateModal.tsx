import { Modal, Form, Input, message, Upload, Button, Typography } from 'antd';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { UploadOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface Props {
    secret: any;
    open: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

/** Check if this secret likely holds a multi-line value (SSH key / cert). */
function isMultilineSecret(alias: string): boolean {
    const a = (alias || '').toLowerCase();
    return (a.includes('ssh') && a.includes('key'))
        || a.includes('cert')
        || a.includes('pem')
        || a.includes('tls');
}

export default function SecretRotateModal({ secret, open, onClose, onSuccess }: Props) {
    const [form] = Form.useForm();
    const isMultiline = isMultilineSecret(secret?.alias);

    const mutation = useMutation({
        mutationFn: (values: any) => apiClient.post(`/portal/secrets/${secret.id}/rotate`, values),
        onSuccess: () => {
            message.success('Secret rotated successfully');
            form.resetFields();
            onSuccess();
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Rotation failed');
        }
    });

    const handleOk = () => {
        form.validateFields().then(values => mutation.mutate(values));
    };

    const handleFileUpload = (file: File) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const content = e.target?.result as string;
            form.setFieldValue('new_value', content);
        };
        reader.readAsText(file);
        return false;
    };

    return (
        <Modal
            title={`Rotate Secret: ${secret?.alias}`}
            open={open}
            onOk={handleOk}
            onCancel={onClose}
            confirmLoading={mutation.isPending}
            okText="Rotate Now"
        >
            <Form form={form} layout="vertical">
                <Form.Item
                    name="new_value"
                    label="New Secret Value"
                    rules={[{ required: true, message: 'New value is required' }]}
                    extra={isMultiline ? (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                            Paste the full PEM content or upload a file below.
                        </Text>
                    ) : undefined}
                >
                    {isMultiline ? (
                        <Input.TextArea
                            rows={8}
                            placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----"
                            style={{ fontFamily: 'monospace', fontSize: 12 }}
                        />
                    ) : (
                        <Input.Password placeholder="Enter new plaintext value" />
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
                            <Button icon={<UploadOutlined />}>Upload Key / Certificate File</Button>
                        </Upload>
                    </Form.Item>
                )}
                <Form.Item name="reason" label="Reason (Optional)">
                    <Input placeholder="e.g. Scheduled rotation" />
                </Form.Item>
            </Form>
        </Modal>
    );
}
