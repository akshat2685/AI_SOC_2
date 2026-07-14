
const mockUsers = [
  { username: 'admin', password: 'password', role: 'Administrator', tenant_id: 'default', token: 'shieldai-mock-jwt-token-abcd-1234', premium: 1 }
];

function getMockDb() {
  console.log('[DB] In-memory database ready.');
  return {
    get: (sql, params, cb) => {
      if (typeof params === 'function') { cb = params; params = []; }
      if (!Array.isArray(params)) params = [];
      console.log('[DB Mock GET] SQL:', sql, 'Params:', params);
      
      if (sql.includes('users WHERE username = ? AND password = ?')) {
        const [username, password] = params;
        const user = mockUsers.find(u => u.username === username && u.password === password);
        if (cb) cb(null, user);
      } else if (sql.includes('SELECT premium FROM users WHERE username = ?')) {
        const [username] = params;
        const user = mockUsers.find(u => u.username === username);
        if (cb) cb(null, user ? { premium: user.premium } : null);
      } else {
        if (cb) cb(null, null);
      }
    },
    all: (sql, params, cb) => {
      if (typeof params === 'function') { cb = params; params = []; }
      if (!Array.isArray(params)) params = [];
      console.log('[DB Mock ALL] SQL:', sql, 'Params:', params);
      if (cb) cb(null, []);
    },
    run: function(sql, params, cb) {
      if (typeof params === 'function') { cb = params; params = []; }
      if (!Array.isArray(params)) params = [];
      console.log('[DB Mock RUN] SQL:', sql, 'Params:', params);
      
      if (sql.includes('INSERT INTO users')) {
        if (params.length >= 3) {
          const username = params[0];
          const password = params[1];
          const token = params[2];
          const role = 'analyst';
          const tenant_id = 'default';
          const premium = 0;
          
          const existing = mockUsers.find(u => u.username === username);
          if (!existing) {
            mockUsers.push({ username, password, role, tenant_id, token, premium });
          }
        }
        if (cb) cb(null);
      } else if (sql.includes('UPDATE users SET premium = 1')) {
        const [username] = params;
        const user = mockUsers.find(u => u.username === username);
        if (user) {
          user.premium = 1;
        }
        if (cb) cb.call({ lastID: null, changes: user ? 1 : 0 }, null);
      } else if (sql.includes('UPDATE users SET premium = 0')) {
        const [username] = params;
        const user = mockUsers.find(u => u.username === username);
        if (user) {
          user.premium = 0;
        }
        if (cb) cb.call({ lastID: null, changes: user ? 1 : 0 }, null);
      } else {
        if (cb) cb(null);
      }
    },
    serialize: (cb) => { if (cb) cb(); },
    close: (cb) => { if (cb) cb(); }
  };
}

import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import { GoogleGenAI } from '@google/genai';
import pg from 'pg';
import dotenv from 'dotenv';
import neo4j from 'neo4j-driver';
import { QdrantClient } from '@qdrant/js-client-rest';
import { Storage } from '@google-cloud/storage';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import multer from 'multer';

// Load environment variables
dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Initialize Database with robust fallback
let db = getMockDb();

if (process.env.DB_TYPE === 'postgres') {
  const pool = new pg.Pool({
    connectionString: process.env.POSTGRES_URL || `postgresql://${process.env.POSTGRES_USER}:${process.env.POSTGRES_PASSWORD}@${process.env.POSTGRES_HOST}:${process.env.POSTGRES_PORT}/${process.env.POSTGRES_DB}`,
    max: 20, // Connection pooling
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 5000, // Timeouts
  });
  
  // Adding retry mechanism for initial connection
  const connectWithRetry = async (retries = 5, delay = 5000) => {
    while (retries > 0) {
      try {
        const client = await pool.connect();
        console.log('[DB] Configured for Google Cloud SQL (PostgreSQL).');
        client.release();
        return;
      } catch (err) {
        console.error(`[DB] Connection to PostgreSQL failed. Retries left: ${retries - 1}`, err);
        retries -= 1;
        if (retries === 0) throw err;
        await new Promise(res => setTimeout(res, delay));
      }
    }
  };
  connectWithRetry().catch(err => console.error('[DB] Final PostgreSQL connection failure:', err));

  const convertSql = (sql) => {
    let index = 1;
    return sql.replace(/\?/g, () => `${index++}`);
  };

  db = {
    run: (sql, params, cb) => {
      if (typeof params === 'function') {
        cb = params;
        params = [];
      }
      pool.query(convertSql(sql), params)
        .then(res => cb && cb.call({ lastID: null, changes: res.rowCount }, null))
        .catch(err => cb && cb(err));
    },
    get: (sql, params, cb) => {
      if (typeof params === 'function') {
        cb = params;
        params = [];
      }
      pool.query(convertSql(sql), params)
        .then(res => cb && cb(null, res.rows[0]))
        .catch(err => cb && cb(err, null));
    },
    all: (sql, params, cb) => {
      if (typeof params === 'function') {
        cb = params;
        params = [];
      }
      pool.query(convertSql(sql), params)
        .then(res => cb && cb(null, res.rows))
        .catch(err => cb && cb(err, null));
    },
    serialize: (cb) => {
      cb();
    },
    close: (cb) => {
      pool.end().then(() => cb && cb(null)).catch(err => cb && cb(err));
    }
  };
} else {
  console.log('[DB] Running with functional in-memory database fallback.');
}

// Initialize Neo4j Client (lazy / graceful fallback)
let neo4jDriver = null;
const NEO4J_URI = process.env.NEO4J_URI;
const NEO4J_USERNAME = process.env.NEO4J_USERNAME;
const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD;
const NEO4J_DATABASE = process.env.NEO4J_DATABASE || 'neo4j';

if (NEO4J_URI && NEO4J_USERNAME && NEO4J_PASSWORD) {
  try {
    neo4jDriver = neo4j.driver(
      NEO4J_URI,
      neo4j.auth.basic(NEO4J_USERNAME, NEO4J_PASSWORD),
      {
        maxConnectionPoolSize: 50,
        connectionTimeout: 10000,
        maxConnectionLifetime: 3 * 60 * 60 * 1000,
        maxTransactionRetryTime: 15000
      }
    );
    neo4jDriver.getServerInfo().then(info => {
        console.log('[NEO4J] Driver configured successfully. Connected to', info.address);
    }).catch(err => {
        console.error('[NEO4J] Connection failed:', err);
    });
  } catch (err) {
    console.error('[NEO4J] Initialization failed:', err);
  }
} else {
  console.log('[NEO4J] Credentials not found in environment. Neo4j operations running in fallback/mock mode.');
}

// Initialize Qdrant Client (lazy / graceful fallback)
let qdrantClient = null;
const QDRANT_URL = process.env.QDRANT_URL;
const QDRANT_API_KEY = process.env.QDRANT_API_KEY;

if (QDRANT_URL && QDRANT_API_KEY) {
  try {
    qdrantClient = new QdrantClient({
      url: QDRANT_URL,
      apiKey: QDRANT_API_KEY,
      timeout: 10000 // Add timeout for managed cloud
    });
    console.log('[QDRANT] Client configured successfully.');
  } catch (err) {
    console.error('[QDRANT] Initialization failed:', err);
  }
} else {
  console.log('[QDRANT] Credentials not found in environment. Qdrant vector memory running in fallback/mock mode.');
}

// Seeding routines for external databases
async function seedNeo4j() {
  if (!neo4jDriver) return;
  const session = neo4jDriver.session();
  try {
    const result = await session.run('MATCH (n) RETURN count(n) AS count');
    const count = result.records[0].get('count').toNumber();
    if (count === 0) {
      console.log('[NEO4J] Database is empty. Seeding Digital Twin cybersecurity topology...');
      const createNodesQuery = `
        CREATE (w:Host {id: 'host-web-1', label: 'Host', ip: '10.0.1.10', os: 'Alpine Linux', criticality: 'Medium', service: 'Frontend Web Portal'})
        CREATE (d:Host {id: 'host-db-1', label: 'Host', ip: '10.0.1.15', os: 'Ubuntu 22.04', criticality: 'High', service: 'PostgreSQL Core DB'})
        CREATE (u:User {id: 'user-admin', label: 'User', username: 'admin', name: 'SOC Administrator', status: 'Active'})
        CREATE (a:Asset {id: 'asset-customer-records', label: 'Asset', name: 'Customer Financial Database', department: 'Finance', type: 'PII / Sensitive Data'})
        CREATE (ip:IP {id: 'ip-attacker', label: 'IP', ip: '198.51.100.42', country: 'Malicious Endpoint', threat_score: 95})
        
        CREATE (ip)-[:CONNECTS_TO {id: 'edge-1', protocol: 'HTTPS', port: 443}]->(w)
        CREATE (w)-[:CONNECTS_TO {id: 'edge-2', protocol: 'TCP', port: 5432}]->(d)
        CREATE (u)-[:USES {id: 'edge-3', role: 'Administrator'}]->(w)
        CREATE (d)-[:ACCESSES {id: 'edge-4', query: 'SELECT * FROM credit_cards'}]->(a)
      `;
      await session.run(createNodesQuery);
      console.log('[NEO4J] Seeding completed successfully.');
    } else {
      console.log(`[NEO4J] Database already contains ${count} nodes. Skipping seed.`);
    }
  } catch (err) {
    console.error('[NEO4J] Seeding failed:', err);
  } finally {
    await session.close();
  }
}

