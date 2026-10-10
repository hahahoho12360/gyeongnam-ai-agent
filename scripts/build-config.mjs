import fs from 'node:fs';
const configured = process.env.API_BASE_URL;
if (process.env.VERCEL && !configured) throw new Error('Set API_BASE_URL to the Render HTTPS URL');
const apiBase = (configured || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const parsed = new URL(apiBase);
if (process.env.VERCEL && parsed.protocol !== 'https:') throw new Error('API_BASE_URL must use HTTPS on Vercel');
fs.writeFileSync('frontend/config.js', `window.APP_CONFIG = ${JSON.stringify({API_BASE_URL: apiBase})};\n`);
console.log('frontend/config.js generated for', apiBase);
