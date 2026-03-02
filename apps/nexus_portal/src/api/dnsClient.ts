import axios from 'axios';

// DNS agent routes go through Caddy at /dns/* (same origin)
const dnsBaseURL = import.meta.env.VITE_DNS_AGENT_URL || '';

export const dnsClient = axios.create({
    baseURL: dnsBaseURL,
    headers: {
        'Content-Type': 'application/json',
        'X-Service-ID': 'nexus',
        'X-Agent-Key': 'nexus-dns-key',
    },
    timeout: 15000,
});