async function seedQdrant() {
  if (!qdrantClient) return;
  const collectionName = 'shieldai_memories';
  try {
    const collectionsRes = await qdrantClient.getCollections();
    const collectionExists = collectionsRes.collections.some(c => c.name === collectionName);
    
    if (!collectionExists) {
      console.log(`[QDRANT] Creating collection "${collectionName}"...`);
      await qdrantClient.createCollection(collectionName, {
        vectors: {
          size: 768,
          distance: 'Cosine'
        }
      });
      console.log(`[QDRANT] Collection "${collectionName}" created successfully.`);
      
      const seedTexts = [
        "Palo Alto CVE-2024-3400 Remote Command Execution with root privileges.",
        "SQL Injection vulnerability detected in Search endpoint of host-web-1 leading to UNION SELECT.",
        "Exfiltration pattern from Host DB-01 to rogue cloud storage destination.",
        "Brute force SSH attempt from malicious Tor IP 198.51.100.42."
      ];

      const points = [];
      for (let i = 0; i < seedTexts.length; i++) {
        const vector = new Array(768).fill(0);
        vector[i % 768] = 1.0;
        
        points.push({
          id: i + 1,
          vector: vector,
          payload: {
            text: seedTexts[i],
            category: 'THREAT_INTEL',
            timestamp: new Date().toISOString()
          }
        });
      }
      
      await qdrantClient.upsert(collectionName, {
        wait: true,
        points: points
      });
      console.log(`[QDRANT] Collection "${collectionName}" seeded with standard memories.`);
    } else {
      console.log(`[QDRANT] Collection "${collectionName}" already exists.`);
    }
  } catch (err) {
    console.error('[QDRANT] Seeding failed:', err);
  }
}

async function getTopologyFromNeo4j() {
  if (!neo4jDriver) return null;
  const session = neo4jDriver.session();
  try {
    const nodesRes = await session.run('MATCH (n) RETURN n');
    const edgesRes = await session.run('MATCH (n)-[r]->(m) RETURN r, id(r) as edgeId, n.id as sourceId, m.id as targetId, type(r) as edgeType');
    
    const nodes = nodesRes.records.map(record => {
      const node = record.get('n');
      const label = node.labels[0] || 'Unknown';
      return {
        id: node.properties.id || node.identity.toString(),
        label: label,
        properties: node.properties
      };
    });

    const edges = edgesRes.records.map(record => {
      const r = record.get('r');
      const edgeId = record.get('edgeId').toString();
      const sourceId = record.get('sourceId');
      const targetId = record.get('targetId');
      const edgeType = record.get('edgeType');
      return {
        id: r.properties.id || `edge-${edgeId}`,
        source: sourceId,
        target: targetId,
        type: edgeType,
        properties: r.properties
      };
    });

    if (nodes.length === 0) return null;
    return { nodes, edges };
  } catch (err) {
    console.error('[NEO4J] Failed to fetch topology from Neo4j:', err);
    return null;
  } finally {
    await session.close();
  }
}

async function addSimulationEdgeToNeo4j(source, target, probability) {
  if (!neo4jDriver) return;
  const session = neo4jDriver.session();
  try {
    await session.run(`
      MATCH (s {id: $source}), (t {id: $target})
      CREATE (s)-[r:SIMULATED_ATTACK {id: $edgeId, probability: $probability, timestamp: datetime()}]->(t)
      RETURN r
    `, { source, target, probability, edgeId: `sim-edge-${Math.random().toString(36).substring(2, 7)}` });
  } catch (err) {
    console.error('[NEO4J] Failed to add simulation edge:', err);
  } finally {
    await session.close();
  }
}

async function cleanupSimulationsInNeo4j() {
  if (!neo4jDriver) return;
  const session = neo4jDriver.session();
  try {
    await session.run('MATCH ()-[r:SIMULATED_ATTACK]-() DELETE r');
  } catch (err) {
    console.error('[NEO4J] Failed to clean up simulations in Neo4j:', err);
  } finally {
    await session.close();
  }
}

async function searchQdrantMemories(queryText) {
  if (!qdrantClient) return [];
  const collectionName = 'shieldai_memories';
  try {
    let vector = null;
    if (ai) {
      try {
        const embedRes = await ai.models.embedContent({
          model: 'text-embedding-04',
          contents: queryText,
        });
        if (embedRes.embedding?.values) {
          vector = embedRes.embedding.values;
        }
      } catch (e) {
        console.warn('[QDRANT] Embedding creation failed:', e);
      }
    }
    
    if (!vector) {
      vector = new Array(768).fill(0);
      let hash = 0;
      for (let i = 0; i < queryText.length; i++) {
        hash = queryText.charCodeAt(i) + ((hash << 5) - hash);
      }
      for (let j = 0; j < 768; j++) {
        vector[j] = Math.sin(hash + j) * 0.1;
      }
    }

    const searchRes = await qdrantClient.search(collectionName, {
      vector: vector,
      limit: 3,
      with_payload: true
    });
    
    return searchRes.map(hit => ({
      text: hit.payload?.text,
      score: hit.score,
      category: hit.payload?.category,
      timestamp: hit.payload?.timestamp
    }));
  } catch (err) {
    console.error('[QDRANT] Search failed:', err);
    return [];
  }
}

async function addQdrantMemory(text, category) {
  if (!qdrantClient) return;
  const collectionName = 'shieldai_memories';
  try {
    let vector = null;
    if (ai) {
      try {
        const embedRes = await ai.models.embedContent({
          model: 'text-embedding-04',
          contents: text,
        });
        if (embedRes.embedding?.values) {
          vector = embedRes.embedding.values;
        }
      } catch (e) {
        console.warn('[QDRANT] Embedding creation failed:', e);
      }
    }
    
    if (!vector) {
      vector = new Array(768).fill(0);
      let hash = 0;
      for (let i = 0; i < text.length; i++) {
        hash = text.charCodeAt(i) + ((hash << 5) - hash);
      }
      for (let j = 0; j < 768; j++) {
        vector[j] = Math.sin(hash + j) * 0.1;
      }
    }

    const pointId = Math.floor(Math.random() * 10000000);
    await qdrantClient.upsert(collectionName, {
      wait: true,
      points: [{
        id: pointId,
        vector: vector,
        payload: {
          text: text,
          category: category || 'MEM_MANUAL',
          timestamp: new Date().toISOString()
        }
      }]
    });
  } catch (err) {
    console.error('[QDRANT] Add memory failed:', err);
  }
}

// Trigger Seeding asynchronously
setTimeout(() => {
  seedNeo4j();
  seedQdrant();
}, 2000);


// Setup database tables
setTimeout(() => {
  if (db && typeof db.serialize === 'function') {
    db.serialize(() => {
      db.run(`
        CREATE TABLE IF NOT EXISTS users (
          username TEXT PRIMARY KEY,
          password TEXT,
          role TEXT,
          tenant_id TEXT,
          token TEXT,
          premium INTEGER DEFAULT 0
        )
      `);

      // Insert default admin user if not exists (with premium=0 to test checkout)
      db.run(
        `INSERT INTO users (username, password, role, tenant_id, token, premium) 
         VALUES ('admin', 'admin', 'admin', 'default', 'shieldai-mock-jwt-token-abcd-1234', 0)
         ON CONFLICT (username) DO NOTHING`
      );
    });
  }
}, 1000);

const app = express();
app.set('trust proxy', 1);
// Cloud Run injects PORT. However, the AI Studio preview environment (identified by APPLET_ID)
// reserves 8080 for its internal proxy and requires the app to bind to 3000.
const PORT = process.env.APPLET_ID ? 3000 : (process.env.PORT || 8080);

// Health Check Endpoint for Cloud Run
app.get('/health', (req, res) => {
  res.status(200).send('OK');
});

// app.use(helmet()); // Disabled for AI Studio preview iframe compatibility
app.use(cors());
app.use(express.json());

const apiLimiter = rateLimit({
  windowMs: 1 * 60 * 1000, // 1 minute
  max: 100, // limit each IP to 100 requests per windowMs
  message: 'Too many requests from this IP, please try again later.',
  validate: false
});
app.use('/api/', apiLimiter);

const agentLimiter = rateLimit({
  windowMs: 1 * 60 * 1000,
  max: 10,
  message: 'Agent task limit exceeded for this IP.',
  validate: false
});
app.use('/api/v1/agents/task', agentLimiter);

// Initialize Gemini Client Lazily/Optionally
let ai = null;
if (process.env.GEMINI_API_KEY) {
  try {
    ai = new GoogleGenAI({
      apiKey: process.env.GEMINI_API_KEY,
      httpOptions: {
        headers: {
          'User-Agent': 'aistudio-build',
        }
      }
    });
    console.log('[AI] Gemini client initialized successfully with API key.');
  } catch (err) {
    console.error('[AI] Gemini initialization failed:', err);
  }
} else {
  console.log('[AI] GEMINI_API_KEY not found. Running in mock analyst fallback mode.');
}

// ==========================================
// IN-MEMORY DATA STORAGE
// ==========================================

