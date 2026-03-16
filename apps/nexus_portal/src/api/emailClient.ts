import axios from 'axios';

// Email agent routes go through Caddy at /email/* (same origin)
const emailBaseURL = import.meta.env.VITE_EMAIL_AGENT_URL || '';

export const emailClient = axios.create({
    baseURL: emailBaseURL,
    headers: {
        'Content-Type': 'application/json',
        'X-Service-ID': 'nexus',
        'X-Agent-Key': import.meta.env.VITE_EMAIL_AGENT_KEY || '',
    },
    timeout: 15000,
});
