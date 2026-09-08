import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { ShieldAlert, Trash2, RotateCcw, Ban, CheckCircle2, Building2 } from 'lucide-react';
import api from '../../lib/api';

type Dono = { id: number; nome: string; email: string };
type EmpresaAdmin = {
  id: number;
  cnpj: string;
  razao_social: string;
  nome_fantasia?: string | null;
  uf?: string | null;
  dono: Dono;
  bloqueada: boolean;
  deletada_em: string | null;
  criado_em: string;
  total_notas_mes: number;
  valor_total_mes: number;
};

type Tab = 'ativas' | 'bloqueadas' | 'lixeira';

type ConfirmState = {
  open: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  variant: 'danger' | 'warn' | 'ok';
} | null;

export default function EmpresasAdmin() {
  const [me, setMe] = useState<{ is_admin?: boolean } | null>(null);
  const [meLoaded, setMeLoaded] = useState(false);
  const [empresas, setEmpresas] = useState<EmpresaAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('ativas');
  const [confirm, setConfirm] = useState<ConfirmState>(null);
  const [banner, setBanner] = useState<{ tipo: 'ok' | 'erro'; msg: string } | null>(null);

  useEffect(() => {
    api.get('/auth/me')
      .then(r => setMe(r.data))
      .finally(() => setMeLoaded(true));
  }, []);

  const carregar = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/empresas?incluir_deletadas=true');
      setEmpresas(res.data);
    } catch (err: any) {
      setBanner({ tipo: 'erro', msg: err?.response?.data?.detail || 'Falha ao carregar empresas.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (me?.is_admin) carregar();
  }, [me]);

  if (!meLoaded) {
    return <div className="text-muted font-bold">Carregando...</div>;
  }
  if (!me?.is_admin) {
    return <Navigate to="/" replace />;
  }

  const filtradas = empresas.filter(e => {
    if (tab === 'lixeira') return e.deletada_em !== null;
    if (tab === 'bloqueadas') return e.deletada_em === null && e.bloqueada;
    return e.deletada_em === null && !e.bloqueada;
  });

  const bloquear = (emp: EmpresaAdmin, novo: boolean) => {
    setConfirm({
      open: true,
      title: novo ? 'Bloquear empresa?' : 'Desbloquear empresa?',
      message: novo
        ? `Todas as tentativas de emissão de ${emp.razao_social} (${emp.cnpj}) vão falhar com HTTP 403 até desbloquear. O histórico fiscal e as notas já emitidas ficam intactos.`
        : `${emp.razao_social} (${emp.cnpj}) volta a poder emitir notas normalmente.`,
      variant: novo ? 'warn' : 'ok',
      onConfirm: async () => {
        setConfirm(null);
        try {
          await api.patch(`/admin/empresas/${emp.id}/bloquear`, { bloqueada: novo });
          setBanner({ tipo: 'ok', msg: `${emp.razao_social} ${novo ? 'bloqueada' : 'desbloqueada'}.` });
          carregar();
        } catch (err: any) {
          setBanner({ tipo: 'erro', msg: err?.response?.data?.detail || 'Erro ao atualizar.' });
        }
      },
    });
  };

  const deletar = (emp: EmpresaAdmin) => {
    setConfirm({
      open: true,
      title: 'Deletar empresa (soft-delete)?',
      message: `${emp.razao_social} (${emp.cnpj}) some da lista do dono. Notas fiscais, XMLs e certificado ficam preservados no banco por obrigação legal (5 anos). Você pode restaurar a qualquer momento pela aba Lixeira.`,
      variant: 'danger',
      onConfirm: async () => {
        setConfirm(null);
        try {
          await api.delete(`/admin/empresas/${emp.id}`);
          setBanner({ tipo: 'ok', msg: `${emp.razao_social} enviada pra lixeira.` });
          carregar();
        } catch (err: any) {
          setBanner({ tipo: 'erro', msg: err?.response?.data?.detail || 'Erro ao deletar.' });
        }
      },
    });
  };

  const restaurar = (emp: EmpresaAdmin) => {
    setConfirm({
      open: true,
      title: 'Restaurar empresa?',
      message: `${emp.razao_social} (${emp.cnpj}) volta a aparecer na lista do dono e pode emitir notas de novo.`,
      variant: 'ok',
      onConfirm: async () => {
        setConfirm(null);
        try {
          await api.post(`/admin/empresas/${emp.id}/restaurar`);
          setBanner({ tipo: 'ok', msg: `${emp.razao_social} restaurada.` });
          carregar();
        } catch (err: any) {
          setBanner({ tipo: 'erro', msg: err?.response?.data?.detail || 'Erro ao restaurar.' });
        }
      },
    });
  };

  const contAtivas = empresas.filter(e => !e.deletada_em && !e.bloqueada).length;
  const contBloq = empresas.filter(e => !e.deletada_em && e.bloqueada).length;
  const contLix = empresas.filter(e => e.deletada_em).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight flex items-center gap-2">
            <ShieldAlert size={22} className="text-i9" /> Admin · Empresas
          </h1>
          <p className="text-muted text-sm font-medium mt-1">
            Todas as empresas do sistema, agrupadas por status. Bloquear trava novas emissões, deletar é reversível.
          </p>
        </div>
      </div>

      {banner && (
        <div className={`mb-4 flex items-center gap-2 border text-sm font-semibold px-4 py-3 rounded-lg ${banner.tipo === 'ok' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500' : 'bg-red-500/10 border-red-500/30 text-red-500'}`}>
          {banner.tipo === 'ok' ? <CheckCircle2 size={16} /> : <ShieldAlert size={16} />}
          {banner.msg}
          <button className="ml-auto text-xs opacity-70 hover:opacity-100" onClick={() => setBanner(null)}>fechar</button>
        </div>
      )}

      <div className="flex items-center gap-1 mb-4 border-b border-line">
        {([
          { key: 'ativas', label: 'Ativas', count: contAtivas },
          { key: 'bloqueadas', label: 'Bloqueadas', count: contBloq },
          { key: 'lixeira', label: 'Lixeira', count: contLix },
        ] as { key: Tab; label: string; count: number }[]).map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-bold border-b-2 -mb-px transition-colors ${tab === t.key ? 'border-i9 text-i9' : 'border-transparent text-muted hover:text-ink'}`}
          >
            {t.label} <span className="text-xs opacity-70">({t.count})</span>
          </button>
        ))}
      </div>

      <div className="bg-card border border-line rounded-DEFAULT shadow overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-muted font-bold">Carregando...</div>
        ) : filtradas.length === 0 ? (
          <div className="p-12 text-center">
            <Building2 size={48} className="mx-auto text-muted mb-4 opacity-50" />
            <h3 className="text-lg font-extrabold text-ink">Nenhuma empresa nessa aba.</h3>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead>
                <tr className="bg-bg text-muted text-xs uppercase tracking-wider font-extrabold border-b border-line">
                  <th className="px-6 py-4">Empresa</th>
                  <th className="px-6 py-4">CNPJ</th>
                  <th className="px-6 py-4">Dono</th>
                  <th className="px-6 py-4 text-right">Notas mês</th>
                  <th className="px-6 py-4 text-right">Valor mês</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {filtradas.map(emp => (
                  <tr key={emp.id} className="hover:bg-i9-tint transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-bold text-ink">{emp.razao_social}</div>
                      {emp.nome_fantasia && (
                        <div className="text-xs text-muted font-medium">{emp.nome_fantasia}{emp.uf ? ` · ${emp.uf}` : ''}</div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-ink-soft font-mono">{emp.cnpj}</td>
                    <td className="px-6 py-4">
                      <div className="font-bold text-ink text-xs">{emp.dono.nome}</div>
                      <div className="text-xs text-muted">{emp.dono.email}</div>
                    </td>
                    <td className="px-6 py-4 text-right font-mono">{emp.total_notas_mes}</td>
                    <td className="px-6 py-4 text-right font-mono">
                      {emp.valor_total_mes.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                    </td>
                    <td className="px-6 py-4">
                      {emp.deletada_em ? (
                        <span className="bg-red-500/10 text-red-400 border border-red-500/20 text-xs px-2.5 py-1 rounded-full font-bold">Deletada</span>
                      ) : emp.bloqueada ? (
                        <span className="bg-amber-500/10 text-amber-400 border border-amber-500/20 text-xs px-2.5 py-1 rounded-full font-bold">Bloqueada</span>
                      ) : (
                        <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs px-2.5 py-1 rounded-full font-bold">Ativa</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {emp.deletada_em ? (
                          <button
                            onClick={() => restaurar(emp)}
                            className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 font-bold text-xs px-3 py-1.5 rounded-md flex items-center gap-1 hover:bg-emerald-500/20"
                          >
                            <RotateCcw size={13} /> Restaurar
                          </button>
                        ) : (
                          <>
                            <button
                              onClick={() => bloquear(emp, !emp.bloqueada)}
                              className={`border font-bold text-xs px-3 py-1.5 rounded-md flex items-center gap-1 ${emp.bloqueada ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500 hover:bg-emerald-500/20' : 'bg-amber-500/10 border-amber-500/30 text-amber-500 hover:bg-amber-500/20'}`}
                            >
                              {emp.bloqueada ? <CheckCircle2 size={13} /> : <Ban size={13} />}
                              {emp.bloqueada ? 'Desbloquear' : 'Bloquear'}
                            </button>
                            <button
                              onClick={() => deletar(emp)}
                              className="bg-red-500/10 border border-red-500/30 text-red-500 font-bold text-xs px-3 py-1.5 rounded-md flex items-center gap-1 hover:bg-red-500/20"
                            >
                              <Trash2 size={13} /> Deletar
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {confirm?.open && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-card border border-line rounded-lg shadow-lg max-w-md w-full p-6">
            <h3 className="text-lg font-extrabold text-ink mb-2">{confirm.title}</h3>
            <p className="text-sm text-muted mb-6 leading-relaxed">{confirm.message}</p>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setConfirm(null)}
                className="text-sm font-bold text-muted px-4 py-2 rounded-md hover:bg-line-soft"
              >
                Cancelar
              </button>
              <button
                onClick={confirm.onConfirm}
                className={`text-sm font-bold text-white px-4 py-2 rounded-md ${confirm.variant === 'danger' ? 'bg-red-500 hover:bg-red-600' : confirm.variant === 'warn' ? 'bg-amber-500 hover:bg-amber-600' : 'bg-emerald-500 hover:bg-emerald-600'}`}
              >
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