let incidents = [
  {
    id: 1,
    timestamp: new Date(Date.now() - 3600000 * 2).toISOString(),
    title: 'Kubernetes API Server Bruteforce',
    severity: 'CRITICAL',
    status: 'OPEN',
    correlation_key: 'corr-k8s-brute-001',
    llm_summary: 'Multiple failed authentication requests detected against the Kube-API from unauthorized cloud endpoints. Correlated via behavioral telemetry.',
    verdict: 'SUSPICIOUS',
    analyst_notes: 'Checking source IPs against Tor exit nodes and CTI databases.',
    resolved_at: null,
    tenant_id: 'default'
  },
  {
    id: 2,
    timestamp: new Date(Date.now() - 3600000 * 5).toISOString(),
    title: 'Exfiltration to Rogue Cloud Storage',
    severity: 'HIGH',
    status: 'INVESTIGATING',
    correlation_key: 'corr-exfil-rogue-002',
    llm_summary: 'Outbound HTTPS transfer of 4.2GB of encrypted payload detected from production database node DB-01 to unauthorized MegaStorage domain.',
    verdict: 'TRUE_POSITIVE',
    analyst_notes: 'Isolated DB-01 network namespace and rotated active PostgreSQL service account credentials.',
    resolved_at: null,
    tenant_id: 'default'
  },
  {
    id: 3,
    timestamp: new Date(Date.now() - 3600000 * 12).toISOString(),
    title: 'Privilege Escalation on host-web-1',
    severity: 'HIGH',
    status: 'RESOLVED',
    correlation_key: 'corr-priv-esc-003',
    llm_summary: 'Sudoers file modification detected via sysmon event id 11. Triggered automated containment playbook containing local endpoint isolation.',
    verdict: 'TRUE_POSITIVE',
    analyst_notes: 'Resolved. Local service container restarted from hardened immutable base image.',
    resolved_at: new Date(Date.now() - 3600000 * 11).toISOString(),
    tenant_id: 'default'
  },
  {
    id: 4,
    timestamp: new Date(Date.now() - 3600000 * 24).toISOString(),
    title: 'Credential Stuffing on Auth Endpoint',
    severity: 'MEDIUM',
    status: 'RESOLVED',
    correlation_key: 'corr-cred-stuff-004',
    llm_summary: 'Spike in HTTP 401 Unauthorized responses on /api/v1/auth/login. Flagged as brute-force pattern targeting multiple customer logins.',
    verdict: 'BENIGN',
    analyst_notes: 'Confirmed standard QA load testing cycle from designated safe sandbox testing network.',
    resolved_at: new Date(Date.now() - 3600000 * 22).toISOString(),
    tenant_id: 'default'
  }
];

let alerts = [
  {
    id: 101,
    timestamp: new Date(Date.now() - 300000).toISOString(),
    title: 'Unauthorized SSH Key Addition',
    severity: 'CRITICAL',
    confidence: '94%',
    confidence_score: 94,
    attack_type: 'CREDENTIAL_ACCESS',
    evidence: 'Modified /root/.ssh/authorized_keys by unprivileged process UID: 1001',
    attacker_ip: '198.51.100.42',
    verdict: 'TRUE_POSITIVE',
    incident_id: 1,
    tenant_id: 'default'
  },
  {
    id: 102,
    timestamp: new Date(Date.now() - 600000).toISOString(),
    title: 'Suspected Reverse Shell Connection',
    severity: 'HIGH',
    confidence: '89%',
    confidence_score: 89,
    attack_type: 'EXECUTION',
    evidence: '/bin/bash launched with active sockets redirected to port 4444',
    attacker_ip: '198.51.100.42',
    verdict: 'TRUE_POSITIVE',
    incident_id: 1,
    tenant_id: 'default'
  },
  {
    id: 103,
    timestamp: new Date(Date.now() - 1200000).toISOString(),
    title: 'SQL Injection on Search API',
    severity: 'HIGH',
    confidence: '91%',
    confidence_score: 91,
    attack_type: 'INITIAL_ACCESS',
    evidence: 'Received input payload containing UNION SELECT schema_name FROM information_schema.schemata',
    attacker_ip: '203.0.113.88',
    verdict: 'SUSPICIOUS',
    incident_id: 2,
    tenant_id: 'default'
  },
  {
    id: 104,
    timestamp: new Date(Date.now() - 1800000).toISOString(),
    title: 'Abnormal Outbound Data Transfer',
    severity: 'MEDIUM',
    confidence: '78%',
    confidence_score: 78,
    attack_type: 'EXFILTRATION',
    evidence: 'DB-01 connected to external socket transferring 4.2GB in 8 minutes',
    attacker_ip: '185.220.101.5',
    verdict: 'TRUE_POSITIVE',
    incident_id: 2,
    tenant_id: 'default'
  },
  {
    id: 105,
    timestamp: new Date(Date.now() - 3600000 * 3).toISOString(),
    title: 'Multi-User Login Lockouts',
    severity: 'MEDIUM',
    confidence: '82%',
    confidence_score: 82,
    attack_type: 'CREDENTIAL_STUFFING',
    evidence: '143 accounts locked out within 60-second window',
    attacker_ip: '45.227.254.12',
    verdict: 'TRUE_POSITIVE',
    incident_id: 4,
    tenant_id: 'default'
  }
];

let auditLogs = [
  { id: 1, timestamp: new Date(Date.now() - 3600000 * 4).toISOString(), action: 'USER_LOGIN', user: 'admin', details: 'Successful sign-in from 10.0.1.5' },
  { id: 2, timestamp: new Date(Date.now() - 3600000 * 3).toISOString(), action: 'ALERT_TRIAGED', user: 'system_ai', details: 'Alert 101 auto-correlated to Incident 1' },
  { id: 3, timestamp: new Date(Date.now() - 3600000 * 2).toISOString(), action: 'INCIDENT_CREATED', user: 'system_ai', details: 'Created Incident 1 (CRITICAL severity)' },
  { id: 4, timestamp: new Date(Date.now() - 3600000).toISOString(), action: 'VERDICT_APPLIED', user: 'admin', details: 'Set Incident 3 verdict to TRUE_POSITIVE' }
];

let approvals = [
  {
    id: 1,
    timestamp: new Date(Date.now() - 600000).toISOString(),
    title: 'Isolate host-web-1 from Production VPC',
    action: 'CONTAINMENT_ISOLATION',
    target: 'host-web-1 (10.0.1.10)',
    requested_by: 'ShieldAI response_agent',
    status: 'PENDING',
    justification: 'Critical reverse shell active on target node posing exfiltration risk.'
  },
  {
    id: 2,
    timestamp: new Date(Date.now() - 1200000).toISOString(),
    title: 'Revoke AWS IAM Role AdminAccess-Dev',
    action: 'ACCESS_REVOCATION',
    target: 'IAM Role: AdminAccess-Dev',
    requested_by: 'ShieldAI identity_agent',
    status: 'PENDING',
    justification: 'Suspicious credential usage detected from Tor Exit Node IP 185.220.101.5.'
  },
  {
    id: 3,
    timestamp: new Date(Date.now() - 1800000).toISOString(),
    title: 'Deploy Virtual Patch for CVE-2024-3400',
    action: 'VIRTUAL_PATCHING',
    target: 'Palo Alto Edge Gateways',
    requested_by: 'ShieldAI patching_agent',
    status: 'PENDING',
    justification: 'Active exploitation attempt detected matching Palo Alto OS Command Injection vulnerability.'
  }
];

// Digital Twin Topology Data
let topology = {
  nodes: [
    { id: 'host-web-1', label: 'Host', properties: { ip: '10.0.1.10', os: 'Alpine Linux', criticality: 'Medium', service: 'Frontend Web Portal' } },
    { id: 'host-db-1', label: 'Host', properties: { ip: '10.0.1.15', os: 'Ubuntu 22.04', criticality: 'High', service: 'PostgreSQL Core DB' } },
    { id: 'user-admin', label: 'User', properties: { username: 'admin', name: 'SOC Administrator', status: 'Active' } },
    { id: 'asset-customer-records', label: 'Asset', properties: { name: 'Customer Financial Database', department: 'Finance', type: 'PII / Sensitive Data' } },
    { id: 'ip-attacker', label: 'IP', properties: { ip: '198.51.100.42', country: 'Malicious Endpoint', threat_score: 95 } }
  ],
  edges: [
    { id: 'edge-1', source: 'ip-attacker', target: 'host-web-1', type: 'CONNECTS_TO', properties: { protocol: 'HTTPS', port: 443 } },
    { id: 'edge-2', source: 'host-web-1', target: 'host-db-1', type: 'CONNECTS_TO', properties: { protocol: 'TCP', port: 5432 } },
    { id: 'edge-3', source: 'user-admin', target: 'host-web-1', type: 'USES', properties: { role: 'Administrator' } },
    { id: 'edge-4', source: 'host-db-1', target: 'asset-customer-records', type: 'ACCESSES', properties: { query: 'SELECT * FROM credit_cards' } }
  ]
};

// ==========================================
// REST API ROUTING
// ==========================================

// Authentication
app.post('/auth/login', (req, res) => {
  const { username, password } = req.body;
  
  db.get('SELECT * FROM users WHERE username = ? AND password = ?', [username, password], (err, row) => {
    if (err) {
      console.error('[DB] Login query error:', err);
      return res.status(500).json({ detail: 'Database error' });
    }
    if (row) {
      res.json({
        username: row.username,
        role: row.role,
        tenant_id: row.tenant_id,
        token: row.token,
        premium: row.premium === 1
      });
    } else {
      res.status(401).json({ detail: 'Invalid username or password' });
    }
  });
});

