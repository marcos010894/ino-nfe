import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Loader2, AlertCircle } from 'lucide-react';
import { setToken } from '../lib/auth';

/**
 * Endpoint de entrada SSO via Token de Integração.
 *
 * Fluxo: InnoSystem chama POST /integracao/sessao com seu X-API-Key (do servidor),
 * recebe um JWT de 15min e redireciona o usuário pra /sso?token=<jwt>[&rascunho=<id>].
 * Aqui, guardamos o JWT no localStorage e navegamos pra /emitir (limpando a URL
 * pra o token não vazar em histórico do browser).
 */
export default function SSO() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [erro, setErro] = useState<string>('');

  useEffect(() => {
    const token = params.get('token');
    const rascunho = params.get('rascunho');

    if (!token) {
      setErro('Link SSO inválido: parâmetro `token` ausente.');
      return;
    }

    setToken(token);

    // Substitui a URL (não empilha no histórico) removendo o token —
    // evita que ele apareça em back/forward, referer ou histórico do browser.
    const destino = rascunho ? `/emitir?rascunho=${encodeURIComponent(rascunho)}` : '/emitir';
    navigate(destino, { replace: true });
  }, [params, navigate]);

  if (erro) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="max-w-md w-full bg-card border border-line rounded-DEFAULT shadow p-6 flex flex-col gap-3">
          <div className="flex items-center gap-2 text-warn font-extrabold">
            <AlertCircle size={20} />
            Falha no SSO
          </div>
          <p className="text-sm text-ink-soft">{erro}</p>
          <a href="/login" className="text-i9 font-bold text-sm underline">
            Ir para login manual →
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-ink-soft">
        <Loader2 size={28} className="animate-spin text-i9" />
        <span className="text-sm font-semibold">Autenticando...</span>
      </div>
    </div>
  );
}
