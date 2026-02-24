import { Modal, Input, Typography, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import axios from 'axios';
import { useState } from 'react';

const { Text } = Typography;

interface Props {
    secret: any;
    open: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

export default function SecretDeleteModal({ secret, open, onClose, onSuccess }: Props) {
    const [confirmAlias, setConfirmAlias] = useState('');

    const mutation = useMutation({
        mutationFn: () => axios.delete(`/api/portal/secrets/${secret.id}`),
        onSuccess: () => {
            message.success('Secret deleted');
            onSuccess();
        },
        onError: (err: any) => {
            message.error(err.response?.data?.detail || 'Delete failed');
        }
    });

    const handleOk = () => {
        if (confirmAlias !== secret.alias) {
            message.error('Alias does not match');
            return;
        }
        mutation.mutate();
    };

    return (
        <Modal
            title="Confirm Deletion"
            open={open}
            onOk={handleOk}
            onCancel={onClose}
            confirmLoading={mutation.isPending}
            okText="Delete Permanently"
            okButtonProps={{ danger: true, disabled: confirmAlias !== secret.alias }}
        >
            <div style={{ marginBottom: 16 }}>
                <Text>Are you sure you want to delete <Text strong>{secret.alias}</Text>? This action is permanent and will be logged.</Text>
            </div>
            <div style={{ marginBottom: 8 }}>
                <Text type="secondary">Type the alias to confirm:</Text>
            </div>
            <Input
                placeholder={secret.alias}
                value={confirmAlias}
                onChange={(e) => setConfirmAlias(e.target.value)}
            />
        </Modal>
    );
}
