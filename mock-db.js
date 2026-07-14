export function createMockDb() {
  console.warn('[DB] Using MOCK database since no real database is configured.');
  
  const mockUsers = [
    { username: 'admin', password: 'password', role: 'Administrator', tenant_id: 'default', premium: true }
  ];

  return {
    get: (sql, params, cb) => {
      if (sql.includes('users WHERE username = ?')) {
        const user = mockUsers.find(u => u.username === params[0] && u.password === params[1]);
        if (cb) cb(null, user);
      } else {
        if (cb) cb(null, null);
      }
    },
    all: (sql, params, cb) => {
      if (typeof params === 'function') {
        cb = params;
        params = [];
      }
      if (cb) cb(null, []);
    },
    run: (sql, params, cb) => {
      if (typeof params === 'function') {
        cb = params;
        params = [];
      }
      if (cb) cb(null);
    },
    serialize: (cb) => {
      cb();
    }
  };
}
