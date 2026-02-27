import { Modal, Form, Input, Select, InputNumber, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { useEffect } from 'react';

interface Props {
    secret: any;
    open: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

export default function SecretEditModal({ secret, open, onClose, onSuccess }: Props) {
    const [form] = Form.useForm();

    useEffect(() => {
        if (secret) {
            form.setFieldsValue({
                alias: secret.alias,
                tenant_id: secret.tenant_id,
                env: secret.env,
                description: secret.description,
                rotation_interval_days: secret.rotation_interval_days,
            });
        }
    }, [secret, form]);

    const mutation = useMutation({
        mutationFn: (values: any) => apiClient.patch(`/portal/secrets/${secret.id}`, values),
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
            if (!values.value) {
                delete values.value;
            }
            mutation.mutate(values);
        });
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
                <Form.Item name="value" label="New Secret Value" tooltip="Leave blank to keep the current value.">
                    <Input.Password placeholder="Enter new plaintext value to rotate" />
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
