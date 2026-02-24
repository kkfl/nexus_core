import { Modal, Form, Input, InputNumber, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import axios from 'axios';
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
                description: secret.description,
                rotation_interval_days: secret.rotation_interval_days,
            });
        }
    }, [secret, form]);

    const mutation = useMutation({
        mutationFn: (values: any) => axios.patch(`/api/portal/secrets/${secret.id}`, values),
        onSuccess: () => {
            message.success('Metadata updated');
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

    return (
        <Modal
            title={`Edit Metadata: ${secret?.alias}`}
            open={open}
            onOk={handleOk}
            onCancel={onClose}
            confirmLoading={mutation.isPending}
        >
            <Form form={form} layout="vertical">
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