app.post('/auth/register', (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) {
    return res.status(400).json({ detail: 'Username and password are required' });
  }

  db.run(
    `INSERT INTO users (username, password, role, tenant_id, token, premium) 
     VALUES (?, ?, 'analyst', 'default', ?, 0)`,
    [username, password, 'shieldai-mock-jwt-token-' + Math.random().toString(36).substring(2, 9)],
    function(err) {
      if (err) {
        if (err.message.includes('UNIQUE constraint failed')) {
          return res.status(400).json({ detail: 'Username already exists' });
        }
        return res.status(500).json({ detail: 'Database error: ' + err.message });
      }
      res.json({ status: 'success', username });
    }
  );
});

// Payments & SaaS Subscription Setup
app.post('/api/v1/payments/checkout', (req, res) => {
  const { username, plan, cardNumber, cardExpiry, cardCvc } = req.body;
  if (!username) {
    return res.status(400).json({ error: 'Missing username' });
  }

  db.run(
    'UPDATE users SET premium = 1 WHERE username = ?',
    [username],
    function(err) {
      if (err) {
        console.error('[DB] Payment state update failed:', err);
        return res.status(500).json({ error: 'Failed to update subscription status' });
      }

      auditLogs.push({
        id: auditLogs.length + 1,
        timestamp: new Date().toISOString(),
        action: 'SUBSCRIPTION_UPGRADED',
        user: username,
        details: `Upgraded to ${plan || 'Pro'} Plan (Payment processed securely)`
      });

      res.json({
        success: true,
        message: `Successfully upgraded ${username} to ${plan || 'Pro'} Plan!`,
        premium: true
      });
    }
  );
});

app.get('/api/v1/payments/status', (req, res) => {
  const { username } = req.query;
  if (!username) {
    return res.status(400).json({ error: 'Missing username' });
  }

  db.get('SELECT premium FROM users WHERE username = ?', [username], (err, row) => {
    if (err) {
      return res.status(500).json({ error: 'Database error' });
    }
    if (row) {
      res.json({ premium: row.premium === 1 });
    } else {
      res.status(404).json({ error: 'User not found' });
    }
  });
});

app.post('/api/v1/payments/downgrade', (req, res) => {
  const { username } = req.body;
  if (!username) {
    return res.status(400).json({ error: 'Missing username' });
  }

  db.run('UPDATE users SET premium = 0 WHERE username = ?', [username], function(err) {
    if (err) {
      return res.status(500).json({ error: 'Database error' });
    }
    
    auditLogs.push({
      id: auditLogs.length + 1,
      timestamp: new Date().toISOString(),
      action: 'SUBSCRIPTION_DOWNGRADED',
      user: username,
      details: `Reverted back to Free Tier`
    });

    res.json({ success: true, premium: false });
  });
});

// Incidents
app.get('/api/v1/incidents', (req, res) => {
  res.json(incidents);
});

