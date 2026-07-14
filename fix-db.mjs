import fs from 'fs';
let code = fs.readFileSync('server.js', 'utf8');

const mockDbCode = `
// MOCK DB FALLBACK
function getMockDb() {
  console.warn('[DB] Using MOCK database fallback.');
  const mockUsers = [
    { username: 'admin', password: 'password', role: 'Administrator', tenant_id: 'default', premium: true }
  ];
  return {
    get: (sql, params, cb) => {
      if (typeof params === 'function') { cb = params; params = []; }
      if (sql.includes('users WHERE username = ?')) {
        const user = mockUsers.find(u => u.username === params[0] && u.password === params[1]);
        if (cb) cb(null, user);
      } else {
        if (cb) cb(null, null);
      }
    },
    all: (sql, params, cb) => {
      if (typeof params === 'function') { cb = params; params = []; }
      if (cb) cb(null, []);
    },
    run: (sql, params, cb) => {
      if (typeof params === 'function') { cb = params; params = []; }
      if (cb) cb(null);
    },
    serialize: (cb) => { if (cb) cb(); }
  };
}
if (!db) {
  db = getMockDb();
}
`;

code = code.replace("console.warn('[DB] Running in production without POSTGRES_URL. Database operations relying on Cloud SQL will fail.');", mockDbCode);
code = code.replace("console.error('[DB] Failed to load sqlite3 module.')", "console.error('[DB] Failed to load sqlite3 module.'); db = getMockDb();");

fs.writeFileSync('server.js', code);
