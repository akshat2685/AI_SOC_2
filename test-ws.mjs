import WebSocket from 'ws';

async function testWebSocket() {
  console.log("Testing WebSocket connection to ws://localhost:3000/ws");
  const ws = new WebSocket('ws://localhost:3000/ws');
  
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      console.log("WebSocket connection timed out");
      ws.close();
      resolve(false);
    }, 5000);

    ws.on('open', () => {
      console.log("WebSocket connected successfully");
      ws.send(JSON.stringify({ type: 'subscribe', channel: 'alerts' }));
    });

    ws.on('message', (data) => {
      console.log(`Received message: ${data.toString()}`);
      clearTimeout(timeout);
      ws.close();
      resolve(true);
    });

    ws.on('error', (err) => {
      console.error(`WebSocket Error: ${err.message}`);
      clearTimeout(timeout);
      resolve(false);
    });
  });
}

testWebSocket();
