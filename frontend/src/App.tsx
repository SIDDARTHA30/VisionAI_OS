import React, { useState } from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { GlassCard } from './components/GlassCard';
import { 
  Sun, Moon, Shield, User as UserIcon, LogOut, Terminal, 
  Settings, Cpu, FileText, Code, Globe, MessageSquare, Video, Mic
} from 'lucide-react';

const DashboardShell: React.FC = () => {
  const { user, logout } = useAuth();
  const [darkMode, setDarkMode] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<string>('dashboard');

  const toggleTheme = () => {
    setDarkMode(!darkMode);
    if (!darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  };

  const navItems = [
    { id: 'dashboard', label: 'Overview', icon: Cpu },
    { id: 'chat', label: 'AI Assistant', icon: MessageSquare },
    { id: 'vision', label: 'Vision Stream', icon: Video },
    { id: 'voice', label: 'Voice Command', icon: Mic },
    { id: 'automation', label: 'Automation', icon: Terminal },
    { id: 'settings', label: 'System Settings', icon: Settings },
  ];

  return (
    <div className={`min-h-screen font-sans flex brand-grad-bg transition-colors duration-300 ${darkMode ? 'dark' : ''}`}>
      {/* Sidebar Navigation */}
      <aside className="w-64 glass-panel border-r border-border-light dark:border-border-dark flex flex-col justify-between m-4 rounded-2xl shadow-xl z-20">
        <div>
          {/* Logo / Header */}
          <div className="p-6 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-indigo to-brand-violet flex items-center justify-center shadow-lg shadow-brand-indigo/35">
              <Cpu className="text-white w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 bg-clip-text text-transparent">
                VisionAI OS
              </h1>
              <span className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold">Core Panel</span>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="px-4 space-y-1">
            {navItems.map((item) => {
              const IconComponent = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 text-sm font-medium ${
                    isActive 
                      ? 'bg-gradient-to-r from-brand-indigo to-brand-violet text-white shadow-lg shadow-brand-indigo/25' 
                      : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-100'
                  }`}
                >
                  <IconComponent className="w-5 h-5" />
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Profile Card / Footer */}
        <div className="p-4 border-t border-border-light dark:border-border-dark">
          <div className="flex items-center gap-3 p-2 rounded-xl bg-slate-100/50 dark:bg-slate-800/40">
            <div className="w-9 h-9 rounded-full bg-brand-violet/20 flex items-center justify-center text-brand-violet font-semibold text-sm">
              {user?.name.slice(0, 2).toUpperCase() || 'US'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold truncate text-slate-700 dark:text-slate-300">{user?.name}</p>
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                <span className="text-[10px] text-slate-400 capitalize">{user?.role}</span>
              </div>
            </div>
            <button 
              onClick={logout}
              className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-all"
              title="Logout"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Panel Area */}
      <main className="flex-1 flex flex-col p-4 pl-0">
        {/* Top Navbar */}
        <header className="h-16 glass-panel flex items-center justify-between px-6 rounded-2xl shadow-md mb-4 border border-border-light dark:border-border-dark">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-400">System Path:</span>
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200 capitalize">
              {activeTab}
            </span>
          </div>

          <div className="flex items-center gap-4">
            {/* Status Indicators */}
            <div className="hidden md:flex items-center gap-4 text-xs font-medium border-r border-border-light dark:border-border-dark pr-4">
              <div className="flex items-center gap-1.5 text-emerald-500">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                PostgreSQL
              </div>
              <div className="flex items-center gap-1.5 text-emerald-500">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                Redis
              </div>
              <div className="flex items-center gap-1.5 text-slate-400">
                <span className="w-2 h-2 rounded-full bg-slate-400"></span>
                Gemini
              </div>
            </div>

            {/* Dark/Light mode toggle */}
            <button
              onClick={toggleTheme}
              className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all duration-200"
            >
              {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
          </div>
        </header>

        {/* Dynamic Pages Contents */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === 'dashboard' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Stat card 1 */}
              <GlassCard className="col-span-1 border border-border-light dark:border-border-dark flex flex-col gap-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-400 font-semibold uppercase tracking-wider">AI Operations</span>
                  <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-500">
                    <Cpu className="w-6 h-6" />
                  </div>
                </div>
                <div>
                  <h3 className="text-3xl font-extrabold text-slate-800 dark:text-slate-100">Active</h3>
                  <p className="text-xs text-slate-400 mt-1">Status OK. Systems idling.</p>
                </div>
              </GlassCard>

              {/* Stat card 2 */}
              <GlassCard className="col-span-1 border border-border-light dark:border-border-dark flex flex-col gap-4" delay={0.1}>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-400 font-semibold uppercase tracking-wider">Storage & Logs</span>
                  <div className="p-2 rounded-lg bg-purple-500/10 text-purple-500">
                    <FileText className="w-6 h-6" />
                  </div>
                </div>
                <div>
                  <h3 className="text-3xl font-extrabold text-slate-800 dark:text-slate-100">0 Documents</h3>
                  <p className="text-xs text-slate-400 mt-1">Vector DB initialized.</p>
                </div>
              </GlassCard>

              {/* Stat card 3 */}
              <GlassCard className="col-span-1 border border-border-light dark:border-border-dark flex flex-col gap-4" delay={0.2}>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-400 font-semibold uppercase tracking-wider">Network Ports</span>
                  <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-500">
                    <Globe className="w-6 h-6" />
                  </div>
                </div>
                <div>
                  <h3 className="text-3xl font-extrabold text-slate-800 dark:text-slate-100">2 Connected</h3>
                  <p className="text-xs text-slate-400 mt-1">CORS & security proxies active.</p>
                </div>
              </GlassCard>

              {/* Main dashboard widgets */}
              <GlassCard className="md:col-span-2 border border-border-light dark:border-border-dark" delay={0.3}>
                <h3 className="text-lg font-bold mb-4 bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
                  System Overview
                </h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed mb-4">
                  Welcome to **VisionAI OS** core control desk. This platform orchestrates real-time desktop inputs, camera tracking, database indexes, and conversational modules. Initialize modules using the navigation menu on the left.
                </p>
                <div className="border border-border-light dark:border-border-dark rounded-xl p-4 bg-slate-50/50 dark:bg-slate-900/35">
                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">Core Settings</h4>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div>
                      <span className="text-slate-400">Environment:</span>
                      <span className="ml-2 font-medium text-slate-700 dark:text-slate-300">Development</span>
                    </div>
                    <div>
                      <span className="text-slate-400">Database Engine:</span>
                      <span className="ml-2 font-medium text-slate-700 dark:text-slate-300">PostgreSQL (Async)</span>
                    </div>
                    <div>
                      <span className="text-slate-400">Security Model:</span>
                      <span className="ml-2 font-medium text-slate-700 dark:text-slate-300">RBAC (Roles Assigned)</span>
                    </div>
                    <div>
                      <span className="text-slate-400">Cache Server:</span>
                      <span className="ml-2 font-medium text-slate-700 dark:text-slate-300">Redis active</span>
                    </div>
                  </div>
                </div>
              </GlassCard>

              {/* Quick actions panel */}
              <GlassCard className="col-span-1 border border-border-light dark:border-border-dark" delay={0.4}>
                <h3 className="text-md font-bold mb-4">Quick Shortcuts</h3>
                <div className="space-y-3">
                  <button className="w-full flex items-center justify-between p-3 rounded-xl border border-border-light dark:border-border-dark bg-slate-50/20 hover:bg-slate-100/50 dark:hover:bg-slate-800/40 transition-all text-xs font-medium">
                    <span className="flex items-center gap-2"><Code className="w-4 h-4 text-indigo-500" /> Explain Code Snippet</span>
                    <span className="text-[10px] bg-indigo-500/10 text-indigo-500 px-1.5 py-0.5 rounded-full uppercase">AI</span>
                  </button>
                  <button className="w-full flex items-center justify-between p-3 rounded-xl border border-border-light dark:border-border-dark bg-slate-50/20 hover:bg-slate-100/50 dark:hover:bg-slate-800/40 transition-all text-xs font-medium">
                    <span className="flex items-center gap-2"><Globe className="w-4 h-4 text-purple-500" /> Start Playwright Job</span>
                    <span className="text-[10px] bg-purple-500/10 text-purple-500 px-1.5 py-0.5 rounded-full uppercase">Task</span>
                  </button>
                  <button className="w-full flex items-center justify-between p-3 rounded-xl border border-border-light dark:border-border-dark bg-slate-50/20 hover:bg-slate-100/50 dark:hover:bg-slate-800/40 transition-all text-xs font-medium">
                    <span className="flex items-center gap-2"><Video className="w-4 h-4 text-cyan-500" /> Start Webcam Monitor</span>
                    <span className="text-[10px] bg-cyan-500/10 text-cyan-500 px-1.5 py-0.5 rounded-full uppercase">Vision</span>
                  </button>
                </div>
              </GlassCard>
            </div>
          )}

          {activeTab !== 'dashboard' && (
            <GlassCard className="border border-border-light dark:border-border-dark h-[500px] flex items-center justify-center text-center">
              <div>
                <Cpu className="w-12 h-12 text-brand-indigo/60 mx-auto mb-4 animate-pulse" />
                <h3 className="text-lg font-bold mb-2 capitalize">{activeTab} Module</h3>
                <p className="text-sm text-slate-400 max-w-sm">
                  This core module is bootstrapped and ready. Implementing specific business logic interfaces in the next project cycles.
                </p>
              </div>
            </GlassCard>
          )}
        </div>
      </main>
    </div>
  );
};

const AuthGate: React.FC = () => {
  const { isAuthenticated, isLoading, login, signup } = useAuth();
  const [isRegister, setIsRegister] = useState<boolean>(false);
  
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [name, setName] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string>('');

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0f172a] brand-grad-bg">
        <div className="flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-full border-4 border-slate-700 border-t-indigo-500 animate-spin"></div>
          <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Syncing System...</span>
        </div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <DashboardShell />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    try {
      if (isRegister) {
        await signup(name, email, password);
        setIsRegister(false);
        alert('Registration successful! Please login.');
      } else {
        await login(email, password);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'An error occurred');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#0f172a] brand-grad-bg">
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-20">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full bg-indigo-500 blur-3xl"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 rounded-full bg-purple-500 blur-3xl"></div>
      </div>

      <GlassCard className="w-full max-w-md border border-slate-800 bg-slate-900/60 shadow-2xl relative z-10 p-8 rounded-2xl">
        <div className="flex flex-col items-center mb-6">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-brand-indigo to-brand-violet flex items-center justify-center shadow-lg shadow-brand-indigo/35 mb-3">
            <Cpu className="text-white w-7 h-7" />
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-white font-sans">
            {isRegister ? 'Create Account' : 'Welcome to VisionAI OS'}
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            {isRegister ? 'Sign up to register a new credentials profile' : 'Enter credentials to access the terminal panel'}
          </p>
        </div>

        {errorMsg && (
          <div className="p-3 mb-4 rounded-xl border border-red-500/20 bg-red-500/10 text-red-400 text-xs font-medium flex items-center gap-2">
            <Shield className="w-4 h-4 flex-shrink-0" />
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {isRegister && (
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5">Full Name</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl text-sm border border-slate-700 bg-slate-800/40 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                placeholder="Ex. John Doe"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5">Email Address</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl text-sm border border-slate-700 bg-slate-800/40 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl text-sm border border-slate-700 bg-slate-800/40 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            className="w-full py-2.5 rounded-xl bg-gradient-to-r from-brand-indigo to-brand-violet hover:from-indigo-600 hover:to-purple-600 text-white font-medium text-sm shadow-lg shadow-brand-indigo/25 hover:shadow-brand-indigo/35 transition-all duration-200 mt-2 flex items-center justify-center gap-2"
          >
            {isRegister ? <UserIcon className="w-4 h-4" /> : <Shield className="w-4 h-4" />}
            {isRegister ? 'Sign Up' : 'Authenticate Credentials'}
          </button>
        </form>

        <div className="mt-6 text-center text-xs">
          <button
            onClick={() => {
              setIsRegister(!isRegister);
              setErrorMsg('');
            }}
            className="text-slate-400 hover:text-indigo-400 font-medium transition-all"
          >
            {isRegister ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
          </button>
        </div>
      </GlassCard>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
  );
}

export default App;
