import fetch from 'node-fetch';

async function run() {
  try {
    const res = await fetch('http://localhost:3000/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'password' })
    });
    console.log('Status:', res.status);
    const data = await res.text();
    console.log('Response:', data);
  } catch (err) {
    console.error('Error:', err.message);
  }
}
run();
