import fs from 'fs';
let css = fs.readFileSync('frontend/src/app/globals.css', 'utf8');

const newCSS = `
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@800&family=Space+Mono:wght@400;700&family=Inter:wght@400;500&display=swap');

:root {
  --bg: #0d0d0f;
  --ink: #f0f0f2;
  --accent: #3b82f6;
  --ink-faint: rgba(240, 240, 242, 0.1);
  --ink-muted: rgba(240, 240, 242, 0.5);
}

.login-view-wrapper {
  background-color: var(--bg);
  color: var(--ink);
  font-family: 'Inter', sans-serif;
  height: 100vh;
  width: 100vw;
  display: grid;
  place-items: center;
  background-image: 
      radial-gradient(circle at 2px 2px, var(--ink-faint) 1px, transparent 0);
  background-size: 32px 32px;
  position: fixed;
  top: 0;
  left: 0;
  z-index: 100;
}

.login-view-wrapper .container {
  display: grid;
  grid-template-columns: 1fr;
  width: 100%;
  max-width: 480px;
  padding: 2rem;
  position: relative;
}

.login-view-wrapper .header {
  margin-bottom: 3.5rem;
  position: relative;
}

.login-view-wrapper .label-meta {
  font-family: 'Space Mono', monospace;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--accent);
  margin-bottom: 0.5rem;
  display: block;
}

.login-view-wrapper h1 {
  font-family: 'Syne', sans-serif;
  font-size: clamp(2.5rem, 5vw, 3.5rem);
  line-height: 0.9;
  letter-spacing: -0.04em;
  text-transform: uppercase;
  margin-bottom: 1rem;
}

.login-view-wrapper .description {
  font-size: 0.85rem;
  color: var(--ink-muted);
  line-height: 1.6;
  border-left: 2px solid var(--accent);
  padding-left: 1rem;
}

.login-view-wrapper .login-card {
  background: #151518;
  border: 1px solid var(--ink-faint);
  padding: 2.5rem;
  border-radius: 4px;
}

.login-view-wrapper .field-group {
  margin-bottom: 1.5rem;
}

.login-view-wrapper label {
  display: block;
  font-family: 'Space Mono', monospace;
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-muted);
  margin-bottom: 0.75rem;
}

.login-view-wrapper input {
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--ink-faint);
  padding: 0.75rem 0;
  color: var(--ink);
  font-family: 'Space Mono', monospace;
  font-size: 0.9rem;
  transition: border-color 0.2s ease;
}

.login-view-wrapper input:focus {
  outline: none;
  border-color: var(--accent);
}

.login-view-wrapper button[type="submit"] {
  width: 100%;
  background: var(--accent);
  color: white;
  border: none;
  padding: 1.25rem;
  font-family: 'Space Mono', monospace;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  cursor: pointer;
  margin-top: 1rem;
  transition: filter 0.2s ease;
}

.login-view-wrapper button[type="submit"]:hover {
  filter: brightness(1.1);
}

.login-view-wrapper .secondary-btn {
  display: block;
  width: 100%;
  background: transparent;
  border: 1px solid var(--ink-faint);
  color: var(--ink-muted);
  padding: 0.75rem;
  font-size: 0.7rem;
  margin-top: 1rem;
  cursor: pointer;
  text-align: center;
  text-decoration: none;
}

.login-view-wrapper .secondary-btn:hover {
  color: var(--ink);
  border-color: var(--ink-muted);
}

.login-view-wrapper .footer-deco {
  position: fixed;
  bottom: 2rem;
  left: 2rem;
  right: 2rem;
  display: flex;
  justify-content: space-between;
  font-family: 'Space Mono', monospace;
  font-size: 0.6rem;
  color: var(--ink-faint);
  text-transform: uppercase;
  letter-spacing: 0.2em;
  pointer-events: none;
}
`;

fs.writeFileSync('frontend/src/app/globals.css', css + '\n\n' + newCSS);
