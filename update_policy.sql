UPDATE vault_policies 
SET actions = '["read", "write", "rotate", "list_metadata", "delete"]' 
WHERE name = 'portal-all';
