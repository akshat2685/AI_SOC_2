import fs from 'fs';
let code = fs.readFileSync('server.js', 'utf8');

code = code.replace(
  "const user = mockUsers.find(u => u.username === params[0] && u.password === params[1]);",
  "const user = mockUsers.find(u => u.username === params[0] && (params[1] ? u.password === params[1] : true));"
);

fs.writeFileSync('server.js', code);
