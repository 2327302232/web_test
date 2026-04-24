#!/usr/bin/env node
const base = 'http://localhost:8788';

async function run() {
  try {
    const regBody = { username: 'testuser_http', password: 'plain123', displayName: 'HTTP User' };
    console.log('POST /api/test/register ->', JSON.stringify(regBody));
    let res = await fetch(`${base}/api/test/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(regBody) });
    console.log('status:', res.status);
    const j1 = await res.json();
    console.log('body:', JSON.stringify(j1));

    console.log('\nPOST /api/test/login ->', JSON.stringify({ username: 'testuser_http', password: 'plain123' }));
    res = await fetch(`${base}/api/test/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'testuser_http', password: 'plain123' }) });
    console.log('status:', res.status);
    const j2 = await res.json();
    console.log('body:', JSON.stringify(j2));

    console.log('\nGET /api/test/users');
    res = await fetch(`${base}/api/test/users`);
    console.log('status:', res.status);
    const j3 = await res.json();
    console.log('body:', JSON.stringify(j3));

    console.log('\nPOST /api/test/register (duplicate) ->', JSON.stringify(regBody));
    res = await fetch(`${base}/api/test/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(regBody) });
    console.log('status:', res.status);
    const j4 = await res.json();
    console.log('body:', JSON.stringify(j4));

    console.log('\nHTTP tests done');
  } catch (err) {
    console.error('HTTP test error', err);
    process.exit(1);
  }
}

run();
