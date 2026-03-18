import axios from 'axios';

// PBX agent routes go through Caddy at /pbx/* (same origin)
const pbxBaseURL = import.meta.env.VITE_PBX_AGENT_URL || '';

export const pbxClient = axios.create({
    baseURL: pbxBaseURL,
    headers: {
        'Content-Type': 'application/json',
        'X-Service-ID': 'nexus',
        'X-Agent-Key': import.meta.env.VITE_PBX_AGENT_KEY || '',
    },
    timeout: 20000,
});
