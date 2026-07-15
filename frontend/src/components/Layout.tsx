import { useEffect, useState } from 'react';
import { Outlet, Navigate, useNavigate, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Building2, FileText, Files, LogOut } from 'lucide-react';
import { isAuthenticated, removeToken } from '../lib/auth';
import api from '../lib/api';

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<{nome: string, email: string} | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      setLoading(false);
      return;
    }
    
    api.get('/auth/me')
      .then(res => {
        setUser(res.data);
        setLoading(false);
      })
      .catch(() => {
        removeToken();
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div className="min-h-screen bg-bg flex items-center justify-center font-bold text-muted">Carregando...</div>;
  }

  if (!isAuthenticated() || !user) {
    return <Navigate to="/login" replace />;
  }

  const handleLogout = () => {
    removeToken();
    navigate('/login');
  };

  const navItems = [
    { name: 'Dashboard', path: '/', icon: <LayoutDashboard size={18} /> },
    { name: 'Empresas', path: '/empresas', icon: <Building2 size={18} /> },
    { name: 'Emitir Nota', path: '/emitir', icon: <FileText size={18} /> },
    { name: 'Documentos', path: '/documentos', icon: <Files size={18} /> },
  ];

  return (
    <div className="min-h-screen bg-bg flex flex-col md:flex-row">
      {/* Sidebar */}
      <aside className="w-full md:w-64 bg-card border-r border-line flex flex-col shrink-0">
        <div className="p-6 border-b border-line">
          <div className="text-xl font-extrabold text-i9 tracking-tight flex items-center gap-1">
            i9<span className="text-gold">·</span><small className="text-ink font-bold">InnoNFe</small>
          </div>
        </div>
        
        <nav className="flex-1 p-4 flex flex-col gap-1">
          {navItems.map(item => {
            const isActive = location.pathname === item.path;
            return (
              <Link 
                key={item.path} 
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-semibold transition-colors ${isActive ? 'bg-i9-tint text-i9-dark' : 'text-muted hover:bg-line-soft hover:text-ink'}`}
              >
                {item.icon}
                {item.name}
              </Link>
            )
          })}
        </nav>
        
        <div className="p-4 border-t border-line">
          <div className="flex items-center gap-3 mb-4 px-2">
            <div className="w-8 h-8 rounded-full bg-i9-tint flex items-center justify-center text-i9 font-bold text-sm">
              {user.nome.charAt(0).toUpperCase()}
            </div>
            <div className="overflow-hidden">
              <div className="text-sm font-bold text-ink truncate">{user.nome}</div>
              <div className="text-xs text-muted truncate">{user.email}</div>
            </div>
          </div>
          <button 
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-semibold text-warn hover:bg-warn-tint rounded-lg transition-colors"
          >
            <LogOut size={16} />
            Sair
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-4 md:p-8">
        <div className="max-w-5xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
