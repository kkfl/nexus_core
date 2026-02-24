import { Modal, Form, Input, Select, InputNumber, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import axios from 'axios';

interface Props {
    open: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

export default function SecretCreateModal({ open, onClose, onSuccess }: Props) {
    const [form] = Form.useForm();

    const mutation = useMutation({
        mutationFn: (values: any) => axios.post('/api/portal/secrets', values),
        onSuccess: () => {
            message.success('Secret created successfully');
            form.resetFields();
            onSuccess();
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Failed to create secret');
        }
    });

    const handleOk = () => {
        form.validateFields().then(values => {
            mutation.mutate(values);
        });
    };

    return (
        <Modal
            title="Add New Secret"
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
                <Form.Item name="value" label="Secret Value" rules={[{ required: true }]}>
                    <Input.Password placeholder="Enter plaintext value" />
                </Form.Item>
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
