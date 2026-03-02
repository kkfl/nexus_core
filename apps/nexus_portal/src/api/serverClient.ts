import axios from 'axios';

// Server agent routes — in dev directly to :8010, in prod via Caddy
const serverBaseURL = import.meta.env.VITE_SERVER_AGENT_URL || '';

export const serverClient = axios.create({
    baseURL: serverBaseURL,
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: 15000,
});
