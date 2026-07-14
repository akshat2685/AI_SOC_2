import fs from 'fs';
let code = fs.readFileSync('frontend/src/components/DashboardShell.tsx', 'utf8');

const oldLoginReturn = `    return (
      <div className="min-h-screen bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-900 via-zinc-950 to-black text-white flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-slate-900/60 backdrop-blur-xl border border-slate-800 p-8 rounded-2xl shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-600"></div>
          
          <div className="flex flex-col items-center mb-8">
            <div className="w-14 h-14 bg-gradient-to-tr from-blue-600 to-indigo-500 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/20 mb-3">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
              EDYSOR AI-SOC
            </h1>
            <p className="text-sm text-slate-400 mt-1">Autonomous Detection & Response</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Username</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500/80 transition-all text-white"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500/80 transition-all text-white"
                required
              />
            </div>
            {loginError && (
              <div className="text-xs bg-red-950/40 border border-red-800/80 text-red-400 px-4 py-3 rounded-xl">
                {loginError}
              </div>
            )}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold py-3 rounded-xl transition-all shadow-lg shadow-indigo-600/20 active:scale-[0.98] disabled:opacity-50"
            >
              {loading ? 'Authenticating...' : (isRegistering ? 'Create Account & Sign In' : 'Sign In')}
            </button>
            <div className="text-center pt-3">
              <button
                type="button"
                onClick={() => {
                  setIsRegistering(!isRegistering);
                  setLoginError('');
                }}
                className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold focus:outline-none transition-all"
              >
                {isRegistering ? 'Already have an account? Sign In' : "Don't have an account? Register Now"}
              </button>
            </div>
          </form>
        </div>
      </div>
    );`;

const newLoginReturn = `    return (
      <div className="login-view-wrapper">
        <div className="container">
          <header className="header">
            <span className="label-meta">[ SYST.OPERATIONS ]</span>
            <h1>EDYSOR AI-SOC</h1>
            <p className="description">Autonomous Detection &amp; Response. Secured gateway for authorized tactical personnel only.</p>
          </header>

          <main className="login-card">
            <form onSubmit={handleLogin} className="space-y-4">
                <div className="field-group">
                    <label>Username / Access Key</label>
                    <input 
                      type="text" 
                      value={username}
                      onChange={e => setUsername(e.target.value)}
                      required 
                    />
                </div>
                <div className="field-group">
                    <label>Password / Token</label>
                    <input 
                      type="password" 
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      required 
                    />
                </div>
                {loginError && (
                  <div style={{ color: '#ef4444', fontSize: '0.75rem', fontFamily: 'Space Mono, monospace', marginTop: '0.5rem', marginBottom: '0.5rem' }}>
                    [ERROR] {loginError}
                  </div>
                )}
                <button type="submit" disabled={loading}>
                  {loading ? 'Authenticating...' : (isRegistering ? 'Create Account & Sign In' : 'Sign In to Shell')}
                </button>
                <button 
                  type="button" 
                  onClick={() => {
                    setIsRegistering(!isRegistering);
                    setLoginError('');
                  }}
                  className="secondary-btn"
                >
                  {isRegistering ? 'Already have an account? Sign In' : "Don't have an account? Register Now"}
                </button>
            </form>
          </main>
        </div>

        <div className="footer-deco">
            <span>SOC_V.042 // SHIELDAI</span>
            <span>LAT: 37.7749 N // LONG: 122.4194 W</span>
        </div>
      </div>
    );`;

if (!code.includes("login-view-wrapper")) {
  code = code.replace(oldLoginReturn, newLoginReturn);
  fs.writeFileSync('frontend/src/components/DashboardShell.tsx', code);
  console.log("Patched successfully!");
} else {
  console.log("Already patched.");
}
