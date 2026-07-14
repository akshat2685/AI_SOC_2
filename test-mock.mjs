import fs from 'fs';
const mockUsers = [
  { username: 'admin', password: 'password', role: 'Administrator', tenant_id: 'default', premium: true }
];
const params = ['admin', 'password'];
const user = mockUsers.find(u => u.username === params[0] && (params[1] ? u.password === params[1] : true));
console.log(user);
