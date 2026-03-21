import axios from 'axios';

// PBX agent routes go through Caddy at /pbx/* (same origin)
// Caddy strips the /pbx prefix before forwarding to pbx-agent:8011
const pbxBaseURL = import.meta.env.VITE_PBX_AGENT_URL || '/pbx';

export const pbxClient = axios.create({
    baseURL: pbxBaseURL,
    headers: {
        'Content-Type': 'application/json',
        'X-Service-ID': 'nexus',
        'X-Agent-Key': import.meta.env.VITE_PBX_AGENT_KEY || 'nexus-pbx-key-change-me',
    },
    timeout: 90000,
});
