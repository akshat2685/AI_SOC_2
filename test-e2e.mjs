import fetch from 'node-fetch';

async function testEndpoint(name, url, method = 'GET', body = null) {
  console.log(`\n--- Testing ${name} ---`);
  try {
    const options = { method, headers: {} };
    if (body) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    const res = await fetch(url, options);
    console.log(`Status: ${res.status}`);
    if (res.status === 200) {
      const contentType = res.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        const data = await res.json();
        console.log(`Response: ${JSON.stringify(data).substring(0, 150)}...`);
        return true;
      } else {
        const text = await res.text();
        console.log(`Response: ${text.substring(0, 150)}...`);
        return true;
      }
    } else {
      console.log(`Failed with status ${res.status}`);
      return false;
    }
  } catch (err) {
    console.error(`Error: ${err.message}`);
    return false;
  }
}

async function runE2E() {
  console.log("=== SHIELDAI E2E PRODUCTION VERIFICATION ===");
  
  await testEndpoint("Health Check", "http://localhost:3000/health");
  await testEndpoint("Integration Status", "http://localhost:3000/api/v1/integrations/status");
  await testEndpoint("Dashboard Metrics", "http://localhost:3000/api/v1/executive/metrics");
  await testEndpoint("Incidents List (Ingestion)", "http://localhost:3000/api/v1/incidents");
  await testEndpoint("Graph Topology (Neo4j)", "http://localhost:3000/api/v1/incidents/INC-1001/graph");
  await testEndpoint("Agent Task / GraphRAG", "http://localhost:3000/api/v1/agents/task", "POST", { task: "Analyze INC-1001", incidentId: "INC-1001" });
  await testEndpoint("Executive Report", "http://localhost:3000/api/v1/reports/digest");
  await testEndpoint("Telemetry Injection", "http://localhost:3000/api/v1/telemetry/generate", "POST", { type: "malware" });
  await testEndpoint("MITRE Mappings", "http://localhost:3000/mitre/mappings");
  await testEndpoint("Chat / Vector RAG", "http://localhost:3000/chat", "POST", { query: "What is host-web-1?" });
}

runE2E().catch(console.error);
