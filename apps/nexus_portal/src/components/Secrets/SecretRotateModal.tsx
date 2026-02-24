import { Modal, Form, Input, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import axios from 'axios';

interface Props {
    secret: any;
    open: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

export default function SecretRotateModal({ secret, open, onClose, onSuccess }: Props) {
    const [form] = Form.useForm();

    const mutation = useMutation({
        mutationFn: (values: any) => axios.post(`/api/portal/secrets/${secret.id}/rotate`, values),
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
                >
                    <Input.Password placeholder="Enter new plaintext value" />
                </Form.Item>
                <Form.Item name="reason" label="Reason (Optional)">
                    <Input placeholder="e.g. Scheduled rotation" />
                </Form.Item>
            </Form>
        </Modal>
    );
}
