import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import api from '../lib/api';
import { formatCPF, formatTelefone, unformat } from '../lib/formatters';

export default function Cadastro() {
  const [nome, setNome] = useState('');
  const [email, setEmail] = useState('');
  const [cpf, setCpf] = useState('');
  const [telefone, setTelefone] = useState('');
  const [senha, setSenha] = useState('');
  const [confirmacaoSenha, setConfirmacaoSenha] = useState('');
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [mostrarConfirmacao, setMostrarConfirmacao] = useState(false);
  
  const [erro, setErro] = useState('');
  const [sucesso, setSucesso] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleCadastro = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro('');
    setSucesso('');

    if (senha !== confirmacaoSenha) {
      setErro('As senhas não coincidem. Por favor, verifique.');
      return;
    }

    if (senha.length < 6) {
      setErro('A senha deve ter no mínimo 6 caracteres.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/register', { 
        nome, 
        email, 
        senha, 
        cpf: unformat(cpf), 
        telefone: unformat(telefone) 
      });
      setSucesso('Usuário criado com sucesso! Redirecionando...');
      setTimeout(() => navigate('/login'), 2000);
    } catch (err: any) {
      // Tratamento de erros do FastAPI (422 Unprocessable Entity ou 400 Bad Request)
      if (err.response?.status === 422) {
        setErro('Dados inválidos. Verifique se o e-mail está correto e tente novamente.');
      } else {
        setErro(err.response?.data?.detail || 'Ocorreu um erro inesperado ao criar o usuário.');
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
          <p className="text-muted mt-2 font-medium">Crie o seu primeiro acesso</p>
        </div>

        <div className="bg-card border border-line rounded-[14px] shadow p-8">
          <form onSubmit={handleCadastro} className="flex flex-col gap-4">
            {erro && (
              <div className="bg-warn-tint text-warn p-3 rounded-lg text-sm font-semibold border border-[#f0c9c4] flex items-center">
                {erro}
              </div>
            )}
            {sucesso && (
              <div className="bg-ok-tint text-ok p-3 rounded-lg text-sm font-semibold border border-[#c3e6cb] flex items-center">
                {sucesso}
              </div>
            )}
            
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase tracking-wider">Nome Completo</label>
              <input 
                type="text" 
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                disabled={loading || !!sucesso}
                className="bg-field border border-line rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-i9 focus:ring-2 focus:ring-i9/20 transition-all disabled:opacity-60"
                placeholder="Seu nome completo"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase tracking-wider">CPF</label>
              <input 
                type="text" 
                value={cpf}
                onChange={(e) => setCpf(formatCPF(e.target.value))}
                disabled={loading || !!sucesso}
                className="bg-field border border-line rounded-lg px-3 py-2.5 text-sm font-mono focus:outline-none focus:border-i9 focus:ring-2 focus:ring-i9/20 transition-all disabled:opacity-60"
                placeholder="000.000.000-00"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase tracking-wider">Telefone (Celular)</label>
              <input 
                type="text" 
                value={telefone}
                onChange={(e) => setTelefone(formatTelefone(e.target.value))}
                disabled={loading || !!sucesso}
                className="bg-field border border-line rounded-lg px-3 py-2.5 text-sm font-mono focus:outline-none focus:border-i9 focus:ring-2 focus:ring-i9/20 transition-all disabled:opacity-60"
                placeholder="(00) 00000-0000"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase tracking-wider">E-mail</label>
              <input 
                type="email" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading || !!sucesso}
                className="bg-field border border-line rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-i9 focus:ring-2 focus:ring-i9/20 transition-all disabled:opacity-60"
                placeholder="seu@email.com"
                required
              />
            </div>
            
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase tracking-wider">Senha</label>
              <div className="relative">
                <input 
                  type={mostrarSenha ? "text" : "password"}
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                  disabled={loading || !!sucesso}
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

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase tracking-wider">Confirmar Senha</label>
              <div className="relative">
                <input 
                  type={mostrarConfirmacao ? "text" : "password"}
                  value={confirmacaoSenha}
                  onChange={(e) => setConfirmacaoSenha(e.target.value)}
                  disabled={loading || !!sucesso}
                  className="w-full bg-field border border-line rounded-lg px-3 py-2.5 pr-10 text-sm focus:outline-none focus:border-i9 focus:ring-2 focus:ring-i9/20 transition-all disabled:opacity-60"
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setMostrarConfirmacao(!mostrarConfirmacao)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink transition-colors"
                >
                  {mostrarConfirmacao ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button 
              type="submit" 
              disabled={loading || !!sucesso}
              className="mt-2 flex items-center justify-center gap-2 bg-gradient-to-b from-ok to-[#1a7040] text-white font-bold rounded-lg py-2.5 text-sm shadow-sm hover:opacity-90 transition-opacity disabled:opacity-70"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  Cadastrando...
                </>
              ) : (
                'Cadastrar'
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-muted">
            Já possui acesso? <Link to="/login" className="text-i9 font-bold hover:underline">Fazer login</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
