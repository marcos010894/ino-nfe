import { useEffect, useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend, LineChart, Line } from 'recharts';
import { TrendingUp, TrendingDown, FileText, Building2, AlertCircle, Globe2, Loader2 } from 'lucide-react';
import api from '../../lib/api';

interface PontoValor { name: string; valor: number }
interface PontoStatus { name: string; value: number; color: string }
interface PontoVolume { name: string; emissao: number; canceladas: number }
interface PontoTicket { name: string; ticket: number }
interface Cards {
  notas_mes: number;
  notas_mes_delta_pct: number | null;
  volume_mes: number;
  volume_mes_delta_pct: number | null;
  empresas_ativas: number;
  rejeicoes_mes: number;
}
interface Resumo {
  cards: Cards;
  faturamento_diario: PontoValor[];
  status_hoje: PontoStatus[];
  historico_6meses: PontoVolume[];
  ticket_medio_semanas: PontoTicket[];
  escopo: 'global' | 'usuario';
}

function fmtMoeda(v: number, curto = false) {
  if (curto && v >= 1000) return `R$ ${(v / 1000).toFixed(1)}k`;
  return `R$ ${v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function DeltaBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-xs font-medium text-muted">sem base do mês anterior</span>;
  if (pct >= 0) {
    return (
      <span className="text-xs font-bold text-ok flex items-center gap-1">
        <TrendingUp size={14} /> +{pct.toFixed(1)}% vs mês anterior
      </span>
    );
  }
  return (
    <span className="text-xs font-bold text-warn flex items-center gap-1">
      <TrendingDown size={14} /> {pct.toFixed(1)}% vs mês anterior
    </span>
  );
}

export default function Home() {
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [erro, setErro] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    setLoading(true);
    api.get('/dashboard/resumo')
      .then((res) => setResumo(res.data))
      .catch((e) => setErro(e?.response?.data?.detail || 'Não foi possível carregar os dados.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted gap-2">
        <Loader2 size={18} className="animate-spin" /> Carregando dashboard…
      </div>
    );
  }
  if (erro || !resumo) {
    return (
      <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-4 rounded-xl text-sm font-semibold">
        {erro || 'Falha ao carregar.'}
      </div>
    );
  }

  const { cards, faturamento_diario, status_hoje, historico_6meses, ticket_medio_semanas, escopo } = resumo;
  const totalStatusHoje = status_hoje.reduce((s, p) => s + p.value, 0);

  return (
    <div className="pb-8">
      <div className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Visão Geral</h1>
          <p className="text-muted text-sm font-medium mt-1">
            Acompanhe as métricas fiscais em tempo real.
            {escopo === 'global' && (
              <span className="ml-2 inline-flex items-center gap-1 text-xs font-bold text-i9 bg-i9-tint px-2 py-0.5 rounded-full">
                <Globe2 size={12} /> Visão admin — dados globais
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3 bg-card border border-line px-4 py-2 rounded-lg shadow-sm">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ok opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-ok"></span>
          </span>
          <span className="text-sm font-bold text-ink-soft">Sistema Operacional</span>
        </div>
      </div>

      {/* Cards de Resumo */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">

        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 relative overflow-hidden group hover:border-i9 transition-colors">
          <div className="absolute -right-4 -top-4 bg-i9-tint w-24 h-24 rounded-full flex items-center justify-center opacity-50 group-hover:scale-110 transition-transform">
            <FileText size={32} className="text-i9 ml-2 mt-2" />
          </div>
          <div className="text-xs font-bold text-muted uppercase tracking-wider mb-2">Notas Emitidas (Mês)</div>
          <div className="text-3xl font-extrabold text-ink mb-1">{cards.notas_mes.toLocaleString('pt-BR')}</div>
          <DeltaBadge pct={cards.notas_mes_delta_pct} />
        </div>

        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 relative overflow-hidden group hover:border-ok transition-colors">
          <div className="absolute -right-4 -top-4 bg-ok-tint w-24 h-24 rounded-full flex items-center justify-center opacity-50 group-hover:scale-110 transition-transform">
            <TrendingUp size={32} className="text-ok ml-2 mt-2" />
          </div>
          <div className="text-xs font-bold text-muted uppercase tracking-wider mb-2">Volume Transacionado</div>
          <div className="text-3xl font-extrabold text-ink mb-1">{fmtMoeda(cards.volume_mes, true)}</div>
          <DeltaBadge pct={cards.volume_mes_delta_pct} />
        </div>

        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 relative overflow-hidden group hover:border-pend transition-colors">
          <div className="absolute -right-4 -top-4 bg-line w-24 h-24 rounded-full flex items-center justify-center opacity-50 group-hover:scale-110 transition-transform">
            <Building2 size={32} className="text-muted ml-2 mt-2" />
          </div>
          <div className="text-xs font-bold text-muted uppercase tracking-wider mb-2">Empresas Ativas</div>
          <div className="text-3xl font-extrabold text-ink mb-1">{cards.empresas_ativas}</div>
          <div className="text-xs font-medium text-muted">
            {escopo === 'global' ? 'Ativas no sistema (não bloqueadas)' : 'Configuradas na sua conta'}
          </div>
        </div>

        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 relative overflow-hidden group hover:border-warn transition-colors">
          <div className="absolute -right-4 -top-4 bg-warn-tint w-24 h-24 rounded-full flex items-center justify-center opacity-50 group-hover:scale-110 transition-transform">
            <AlertCircle size={32} className="text-warn ml-2 mt-2" />
          </div>
          <div className="text-xs font-bold text-muted uppercase tracking-wider mb-2">Rejeições Sefaz (Mês)</div>
          <div className="text-3xl font-extrabold text-ink mb-1">{cards.rejeicoes_mes}</div>
          <div className="text-xs font-bold text-warn flex items-center gap-1">
            {cards.rejeicoes_mes > 0 ? 'Verifique em Documentos' : 'Nenhuma rejeição no mês'}
          </div>
        </div>

      </div>

      {/* Gráficos */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Faturamento diário (7 dias) */}
        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 lg:col-span-2 flex flex-col">
          <h2 className="text-base font-extrabold text-ink mb-6">Faturamento Diário — últimos 7 dias (R$)</h2>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={faturamento_diario} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorValor" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0b63c4" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#0b63c4" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f7" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#8190a5', fontWeight: 600 }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#8190a5', fontWeight: 600 }} />
                <Tooltip
                  contentStyle={{ borderRadius: '12px', border: '1px solid #e4e9f0', boxShadow: '0 8px 30px rgba(15,27,45,.06)', fontWeight: 'bold' }}
                  itemStyle={{ color: '#0b63c4' }}
                  formatter={(v: any) => fmtMoeda(Number(v))}
                />
                <Area type="monotone" dataKey="valor" stroke="#0b63c4" strokeWidth={3} fillOpacity={1} fill="url(#colorValor)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Donut status hoje */}
        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 flex flex-col">
          <h2 className="text-base font-extrabold text-ink mb-2">Status de Emissão (Hoje)</h2>
          {totalStatusHoje === 0 ? (
            <div className="flex items-center justify-center h-[250px] text-sm text-muted italic">
              Sem emissões hoje
            </div>
          ) : (
            <div style={{ width: '100%', height: 250 }} className="mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={status_hoje}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                  >
                    {status_hoje.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)', fontWeight: 'bold' }}
                    itemStyle={{ color: '#0f1b2d' }}
                  />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', fontWeight: 'bold', paddingTop: '20px' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Histórico 6 meses */}
        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 lg:col-span-2 flex flex-col">
          <h2 className="text-base font-extrabold text-ink mb-6">Histórico — últimos 6 meses</h2>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={historico_6meses} margin={{ top: 10, right: 10, left: -20, bottom: 0 }} barSize={32}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f7" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#8190a5', fontWeight: 600 }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#8190a5', fontWeight: 600 }} />
                <Tooltip
                  cursor={{ fill: '#eaf3fd' }}
                  contentStyle={{ borderRadius: '12px', border: '1px solid #e4e9f0', boxShadow: '0 8px 30px rgba(15,27,45,.06)', fontWeight: 'bold' }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', fontWeight: 'bold', paddingTop: '10px' }} />
                <Bar dataKey="emissao" name="Emitidas" fill="#0b63c4" radius={[4, 4, 0, 0]} />
                <Bar dataKey="canceladas" name="Canceladas" fill="#c0392b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Ticket médio 4 semanas */}
        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 flex flex-col">
          <h2 className="text-base font-extrabold text-ink mb-6">Ticket Médio — últimas 4 semanas</h2>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={ticket_medio_semanas} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f7" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#8190a5', fontWeight: 600 }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#8190a5', fontWeight: 600 }} />
                <Tooltip
                  contentStyle={{ borderRadius: '12px', border: '1px solid #e4e9f0', boxShadow: '0 8px 30px rgba(15,27,45,.06)', fontWeight: 'bold' }}
                  itemStyle={{ color: '#e6a817' }}
                  formatter={(v: any) => fmtMoeda(Number(v))}
                />
                <Line type="monotone" dataKey="ticket" stroke="#e6a817" strokeWidth={4} dot={{ r: 6, fill: '#fff', stroke: '#e6a817', strokeWidth: 3 }} activeDot={{ r: 8 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>
    </div>
  );
}
