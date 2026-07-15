import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import api from '../lib/api';
import { setToken } from '../lib/auth';

export default function Login() {
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [erro, setErro] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro('');
    setLoading(true);
    
    try {
      const res = await api.post('/auth/login', { email, senha });
      setToken(res.data.access_token);
      navigate('/');
    } catch (err: any) {
      if (err.response?.status === 422) {
        setErro('E-mail ou senha em formato inválido.');
      } else {
        setErro(err.response?.data?.detail || 'Erro ao fazer login. Verifique suas credenciais.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="text-3xl font-extrabold text-i9 tracking-tight flex items-center justify-center gap-1">
            i9<span className="text-gold">·</span><small className="text-ink font-bold">InnoNFe</small>
          </div>
          <p className="text-muted mt-2 font-medium">Acesse o painel do sistema</p>
        </div>

        <div className="bg-card border border-line rounded-[14px] shadow p-8">
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            {erro && (
              <div className="bg-warn-tint text-warn p-3 rounded-lg text-sm font-semibold border border-[#f0c9c4] flex items-center">
                {erro}
              </div>
            )}
            
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase tracking-wider">E-mail</label>
              <input 
                type="email" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
                className="bg-field border border-line rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-i9 focus:ring-2 focus:ring-i9/20 transition-all disabled:opacity-60"
                placeholder="seu@email.com"
                required
              />
            </div>
            
            <div className="flex flex-col gap-1.5">
              <div className="flex justify-between items-center">
                <label className="text-xs font-bold text-muted uppercase tracking-wider">Senha</label>
              </div>
              <div className="relative">
                <input 
                  type={mostrarSenha ? "text" : "password"}
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                  disabled={loading}
                  className="w-full bg-field border border-line rounded-lg px-3 py-2.5 pr-10 text-sm focus:outline-none focus:border-i9 focus:ring-2 focus:ring-i9/20 transition-all disabled:opacity-60"
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setMostrarSenha(!mostrarSenha)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink transition-colors"
                >
                  {mostrarSenha ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button 
              type="submit" 
              disabled={loading}
              className="mt-2 flex items-center justify-center gap-2 bg-gradient-to-b from-i9 to-i9-dark text-white font-bold rounded-lg py-2.5 text-sm shadow-sm hover:opacity-90 transition-opacity disabled:opacity-70"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  Entrando...
                </>
              ) : (
                'Entrar'
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-muted">
            Ainda não tem acesso? <Link to="/cadastro" className="text-i9 font-bold hover:underline">Cadastre-se</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
