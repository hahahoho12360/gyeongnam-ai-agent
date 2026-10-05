import fs from 'node:fs';
const apiBase = process.env.API_BASE_URL || 'http://127.0.0.1:8000';
fs.writeFileSync('frontend/config.js', `window.APP_CONFIG = ${JSON.stringify({API_BASE_URL: apiBase})};\n`);
console.log('frontend/config.js generated for', apiBase);
