import fs from 'node:fs';
const policy=JSON.parse(fs.readFileSync(new URL('./production-policy.json',import.meta.url),'utf8'));
export const productionPolicy=()=>structuredClone(policy);