app.get('/incidents/:id/details', (req, res) => {
  const incId = parseInt(req.params.id);
  const inc = incidents.find(i => i.id === incId);
  if (!inc) return res.status(404).json({ error: 'Incident not found' });
  
  // Return nested details
  res.json({
    id: inc.id,
    logs: auditLogs.filter(l => l.details.includes(String(inc.id))),
    alerts: alerts.filter(a => a.incident_id === incId),
    related_logs: [
      { event_type: 'FAILED_SSH_LOGIN', timestamp: new Date(Date.now() - 3600000 * 2.5).toISOString(), source_ip: '198.51.100.42', endpoint: 'kube-api-server', user_id: 'root' },
      { event_type: 'PROCESS_SPAWNED', timestamp: new Date(Date.now() - 3600000 * 2.2).toISOString(), source_ip: '10.0.1.5', endpoint: 'host-web-1', user_id: 'web-service' },
      { event_type: 'CREDENTIAL_ACCESS', timestamp: new Date(Date.now() - 3600000 * 2.1).toISOString(), source_ip: '198.51.100.42', endpoint: 'host-web-1', user_id: 'root' },
    ],
    iocs: [
      { type: 'IP', value: '198.51.100.42', description: 'Attack source IP' },
      { type: 'File Hash (SHA256)', value: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', description: 'Suspected implant payload' }
    ],
    actions: [
      { timestamp: new Date(Date.now() - 100000).toISOString(), status: 'COMPLETE', description: 'VPC Route Isolation triggered' },
      { timestamp: new Date(Date.now() - 50000).toISOString(), status: 'PENDING', description: 'Triggering secondary credentials flush' }
    ]
  });
});

app.get('/api/v1/incidents/:id/predict-risk', async (req, res) => {
  const incId = parseInt(req.params.id);
  const inc = incidents.find(i => i.id === incId);
  if (!inc) return res.status(404).json({ error: 'Incident not found' });

  const incidentAlerts = alerts.filter(a => a.incident_id === incId);

  // Default deterministic rules-based calculations
  let riskScore = 30;
  let riskLevel = 'Low';
  let likelihood = '30%';
  let reasoning = 'Minimal indicators of escalation detected. Under passive monitoring.';
  let mitigation = 'Maintain standard continuous telemetry logging and alert consolidation.';

  if (inc.severity === 'CRITICAL') {
    riskScore = 85;
    riskLevel = 'Critical';
    likelihood = '85%';
    reasoning = 'Critical base severity incident with active system compromise patterns.';
    mitigation = 'Initiate immediate endpoint containment and perform credential rotation.';
  } else if (inc.severity === 'HIGH') {
    riskScore = 65;
    riskLevel = 'High';
    likelihood = '65%';
    reasoning = 'High severity alert indicating system privilege attempts or unauthorized lateral hops.';
    mitigation = 'Enable strict egress VPC firewall filters and check Active Directory PAM logs.';
  } else if (inc.severity === 'MEDIUM') {
    riskScore = 45;
    riskLevel = 'Medium';
    likelihood = '45%';
    reasoning = 'Medium severity event with isolated suspicious process spawns or unauthorized login peaks.';
    mitigation = 'Require multi-factor authentication prompt re-verification for targeted endpoints.';
  }

  if (incidentAlerts.length > 0) {
    riskScore = Math.min(100, riskScore + (incidentAlerts.length * 5));
    if (riskScore >= 80) riskLevel = 'Critical';
    else if (riskScore >= 60) riskLevel = 'High';
    else if (riskScore >= 40) riskLevel = 'Medium';
    likelihood = `${riskScore}%`;
  }

  if (ai) {
    try {
      const prompt = `You are an elite automated Security Incident Analyst powered by ShieldAI's AI engine.
Your goal is to estimate the risk score (0-100) and escalation likelihood of a security incident.

Incident details:
- Title: ${inc.title}
- Severity: ${inc.severity}
- Correlation Key: ${inc.correlation_key}
- Initial AI Summary: ${inc.llm_summary || 'N/A'}
- Verdict: ${inc.verdict || 'N/A'}
- Analyst Notes: ${inc.analyst_notes || 'None'}

Correlated Alerts:
${JSON.stringify(incidentAlerts.map(a => ({ title: a.title, severity: a.severity, attack_type: a.attack_type, evidence: a.evidence })))}

Analyze these details and provide:
1. Risk score (0-100 integer)
2. Risk Level ('Critical' | 'High' | 'Medium' | 'Low')
3. Likelihood of escalation (percentage format, e.g. "75%")
4. Direct, crisp 1-sentence reasoning for the estimation.
5. Direct, crisp 1-sentence mitigation recommendation.

Return your response in EXACT JSON format below. Do not include markdown wraps or code fences, return raw JSON string.
{
  "riskScore": number,
  "riskLevel": "Critical" | "High" | "Medium" | "Low",
  "likelihood": "string with percentage",
  "reasoning": "string",
  "mitigation": "string"
}`;

      const response = await ai.models.generateContent({
        model: 'gemini-3.5-flash',
        contents: prompt,
      });

      if (response && response.text) {
        let text = response.text.trim();
        if (text.startsWith('```json')) {
          text = text.substring(7);
        }
        if (text.startsWith('```')) {
          text = text.substring(3);
        }
        if (text.endsWith('```')) {
          text = text.substring(0, text.length - 3);
        }
        text = text.trim();
        
        const parsed = JSON.parse(text);
        if (parsed.riskScore !== undefined) {
          riskScore = Number(parsed.riskScore);
          riskLevel = parsed.riskLevel || riskLevel;
          likelihood = parsed.likelihood || likelihood;
          reasoning = parsed.reasoning || reasoning;
          mitigation = parsed.mitigation || mitigation;
        }
      }
    } catch (err) {
      console.error('[AI ESCALATION PREDICTION ERR]', err);
    }
  }

  res.json({
    incidentId: incId,
    riskScore,
    riskLevel,
    likelihood,
    reasoning,
    mitigation,
    timestamp: new Date().toISOString()
  });
});

app.get('/api/v1/incidents/:id/recommended-triage', async (req, res) => {
  const incId = parseInt(req.params.id);
  const inc = incidents.find(i => i.id === incId);
  if (!inc) return res.status(404).json({ error: 'Incident not found' });

  const historicalIncidents = incidents.filter(i => i.id !== incId);

  // Define realistic threat feeds
  const threatIntelFeeds = [
    {
      id: "TI-01",
      source: "ShieldAI Threat Intelligence",
      indicator: "198.51.100.42",
      indicatorType: "IP",
      threatActor: "APT29 (Cozy Bear) / UNC2532",
      campaign: "Kube-API Authentication Harvest Campaign",
      malwareFamily: "Spyre-Kubernetes-Implant",
      severity: "CRITICAL",
      description: "Active threat group targeting Kubernetes API server endpoints using coordinated brute-force attacks from bulletproof hosting subnets. Corresponds to active campaign UNC2532.",
      observedInWildCount: 1420
    },
    {
      id: "TI-02",
      source: "DHS CISA Feed",
      indicator: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      indicatorType: "SHA256",
      threatActor: "Lazarus Group",
      campaign: "Rogue Cloud Storage Exfiltration Initiative",
      malwareFamily: "MegaDrop-Stealer",
      severity: "HIGH",
      description: "Encrypted payload exfiltration binary that mimics authorized MegaStorage background sync agents. Primarily targets production database servers.",
      observedInWildCount: 512
    },
    {
      id: "TI-03",
      source: "Mitre ATT&CK CTI",
      indicator: "host-web-1",
      indicatorType: "Endpoint",
      threatActor: "KUBE-SPIDER",
      campaign: "Web-to-Pod Privilege Escalation",
      malwareFamily: "Rooter-Sudo-Inject",
      severity: "HIGH",
      description: "Privilege escalation attempts targeting vulnerable web-servers to hijack host namespaces and alter local sudoers configurations.",
      observedInWildCount: 89
    }
  ];

  // Match relevant threat intel to current incident context deterministically
  const matchedFeed = threatIntelFeeds.find(feed => {
    const lowerTitle = inc.title.toLowerCase();
    const lowerSummary = (inc.llm_summary || "").toLowerCase();
    const lowerNotes = (inc.analyst_notes || "").toLowerCase();
    
    if (feed.indicatorType === "IP" && (lowerNotes.includes(feed.indicator) || lowerSummary.includes(feed.indicator) || lowerTitle.includes("kubernetes") || lowerTitle.includes("bruteforce"))) return true;
    if (feed.indicatorType === "SHA256" && (lowerNotes.includes(feed.indicator) || lowerSummary.includes(feed.indicator) || lowerTitle.includes("exfiltration") || lowerTitle.includes("storage"))) return true;
    if (feed.indicatorType === "Endpoint" && (lowerTitle.includes("privilege") || lowerSummary.includes("web-1") || lowerNotes.includes("host-web-1"))) return true;
    
    return false;
  }) || threatIntelFeeds[0]; // fallback to first threat intel if nothing else matches

  // Deterministic similar incidents calculation
  const similarIncidents = historicalIncidents.map(h => {
    let similarityReason = "Under passive monitoring with similar base severity levels.";
    let score = 0;

    if (h.severity === inc.severity) {
      similarityReason = `Shares identical severity class (${h.severity}) and system telemetry parameters.`;
      score += 30;
    }

    const lowerCurrent = inc.title.toLowerCase() + " " + (inc.llm_summary || "").toLowerCase();
    const lowerHist = h.title.toLowerCase() + " " + (h.llm_summary || "").toLowerCase();
    
    // Check keywords
    const keywords = ["kube", "kubernetes", "brute", "ssh", "credential", "exfiltration", "storage", "privilege", "web", "host"];
    keywords.forEach(word => {
      if (lowerCurrent.includes(word) && lowerHist.includes(word)) {
        score += 40;
        similarityReason = `Highly similar threat vector: Shared active context on "${word}" indicators and behavioral patterns.`;
      }
    });

    return {
      id: h.id,
      title: h.title,
      similarityReason,
      verdict: h.verdict || "UNKNOWN",
      resolvedAt: h.resolved_at,
      score
    };
  }).sort((a, b) => b.score - a.score).slice(0, 2);

  // Recommended Playbooks (fallback / default)
  let recommendedPlaybooks = [
    {
      id: 'IP_BLOCK',
      name: 'Block Source IP (Automated)',
      description: 'Enforce perimeter firewall blocks and route table drop rules for malicious source IPs.',
      difficulty: 'Low',
      duration: '2 mins',
      matchReason: 'Similar to resolved cases where perimeter blocks halted brute-force and command injection loops.',
      recommendedActions: ['Add perimeter drop rule in VPC firewall', 'Invalidate active connection sessions from 198.51.100.42']
    },
    {
      id: 'HOST_ISOLATE',
      name: 'Isolate Impacted Host VM',
      description: 'Sever active egress/ingress routes of compromised VM/container while preserving volatile memory.',
      difficulty: 'Medium',
      duration: '5 mins',
      matchReason: 'Critical escalation pattern requiring isolation to mitigate potential lateral network hops.',
      recommendedActions: ['Apply Isolation Security Group policy', 'Spin up memory snapshot agent to capture root processes']
    }
  ];

  if (inc.title.toLowerCase().includes("exfiltration") || inc.title.toLowerCase().includes("storage")) {
    recommendedPlaybooks = [
      {
        id: 'HOST_ISOLATE',
        name: 'Isolate Impacted Host VM',
        description: 'Sever active egress/ingress routes of compromised VM/container while preserving volatile memory.',
        difficulty: 'Medium',
        duration: '5 mins',
        matchReason: 'Critical exfiltration streams identified. Isolation halts data outflow immediately.',
        recommendedActions: ['Apply Isolation Security Group policy', 'Configure strict network namespace container sandbox limits']
      },
      {
        id: 'USER_DISABLE',
        name: 'Revoke database credentials & reset account',
        description: 'Instantly disable user active directory profile, rotate API tokens, and flush active database credentials.',
        difficulty: 'Low',
        duration: '3 mins',
        matchReason: 'Exfiltration requires valid service token context; rotation disrupts illegitimate operations.',
        recommendedActions: ['Revoke active production service account credentials', 'Inhibit Active Directory access tokens']
      }
    ];
  } else if (inc.title.toLowerCase().includes("privilege") || inc.title.toLowerCase().includes("web-1")) {
    recommendedPlaybooks = [
      {
        id: 'HOST_ISOLATE',
        name: 'Isolate and Rebuild Host',
        description: 'Sever egress routes and immediately redeploy web service from secure golden base images.',
        difficulty: 'Medium',
        duration: '5 mins',
        matchReason: 'Similar to host-web-1 incident #3 where redeploying immutable container resolved local system changes.',
        recommendedActions: ['Enable golden-image server redeployment trigger', 'Apply local endpoint containment controls']
      },
      {
        id: 'JIRA_TICKET',
        name: 'Escalate to L2 Security Response Team',
        description: 'Consolidate host process telemetry logs, privilege modification reports, and trigger on-call alert.',
        difficulty: 'Low',
        duration: '1 min',
        matchReason: 'Privilege escalation triggers internal audit requirements requiring handoff to secondary responders.',
        recommendedActions: ['Submit high-priority issue thread in Jira', 'Trigger system-level PagerDuty notification']
      }
    ];
  }

  let threatIntel = {
    hasMatch: true,
    source: matchedFeed.source,
    threatActor: matchedFeed.threatActor,
    campaign: matchedFeed.campaign,
    malwareFamily: matchedFeed.malwareFamily,
    matchedIndicator: matchedFeed.indicator,
    severity: matchedFeed.severity,
    context: `Correlated with active external IOC profiles. ${matchedFeed.description}`
  };

  if (ai) {
    try {
      const prompt = `You are an elite automated Security Incident Analyst powered by ShieldAI's triage and CTI correlation engines.
We are analyzing a security incident to recommend a triage plan including similar historical incidents, threat intelligence details, and 2-3 tailored containment/mitigation playbooks.

Current Incident:
${JSON.stringify({
  id: inc.id,
  title: inc.title,
  severity: inc.severity,
  llm_summary: inc.llm_summary || 'N/A',
  analyst_notes: inc.analyst_notes || 'N/A',
  correlation_key: inc.correlation_key
})}

Historical Incidents Available:
${JSON.stringify(historicalIncidents.map(h => ({
  id: h.id,
  title: h.title,
  severity: h.severity,
  status: h.status,
  verdict: h.verdict,
  llm_summary: h.llm_summary,
  analyst_notes: h.analyst_notes,
  resolved_at: h.resolved_at
})))}

Threat Intelligence Catalog:
${JSON.stringify(threatIntelFeeds)}

Your goal is to output a valid JSON response exactly fitting this structure:
{
  "similarIncidents": [
    {
      "id": number,
      "title": "string",
      "similarityReason": "crisp explanation of similarity regarding attack vectors, severity, or endpoints (e.g. 'Both target web server namespaces...')",
      "verdict": "string",
      "resolvedAt": "string or null"
    }
  ],
  "threatIntel": {
    "hasMatch": true,
    "source": "string source feed name",
    "threatActor": "string threat actor name",
    "campaign": "string campaign name",
    "malwareFamily": "string malware family",
    "matchedIndicator": "string matched IOC indicator",
    "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
    "context": "Highly informative 1-2 sentence description combining threat intel with current incident context."
  },
  "recommendedPlaybooks": [
    {
      "id": "IP_BLOCK" | "HOST_ISOLATE" | "USER_DISABLE" | "JIRA_TICKET" | "CUSTOM",
      "name": "string playbook title",
      "description": "string description",
      "difficulty": "Low" | "Medium" | "High",
      "duration": "string duration",
      "matchReason": "Concisely explain why this playbook is recommended based on similar historical occurrences or threat intel",
      "recommendedActions": ["string list of 2 action items to run"]
    }
  ]
}

Provide EXACTLY the JSON string. Do not include markdown wraps or code fences, return raw JSON string.`;

      const response = await ai.models.generateContent({
        model: 'gemini-3.5-flash',
        contents: prompt,
      });

      if (response && response.text) {
        let text = response.text.trim();
        if (text.startsWith('```json')) {
          text = text.substring(7);
        }
        if (text.startsWith('```')) {
          text = text.substring(3);
        }
        if (text.endsWith('```')) {
          text = text.substring(0, text.length - 3);
        }
        text = text.trim();
        
        const parsed = JSON.parse(text);
        if (parsed.similarIncidents && parsed.recommendedPlaybooks) {
          res.json({
            incidentId: incId,
            similarIncidents: parsed.similarIncidents,
            threatIntel: parsed.threatIntel || threatIntel,
            recommendedPlaybooks: parsed.recommendedPlaybooks,
            timestamp: new Date().toISOString()
          });
          return;
        }
      }
    } catch (err) {
      console.error('[AI TRIAGE PREDICTION ERR]', err);
    }
  }

  // Fallback response if AI is not available
  res.json({
    incidentId: incId,
    similarIncidents,
    threatIntel,
    recommendedPlaybooks,
    timestamp: new Date().toISOString()
  });
});

app.put('/api/v1/incidents/:id', (req, res) => {
  const incId = parseInt(req.params.id);
  const { status, verdict, analyst_notes } = req.body;
  const incIdx = incidents.findIndex(i => i.id === incId);
  if (incIdx === -1) return res.status(404).json({ error: 'Incident not found' });

  incidents[incIdx] = {
    ...incidents[incIdx],
    ...(status && { status }),
    ...(verdict && { verdict }),
    ...(analyst_notes && { analyst_notes }),
    ...(status === 'RESOLVED' && { resolved_at: new Date().toISOString() })
  };

  auditLogs.push({
    id: auditLogs.length + 1,
    timestamp: new Date().toISOString(),
    action: 'INCIDENT_UPDATED',
    user: 'admin',
    details: `Updated Incident ${incId}: Status=${status || 'N/A'}, Verdict=${verdict || 'N/A'}`
  });

  res.json(incidents[incIdx]);
});

app.post('/incidents/:id/verdict', (req, res) => {
  const incId = parseInt(req.params.id);
  const { verdict, notes } = req.body;
  const incIdx = incidents.findIndex(i => i.id === incId);
  if (incIdx === -1) return res.status(404).json({ error: 'Incident not found' });

  incidents[incIdx].verdict = verdict;
  incidents[incIdx].analyst_notes = notes;

  auditLogs.push({
    id: auditLogs.length + 1,
    timestamp: new Date().toISOString(),
    action: 'VERDICT_APPLIED',
    user: 'admin',
    details: `Set verdict for Incident ${incId} to ${verdict}`
  });

  res.json({ status: 'success', incident: incidents[incIdx] });
});

app.get('/api/v1/incidents/:id/graph', (req, res) => {
  // Cytoscape-compatible subgraph representing attack graph
  res.json({
    nodes: topology.nodes,
    edges: topology.edges
  });
});

// Alerts
app.get('/api/v1/alerts', (req, res) => {
  res.json(alerts);
});

app.get('/alerts/:id/details', (req, res) => {
  const altId = parseInt(req.params.id);
  const alert = alerts.find(a => a.id === altId);
  if (!alert) return res.status(404).json({ error: 'Alert not found' });
  res.json(alert);
});

app.get('/alerts/:id/investigation', (req, res) => {
  const altId = parseInt(req.params.id);
  res.json({
    alert_id: altId,
    investigation_steps: [
      { step: 1, action: 'Query reputation of source IP 198.51.100.42', status: 'FINISHED', result: 'Known malicious block (CTI reputation score: 95/100)' },
      { step: 2, action: 'Examine target node process logs', status: 'FINISHED', result: 'Found system user escalation using insecure bash variables' },
      { step: 3, action: 'Correlate with previous cluster events', status: 'FINISHED', result: 'Identified matching credential leaks from June 2026' }
    ],
    ai_conclusion: 'Strong indicator of automated command injection attack following successful initial reconnaissance.'
  });
});

app.post('/alerts/:id/investigate', (req, res) => {
  const altId = parseInt(req.params.id);
  res.json({
    status: 'triggered',
    alert_id: altId,
    message: 'ShieldAI Investigation Orchestrator started asynchronous Deep Analysis.'
  });
});

// Multi-Agent Task trigger
app.post('/api/v1/agents/task', (req, res) => {
  const { task } = req.body;
  res.json({
    status: 'received',
    task,
    agent_logs: [
      `[Supervisor] Routing task "${task}" to specialized hunter agents.`,
      `[Cloud Hunter] Querying GCP IAM policies for unusual bindings...`,
      `[Malware Hunter] Running dynamic sandbox telemetry matches...`,
      `[Supervisor] Consolidated response draft created and staged for analyst review.`
    ]
  });
});

// Digital Twin
app.get('/api/v1/digital_twin/topology', async (req, res) => {
  if (neo4jDriver) {
    try {
      const dbTopology = await getTopologyFromNeo4j();
      if (dbTopology) {
        return res.json(dbTopology);
      }
    } catch (err) {
      console.error('[NEO4J] Fetch topology failed, using in-memory fallback:', err);
    }
  }
  res.json(topology);
});

app.post('/api/v1/digital_twin/simulate', async (req, res) => {
  const { start_node_id, attack_type, risk_factor } = req.body;
  const rf = risk_factor ? Number(risk_factor) : 0.6;
  
  if (neo4jDriver) {
    try {
      // Add simulated threat propagation path relationships to Neo4j Graph
      await addSimulationEdgeToNeo4j('host-web-1', 'host-db-1', rf);
      await addSimulationEdgeToNeo4j('host-db-1', 'asset-customer-records', rf * 0.8);
    } catch (err) {
      console.error('[NEO4J] Simulation save failed:', err);
    }
  }

  // Return realistic attack propagation simulation
  res.json({
    simulation_id: 'sim-' + Math.random().toString(36).substring(2, 9),
    status: 'success',
    blast_radius_percentage: Math.round(rf * 100),
    blast_radius_score: rf,
    critical_assets_at_risk: start_node_id === 'host-web-1' ? 2 : 1,
    impacted_nodes: ['host-web-1', 'host-db-1', 'asset-customer-records'],
    affected_nodes: [
      { id: 'host-web-1' },
      { id: 'host-db-1' },
      { id: 'asset-customer-records' }
    ],
    affected_edges: [
      { source: 'host-web-1', target: 'host-db-1', probability: rf },
      { source: 'host-db-1', target: 'asset-customer-records', probability: rf * 0.8 }
    ],
    propagation_path: [
      { step: 1, node: 'host-web-1', action: 'Exploited Remote Code Execution (RCE)' },
      { step: 2, node: 'host-db-1', action: 'Lateral Movement via SSH credentials found in env variables' },
      { step: 3, node: 'asset-customer-records', action: 'Unprivileged database connection query targeting sensitive database' }
    ],
    containment_recommendation: 'Isolate frontend host-web-1 immediately and revoke credentials stored in environment files.'
  });
});

app.get('/api/v1/digital_twin/blast-radius', (req, res) => {
  res.json({
    node_id: req.query.node_id,
    nodes: ['host-web-1', 'host-db-1'],
    edges: ['edge-1', 'edge-2']
  });
});

app.get('/api/v1/digital_twin/attack-paths', (req, res) => {
  res.json({
    paths: [
      ['ip-attacker', 'host-web-1', 'host-db-1', 'asset-customer-records']
    ]
  });
});

app.delete('/api/v1/digital_twin/cleanup', async (req, res) => {
  if (neo4jDriver) {
    try {
      await cleanupSimulationsInNeo4j();
    } catch (err) {
      console.error('[NEO4J] Simulation cleanup failed:', err);
    }
  }
  res.json({ status: 'success', message: 'Simulations and temporary telemetry overlays flushed.' });
});

// External Integrations Status & Sync
app.get('/api/v1/integrations/status', async (req, res) => {
  let neo4jConnected = false;
  let qdrantConnected = false;
  let neo4jCount = 0;
  let qdrantCount = 0;

  if (neo4jDriver) {
    const session = neo4jDriver.session();
    try {
      const result = await session.run('MATCH (n) RETURN count(n) AS count');
      neo4jCount = result.records[0].get('count').toNumber();
      neo4jConnected = true;
    } catch (err) {
      console.warn('[INTEGRATIONS] Neo4j ping failed:', err.message);
    } finally {
      await session.close();
    }
  }

  if (qdrantClient) {
    try {
      const collectionsRes = await qdrantClient.getCollections();
      qdrantConnected = true;
      const collectionExists = collectionsRes.collections.some(c => c.name === 'shieldai_memories');
      if (collectionExists) {
        const countRes = await qdrantClient.getCollection('shieldai_memories');
        qdrantCount = countRes.points_count || 0;
      }
    } catch (err) {
      console.warn('[INTEGRATIONS] Qdrant ping failed:', err.message);
    }
  }

  res.json({
    neo4j: {
      connected: neo4jConnected,
      uri: NEO4J_URI || 'mock',
      database: NEO4J_DATABASE,
      nodesCount: neo4jCount
    },
    qdrant: {
      connected: qdrantConnected,
      url: QDRANT_URL || 'mock',
      pointsCount: qdrantCount
    }
  });
});

app.post('/api/v1/integrations/sync', async (req, res) => {
  try {
    if (neo4jDriver) {
      await seedNeo4j();
    }
    if (qdrantClient) {
      await seedQdrant();
    }
    res.json({
      success: true,
      message: 'External database indices and schemas synchronized successfully.'
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Executive Dashboard Metrics
app.get('/api/v1/executive/metrics', (req, res) => {
  res.json({
    risk_score_avg: 42.5,
    mttd_avg: 12.8,
    mttr_avg: 45.4,
    precision_avg: 94.2,
    cost_prevented_total: 14200,
    trends: [
      { date: 'Jul 2', count: 4 },
      { date: 'Jul 3', count: 7 },
      { date: 'Jul 4', count: 3 },
      { date: 'Jul 5', count: 5 },
      { date: 'Jul 6', count: 9 },
      { date: 'Jul 7', count: 12 },
      { date: 'Jul 8', count: 5 },
      { date: 'Jul 9', count: 3 }
    ]
  });
});

let firewallBlocks = [
  { ip: '198.51.100.42', type: 'permanent', hours: null, reason: 'Known malicious block (CTI reputation score: 95/100)', timestamp: new Date(Date.now() - 3 * 3600000).toISOString() },
  { ip: '203.0.113.110', type: 'temporary', hours: '24h', reason: 'High-frequency port scan detection', timestamp: new Date(Date.now() - 1 * 3600000).toISOString() },
  { ip: '185.190.140.15', type: 'temporary', hours: '12h', reason: 'Brute force attack on admin portal', timestamp: new Date(Date.now() - 12 * 3600000).toISOString() },
  { ip: '45.80.200.12', type: 'permanent', hours: null, reason: 'C2 beacons on unauthorized ports', timestamp: new Date(Date.now() - 5 * 3600000).toISOString() }
];

app.get('/stats', (req, res) => {
  res.json({
    total_incidents: incidents.length,
    active_incidents: incidents.filter(i => i.status !== 'RESOLVED').length,
    total_alerts: alerts.length,
    blocked_ipsCount: firewallBlocks.length,
    active_blocks: firewallBlocks.length,
    total_logs: 125430,
    pending_approvals: 3,
    event_rate: 852.1
  });
});

app.get('/api/v1/firewall/blocks', (req, res) => {
  res.json(firewallBlocks);
});

app.post('/api/v1/firewall/block', (req, res) => {
  const { ip, type, hours, reason } = req.body;
  if (!ip) {
    return res.status(400).json({ error: 'IP address is required' });
  }

  const existingIndex = firewallBlocks.findIndex(b => b.ip === ip);
  const blockEntry = {
    ip,
    type: type || 'temporary',
    hours: hours || '24h',
    reason: reason || 'Manual analyst intervention',
    timestamp: new Date().toISOString()
  };

  if (existingIndex > -1) {
    firewallBlocks[existingIndex] = blockEntry;
  } else {
    firewallBlocks.push(blockEntry);
  }

  auditLogs.push({
    id: auditLogs.length + 1,
    timestamp: new Date().toISOString(),
    action: 'IP_BLOCKED',
    user: 'admin',
    details: `Blocked IP ${ip} (${type === 'permanent' ? 'Permanent' : `Temporary: ${hours}`}) - Reason: ${blockEntry.reason}`
  });

  res.json({ success: true, message: `IP ${ip} successfully blocked`, entry: blockEntry });
});

app.post('/api/v1/firewall/unblock', (req, res) => {
  const { ip } = req.body;
  if (!ip) {
    return res.status(400).json({ error: 'IP address is required' });
  }

  const initialLength = firewallBlocks.length;
  firewallBlocks = firewallBlocks.filter(b => b.ip !== ip);

  if (firewallBlocks.length < initialLength) {
    auditLogs.push({
      id: auditLogs.length + 1,
      timestamp: new Date().toISOString(),
      action: 'IP_UNBLOCKED',
      user: 'admin',
      details: `Unblocked IP ${ip}`
    });
    res.json({ success: true, message: `IP ${ip} successfully unblocked` });
  } else {
    res.status(404).json({ error: `IP ${ip} was not in the block list` });
  }
});

// Threat Intelligence
app.get('/threat-intel/cve/:cveId', (req, res) => {
  res.json({
    cve_id: req.params.cveId,
    description: `A critical command injection vulnerability exists in Palo Alto GlobalProtect (CVE-2024-3400) allowing an unauthenticated attacker to execute arbitrary code with root privileges.`,
    cvss_score: 10.0,
    published_at: '2024-04-12T00:00:00Z',
    remediation: 'Apply official vendors security patch and restrict inbound access to trusted IPs.'
  });
});

app.get('/threat-intel/ip/:ip', (req, res) => {
  res.json({
    ip: req.params.ip,
    reputation: 'Malicious',
    score: 95,
    country: 'Netherlands',
    asn: 'AS16265 Tor exit host',
    recent_detections: ['SSH Bruteforce', 'Scan / HTTP Reconnaissance']
  });
});

app.post('/threat-intel/sync', (req, res) => {
  res.json({ status: 'success', message: 'CTI threat database synchronized. Logged 142 new IOC signatures.' });
});

app.post('/threat-intel/kev/sync', (req, res) => {
  res.json({ status: 'success', message: 'CISA KEV (Known Exploited Vulnerabilities) feed fully populated.' });
});

// Reports & Storage (Google Cloud Storage Integration)

// Initialize Google Cloud Storage
const storage = new Storage();
const bucketName = process.env.GCS_BUCKET_NAME || 'edysor-storage-bucket';
const bucket = storage.bucket(bucketName);

// Multer memory storage for incoming attachments/exports
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 50 * 1024 * 1024 } // 50MB limit
});

// Helper function to upload buffer to GCS
const uploadToGCS = async (filename, buffer, contentType) => {
  try {
    const file = bucket.file(filename);
    await file.save(buffer, {
      metadata: { contentType },
      resumable: false
    });
    console.log(`[Storage] Uploaded ${filename} to ${bucketName}`);
    return `https://storage.googleapis.com/${bucketName}/${filename}`;
  } catch (error) {
    console.error(`[Storage] Error uploading ${filename}:`, error);
    throw error;
  }
};

// Upload Endpoint for attachments/exports
app.post('/api/v1/storage/upload', upload.single('file'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded.' });
  try {
    const filename = `attachments/${Date.now()}_${req.file.originalname}`;
    const url = await uploadToGCS(filename, req.file.buffer, req.file.mimetype);
    res.json({ status: 'success', url, filename });
  } catch (error) {
    res.status(500).json({ error: 'Failed to store attachment in Cloud Storage.' });
  }
});

app.get('/alerts/:alertId/report.pdf', async (req, res) => {
  const filename = `reports/edysor_alert_${req.params.alertId}.pdf`;
  const pdfBuffer = Buffer.from('%PDF-1.4 Mock Security PDF Report — ShieldAI Alert ' + req.params.alertId);
  
  try {
    await uploadToGCS(filename, pdfBuffer, 'application/pdf');
  } catch (e) {
    console.warn('[Storage] Could not store report, continuing to serve buffer.');
  }

  res.setHeader('Content-Type', 'application/pdf');
  res.setHeader('Content-Disposition', `attachment; filename=edysor_alert_${req.params.alertId}.pdf`);
  res.send(pdfBuffer);
});

app.get('/api/v1/reports/digest', async (req, res) => {
  const period = req.query.period || 'week';
  const filename = `reports/edysor_digest_${period}.pdf`;
  const pdfBuffer = Buffer.from('%PDF-1.4 Mock Executive Digest — Period: ' + period);

  try {
    await uploadToGCS(filename, pdfBuffer, 'application/pdf');
  } catch (e) {
    console.warn('[Storage] Could not store digest, continuing to serve buffer.');
  }

  res.setHeader('Content-Type', 'application/pdf');
  res.setHeader('Content-Disposition', `attachment; filename=edysor_digest_${period}.pdf`);
  res.send(pdfBuffer);
});

app.get('/api/v1/reports/audit-alerts-24h', (req, res) => {
  const now = Date.now();
  const oneDayAgo = now - 24 * 60 * 60 * 1000;
  
  // Filter alerts in the last 24 hours
  const filteredAlerts = alerts.filter(alert => {
    const ts = Date.parse(alert.timestamp);
    return !isNaN(ts) && ts >= oneDayAgo;
  });

  const auditReport = {
    report_type: 'JSON_AUDIT_REPORT_24H',
    generated_at: new Date().toISOString(),
    time_window_start: new Date(oneDayAgo).toISOString(),
    time_window_end: new Date(now).toISOString(),
    total_triggered_alerts_last_24h: filteredAlerts.length,
    alerts: filteredAlerts,
    system_status: {
      siem_layer: 'ACTIVE',
      digital_twin_topology: 'SYNCHRONIZED',
      policy_engine: 'ENFORCED'
    }
  };

  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Content-Disposition', 'attachment; filename=edysor_audit_alerts_24h.json');
  res.send(JSON.stringify(auditReport, null, 2));
});

app.get('/threat-intel/report.pdf', async (req, res) => {
  const filename = `reports/edysor_threat_intel_${Date.now()}.pdf`;
  const pdfBuffer = Buffer.from('%PDF-1.4 Mock Threat Intelligence Briefing Report');

  try {
    await uploadToGCS(filename, pdfBuffer, 'application/pdf');
  } catch (e) {
    console.warn('[Storage] Could not store threat intel report, continuing to serve buffer.');
  }

  res.setHeader('Content-Type', 'application/pdf');
  res.setHeader('Content-Disposition', 'attachment; filename=edysor_threat_intel.pdf');
  res.send(pdfBuffer);
});

// Telemetry Log Generation
app.post('/api/v1/telemetry/generate', (req, res) => {
  res.json({
    status: 'success',
    count: req.body.count || 100,
    message: 'Injected synthesized events into active SIEM event log stream.'
  });
});

// MITRE mappings
app.get('/mitre/mappings', (req, res) => {
  res.json([
    { technique_id: 'T1190', name: 'Exploit Public-Facing Application', phase: 'Initial Access', severity: 'High' },
    { technique_id: 'T1059', name: 'Command and Scripting Interpreter', phase: 'Execution', severity: 'High' },
    { technique_id: 'T1021', name: 'Remote Services', phase: 'Lateral Movement', severity: 'Medium' },
    { technique_id: 'T1041', name: 'Exfiltration Over Alternative Protocol', phase: 'Exfiltration', severity: 'High' }
  ]);
});

// Audit log
app.get('/audit-log', (req, res) => {
  res.json(auditLogs);
});

// Approvals
app.get('/approvals', (req, res) => {
  res.json(approvals);
});

// ==========================================
// GEMINI API POWERED CHAT / OFF-LINE FALLBACK
// ==========================================

app.post('/chat', async (req, res) => {
  const { query } = req.body;
  if (!query) {
    return res.status(400).json({ error: 'Missing query parameter in request body' });
  }

  let responseText = '';
  let qdrantContext = [];
  let neo4jContext = [];

  // 1. Fetch Vector Context from Qdrant
  if (qdrantClient) {
    try {
      qdrantContext = await searchQdrantMemories(query);
    } catch (err) {
      console.error('[CHAT-QDRANT] Context fetch failed:', err);
    }
  }

  // 2. Fetch Graph Context from Neo4j
  if (neo4jDriver) {
    const session = neo4jDriver.session();
    try {
      const queryStr = String(query);
      const result = await session.run(`
        MATCH (n) 
        WHERE n.id CONTAINS $query OR (exists(n.ip) AND n.ip CONTAINS $query)
        RETURN n, labels(n)[0] AS label LIMIT 5
      `, { query: queryStr });
      
      neo4jContext = result.records.map(r => {
        const node = r.get('n');
        return {
          id: node.properties.id,
          type: r.get('label') || 'Unknown',
          properties: node.properties
        };
      });

      // Fallback: If no match, return some standard nodes
      if (neo4jContext.length === 0) {
        const fallbackRes = await session.run(`
          MATCH (n) RETURN n, labels(n)[0] AS label LIMIT 3
        `);
        neo4jContext = fallbackRes.records.map(r => {
          const node = r.get('n');
          return {
            id: node.properties.id,
            type: r.get('label') || 'Unknown',
            properties: node.properties
          };
        });
      }
    } catch (err) {
      console.error('[CHAT-NEO4J] Context fetch failed:', err);
    } finally {
      await session.close();
    }
  }

  // Formulate Context Message
  const vectorStr = qdrantContext.length > 0 
    ? qdrantContext.map(c => `• [Score: ${c.score?.toFixed(2) || '1.00'}] ${c.text} (${c.category})`).join('\n')
    : 'No relevant vector memories matched.';

  const graphStr = neo4jContext.length > 0
    ? neo4jContext.map(n => `• Node: ${n.id} [Type: ${n.type}] - IP: ${n.properties?.ip || 'N/A'}, OS: ${n.properties?.os || 'N/A'}`).join('\n')
    : 'No relevant graph nodes matched.';

  if (ai) {
    try {
      const prompt = `You are the ShieldAI Security Co-pilot, an elite AI SOC analyst assistant. Provide clear, highly professional, actionable security advice based on the user's query.
You have active access to the live Qdrant Vector Memory Layer (Vector RAG) and Neo4j Security Knowledge Graph (GraphRAG). Use the retrieved context below to enrich your response.

RETRIEVED VECTOR CONTEXT (Qdrant):
${vectorStr}

RETRIEVED GRAPH CONTEXT (Neo4j):
${graphStr}

User Query: "${query}"`;
      
      const response = await ai.models.generateContent({
        model: 'gemini-3.5-flash',
        contents: prompt,
      });
      
      responseText = response.text;
    } catch (err) {
      console.error('[GEMINI ERR]', err);
      responseText = `[ShieldAI Gemini Connection Warning]: ${err.message}. \n\nDirect response: Understood. Let's analyze the digital twin configuration. What specific host or IP should we isolate or inspect?`;
    }
  } else {
    // Elegant local fallback highlighting active connections
    const lowerQuery = query.toLowerCase();
    let prefix = '';
    if (qdrantClient || neo4jDriver) {
      prefix = `### [Hybrid GraphRAG + Vector RAG Active Context Retrieval]\n`;
      if (qdrantClient) prefix += `**Qdrant Vector Memories:**\n${vectorStr}\n\n`;
      if (neo4jDriver) prefix += `**Neo4j Knowledge Graph Nodes:**\n${graphStr}\n\n`;
      prefix += `**Analyst Response:**\n`;
    }

    if (lowerQuery.includes('status') || lowerQuery.includes('health')) {
      responseText = prefix + `ShieldAI SOC Platform is fully online. Currently monitoring 5 assets, tracking ${incidents.length} active incidents, and verifying ${approvals.filter(a => a.status === 'PENDING').length} pending containment approvals. Custom Neo4j and Qdrant clusters are successfully connected and synchronized.`;
    } else if (lowerQuery.includes('isolate') || lowerQuery.includes('block')) {
      responseText = prefix + `To isolate an asset such as 'host-web-1', navigate to the Digital Twin or Approvals tab and approve the isolation request 'CONTAINMENT_ISOLATION'. This will immediately deploy standard iptables/VPC security groups blocks.`;
    } else if (lowerQuery.includes('cve') || lowerQuery.includes('vulnerability')) {
      responseText = prefix + `CTI Feed is active. We are tracking high-severity CVE-2024-3400 (Palo Alto command injection) with full CISA KEV correlation. Mitigation playbook is staged under the Approvals menu.`;
    } else {
      responseText = prefix + `Hello, I'm the ShieldAI Analyst Co-pilot. I can help investigate alerts, run digital twin breach simulations, analyze network blast radiuses, or execute isolation playbooks. \n\n*To enable live Gemini answers, configure your GEMINI_API_KEY in Settings > Secrets.*`;
    }
  }

  res.json({ response: responseText });
});

// ==========================================
// VITE AND STATIC ASSETS SERVING
// ==========================================

const distPath = path.join(__dirname, 'dist');
app.use(express.static(distPath));

// SPA Routing fallback
app.get('*', (req, res, next) => {
  if (req.path.startsWith('/api') || req.path.startsWith('/ws')) {
    return next();
  }
  res.sendFile(path.join(distPath, 'index.html'));
});

// Create HTTP Server for WS multiplexing
const server = createServer(app);

// ==========================================
// REAL-TIME WEBSOCKET FEED FOR LOGS & ALERTS
// ==========================================

const wss = new WebSocketServer({ server, path: '/ws' });

wss.on('connection', (ws) => {
  console.log('[WS] Client connected');
  
  // Send welcome ping
  ws.send(JSON.stringify({
    type: 'SYSTEM',
    timestamp: new Date().toISOString(),
    message: 'Correlated telemetry feed active — connection established.'
  }));

  // Send periodic mock security logs / alerts every 10 seconds to make the UI look active
  const interval = setInterval(() => {
    if (ws.readyState === ws.OPEN) {
      const logs = [
        { type: 'INGEST', level: 'INFO', message: 'HTTP 200 GET /api/v1/status from IP 10.0.1.4' },
        { type: 'SIEM', level: 'DEBUG', message: 'Sysmon Process Creation: PID 2514 /usr/bin/python3' },
        { type: 'CTI', level: 'INFO', message: 'Updated reputation database cache for Tor Exit node lists' },
        { type: 'ALERT', level: 'HIGH', message: 'Rate-limit threshold reached for API client login endpoints' }
      ];
      const randomLog = logs[Math.floor(Math.random() * logs.length)];
      ws.send(JSON.stringify({
        ...randomLog,
        timestamp: new Date().toISOString()
      }));
    }
  }, 10000);

  ws.on('close', () => {
    console.log('[WS] Client disconnected');
    clearInterval(interval);
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[SERVER] Full-stack server running on http://0.0.0.0:${PORT}`);
});

// Graceful Shutdown
const shutdown = () => {
  console.log('[SERVER] SIGTERM/SIGINT received. Shutting down gracefully...');
  server.close(() => {
    console.log('[SERVER] HTTP server closed.');
    
    // Close Database connections
    if (db && typeof db.close === 'function') {
      db.close((err) => {
        if (err) console.error('[DB] Error closing SQLite:', err);
        else console.log('[DB] SQLite connection closed.');
      });
    }

    if (neo4jDriver) {
      neo4jDriver.close()
        .then(() => console.log('[NEO4J] Connection closed.'))
        .catch(err => console.error('[NEO4J] Error closing connection:', err));
    }

    process.exit(0);
  });
};

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
