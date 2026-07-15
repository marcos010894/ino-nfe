import { useEffect, useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend, LineChart, Line } from 'recharts';
import { TrendingUp, FileText, Building2, AlertCircle } from 'lucide-react';
import api from '../../lib/api';

// Dados fictícios para demonstração
const faturamentoData = [
  { name: 'Seg', valor: 4000 },
  { name: 'Ter', valor: 3000 },
  { name: 'Qua', valor: 5000 },
  { name: 'Qui', valor: 2780 },
  { name: 'Sex', valor: 8900 },
  { name: 'Sáb', valor: 2390 },
  { name: 'Dom', valor: 3490 },
];

const volumeNotasData = [
  { name: 'Jan', emissao: 400, canceladas: 24 },
  { name: 'Fev', emissao: 300, canceladas: 13 },
  { name: 'Mar', emissao: 550, canceladas: 45 },
  { name: 'Abr', emissao: 480, canceladas: 18 },
  { name: 'Mai', emissao: 600, canceladas: 30 },
  { name: 'Jun', emissao: 720, canceladas: 20 },
];

const statusNotasData = [
  { name: 'Autorizadas', value: 850, color: '#1e874b' }, // ok
  { name: 'Pendentes', value: 50, color: '#b7791f' },    // pend
  { name: 'Rejeitadas', value: 30, color: '#c0392b' },   // warn
];

const ticketMedioData = [
  { name: 'Sem 1', ticket: 120 },
  { name: 'Sem 2', ticket: 150 },
  { name: 'Sem 3', ticket: 140 },
  { name: 'Sem 4', ticket: 180 },
];

export default function Home() {
  const [qtdEmpresas, setQtdEmpresas] = useState(0);

  useEffect(() => {
    // Buscar quantidade real de empresas
    api.get('/empresas/').then(res => setQtdEmpresas(res.data.length)).catch(() => {});
  }, []);

  return (
    <div className="pb-8">
      <div className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Visão Geral</h1>
          <p className="text-muted text-sm font-medium mt-1">Acompanhe as métricas fiscais em tempo real.</p>
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
          <div className="text-3xl font-extrabold text-ink mb-1">3.050</div>
          <div className="text-xs font-bold text-ok flex items-center gap-1">
            <TrendingUp size={14} /> +12% em relação ao mês anterior
          </div>
        </div>
        
        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 relative overflow-hidden group hover:border-ok transition-colors">
          <div className="absolute -right-4 -top-4 bg-ok-tint w-24 h-24 rounded-full flex items-center justify-center opacity-50 group-hover:scale-110 transition-transform">
            <TrendingUp size={32} className="text-ok ml-2 mt-2" />
          </div>
          <div className="text-xs font-bold text-muted uppercase tracking-wider mb-2">Volume Transacionado</div>
          <div className="text-3xl font-extrabold text-ink mb-1">R$ 29.5k</div>
          <div className="text-xs font-bold text-ok flex items-center gap-1">
            <TrendingUp size={14} /> +5.4% de faturamento
          </div>
        </div>

        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 relative overflow-hidden group hover:border-pend transition-colors">
          <div className="absolute -right-4 -top-4 bg-line w-24 h-24 rounded-full flex items-center justify-center opacity-50 group-hover:scale-110 transition-transform">
            <Building2 size={32} className="text-muted ml-2 mt-2" />
          </div>
          <div className="text-xs font-bold text-muted uppercase tracking-wider mb-2">Empresas Ativas</div>
          <div className="text-3xl font-extrabold text-ink mb-1">{qtdEmpresas}</div>
          <div className="text-xs font-medium text-muted">Configuradas na sua conta</div>
        </div>

        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 relative overflow-hidden group hover:border-warn transition-colors">
          <div className="absolute -right-4 -top-4 bg-warn-tint w-24 h-24 rounded-full flex items-center justify-center opacity-50 group-hover:scale-110 transition-transform">
            <AlertCircle size={32} className="text-warn ml-2 mt-2" />
          </div>
          <div className="text-xs font-bold text-muted uppercase tracking-wider mb-2">Rejeições Sefaz</div>
          <div className="text-3xl font-extrabold text-ink mb-1">30</div>
          <div className="text-xs font-bold text-warn flex items-center gap-1">
            Necessitam de correção (CFOP/NCM)
          </div>
        </div>

      </div>

      {/* Gráficos */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Gráfico 1: Área de Faturamento */}
        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 lg:col-span-2 flex flex-col">
          <h2 className="text-base font-extrabold text-ink mb-6">Faturamento Diário (R$)</h2>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={faturamentoData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
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
                />
                <Area type="monotone" dataKey="valor" stroke="#0b63c4" strokeWidth={3} fillOpacity={1} fill="url(#colorValor)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Gráfico 2: Donut Status */}
        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 flex flex-col">
          <h2 className="text-base font-extrabold text-ink mb-2">Status de Emissão (Hoje)</h2>
          <div style={{ width: '100%', height: 250 }} className="mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusNotasData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={5}
                  dataKey="value"
                  stroke="none"
                >
                  {statusNotasData.map((entry, index) => (
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
        </div>

        {/* Gráfico 3: Barras Volume */}
        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 lg:col-span-2 flex flex-col">
          <h2 className="text-base font-extrabold text-ink mb-6">Histórico de Notas Geradas</h2>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={volumeNotasData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }} barSize={32}>
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

        {/* Gráfico 4: Ticket Médio (Linha) */}
        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 flex flex-col">
          <h2 className="text-base font-extrabold text-ink mb-6">Ticket Médio (R$)</h2>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={ticketMedioData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f7" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#8190a5', fontWeight: 600 }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#8190a5', fontWeight: 600 }} />
                <Tooltip 
                  contentStyle={{ borderRadius: '12px', border: '1px solid #e4e9f0', boxShadow: '0 8px 30px rgba(15,27,45,.06)', fontWeight: 'bold' }}
                  itemStyle={{ color: '#e6a817' }}
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
