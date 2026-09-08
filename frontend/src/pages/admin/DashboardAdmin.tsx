import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Gauge, Building2, Ban, Trash2, Users, FileText, TrendingUp } from 'lucide-react';
import api from '../../lib/api';

type NotasMes = { nfe: number; nfce: number; devolucao: number };
type TopEmpresa = { empresa_id: number; razao_social: string; cnpj: string; total_notas: number };
type Metricas = {
  empresas_total: number;
  empresas_ativas: number;
  empresas_bloqueadas: number;
  empresas_deletadas: number;
  usuarios_total: number;
  notas_mes: NotasMes;
  valor_total_mes: number;
  top_5_empresas_por_notas: TopEmpresa[];
};

export default function DashboardAdmin() {
  const [me, setMe] = useState<{ is_admin?: boolean } | null>(null);
  const [meLoaded, setMeLoaded] = useState(false);
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api.get('/auth/me')
      .then(r => setMe(r.data))
      .finally(() => setMeLoaded(true));
  }, []);

  useEffect(() => {
    if (!me?.is_admin) return;
    api.get('/admin/metricas')
      .then(r => setMetricas(r.data))
      .catch(err => setErro(err?.response?.data?.detail || 'Erro ao carregar métricas.'))
      .finally(() => setLoading(false));
  }, [me]);

  if (!meLoaded) return <div className="text-muted font-bold">Carregando...</div>;
  if (!me?.is_admin) return <Navigate to="/" replace />;

  const cards = metricas ? [
    { label: 'Empresas ativas', valor: metricas.empresas_ativas, icon: <Building2 size={20} />, cor: 'text-emerald-500' },
    { label: 'Bloqueadas', valor: metricas.empresas_bloqueadas, icon: <Ban size={20} />, cor: 'text-amber-500' },
    { label: 'Deletadas', valor: metricas.empresas_deletadas, icon: <Trash2 size={20} />, cor: 'text-red-500' },
    { label: 'Usuários', valor: metricas.usuarios_total, icon: <Users size={20} />, cor: 'text-i9' },
  ] : [];

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-2xl font-extrabold tracking-tight flex items-center gap-2">
          <Gauge size={22} className="text-i9" /> Admin · Dashboard
        </h1>
        <p className="text-muted text-sm font-medium mt-1">Visão global do sistema — todas empresas de todos usuários.</p>
      </div>

      {loading && <div className="text-muted font-bold">Carregando métricas...</div>}
      {erro && (
        <div className="mb-4 bg-red-500/10 border border-red-500/30 text-red-500 text-sm font-semibold px-4 py-3 rounded-lg">
          {erro}
        </div>
      )}

      {metricas && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            {cards.map(card => (
              <div key={card.label} className="bg-card border border-line rounded-lg p-4">
                <div className={`flex items-center gap-2 ${card.cor}`}>{card.icon}</div>
                <div className="text-3xl font-extrabold text-ink mt-2">{card.valor}</div>
                <div className="text-xs text-muted font-bold uppercase tracking-wider mt-1">{card.label}</div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div className="bg-card border border-line rounded-lg p-4">
              <div className="flex items-center gap-2 text-i9 mb-2">
                <FileText size={18} /> <span className="text-xs uppercase tracking-wider font-extrabold">Notas do mês</span>
              </div>
              <div className="grid grid-cols-3 gap-2 mt-3">
                <div>
                  <div className="text-2xl font-extrabold text-ink">{metricas.notas_mes.nfe}</div>
                  <div className="text-xs text-muted font-bold">NF-e (55)</div>
                </div>
                <div>
                  <div className="text-2xl font-extrabold text-ink">{metricas.notas_mes.nfce}</div>
                  <div className="text-xs text-muted font-bold">NFC-e (65)</div>
                </div>
                <div>
                  <div className="text-2xl font-extrabold text-ink">{metricas.notas_mes.devolucao}</div>
                  <div className="text-xs text-muted font-bold">Devolução</div>
                </div>
              </div>
            </div>

            <div className="bg-card border border-line rounded-lg p-4">
              <div className="flex items-center gap-2 text-emerald-500 mb-2">
                <TrendingUp size={18} /> <span className="text-xs uppercase tracking-wider font-extrabold">Valor total do mês</span>
              </div>
              <div className="text-3xl font-extrabold text-ink mt-3">
                {metricas.valor_total_mes.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
              </div>
              <div className="text-xs text-muted font-bold mt-1">Soma de valor_total (exclui rascunhos)</div>
            </div>
          </div>

          <div className="bg-card border border-line rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-line font-extrabold text-ink text-sm">
              Top 5 empresas por notas (mês)
            </div>
            {metricas.top_5_empresas_por_notas.length === 0 ? (
              <div className="p-6 text-center text-muted text-sm font-bold">Nenhuma nota emitida no mês.</div>
            ) : (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="bg-bg text-muted text-xs uppercase tracking-wider font-extrabold border-b border-line">
                    <th className="px-4 py-2">#</th>
                    <th className="px-4 py-2">Empresa</th>
                    <th className="px-4 py-2">CNPJ</th>
                    <th className="px-4 py-2 text-right">Notas</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-soft">
                  {metricas.top_5_empresas_por_notas.map((emp, idx) => (
                    <tr key={emp.empresa_id} className="hover:bg-i9-tint transition-colors">
                      <td className="px-4 py-2 font-mono text-xs">{idx + 1}</td>
                      <td className="px-4 py-2 font-bold text-ink">{emp.razao_social}</td>
                      <td className="px-4 py-2 font-mono text-ink-soft">{emp.cnpj}</td>
                      <td className="px-4 py-2 text-right font-mono font-bold">{emp.total_notas}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
