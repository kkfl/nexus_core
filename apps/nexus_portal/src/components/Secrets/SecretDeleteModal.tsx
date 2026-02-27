import { Modal, Form, Input, Typography, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';

const { Text } = Typography;

interface Props {
    secret: any;
    open: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

export default function SecretDeleteModal({ secret, open, onClose, onSuccess }: Props) {
    const [form] = Form.useForm();

    const mutation = useMutation({
        mutationFn: (values: any) => apiClient.delete(`/portal/secrets/${secret.id}`, { data: values }),
        onSuccess: () => {
            message.success('Secret deleted');
            form.resetFields();
            onSuccess();
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Delete failed');
        }
    });

    const handleOk = () => {
        form.validateFields().then(values => {
            if (values.confirm_alias !== secret.alias) {
                message.error('Alias confirmation does not match');
                return;
            }
            mutation.mutate({ password: values.password, reason: values.reason });
        });
    };

    return (
        <Modal
            title="Break-Glass Delete Required"
            open={open}
            onOk={handleOk}
            onCancel={onClose}
            confirmLoading={mutation.isPending}
            okText="Delete Permanently"
            okButtonProps={{ danger: true }}
        >
            <div style={{ marginBottom: 16 }}>
                <Text>Are you sure you want to delete <Text strong>{secret.alias}</Text>? This action is permanent and will be logged.</Text>
            </div>

            <Form form={form} layout="vertical" autoComplete="off">
                <Form.Item
                    name="confirm_alias"
                    label="Type the alias to confirm:"
                    rules={[{ required: true, message: 'Please confirm the alias' }]}
                >
                    <Input placeholder={secret.alias} autoComplete="off" />
                </Form.Item>

                <Form.Item
                    name="password"
                    label="Re-authenticate with Password"
                    rules={[{ required: true, message: 'Password is required for deletion' }]}
                >
                    <Input.Password placeholder="Enter your password" autoComplete="new-password" />
                </Form.Item>

                <Form.Item
                    name="reason"
                    label="Reason for Deletion"
                    rules={[{ required: true, message: 'Audit reason is required' }]}
                >
                    <Input.TextArea rows={2} placeholder="e.g. Migrated to new API key" />
                </Form.Item>
            </Form>
        </Modal>
    );
}
