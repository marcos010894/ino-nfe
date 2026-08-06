import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Building2, Plus, AlertCircle, CheckCircle2, ShieldCheck, Zap, Wifi } from 'lucide-react';
import api from '../../lib/api';

interface Empresa {
  id: number;
  razao_social: string;
  nome_fantasia: string;
  cnpj: string;
  has_certificado: boolean;
  certificado_vencimento?: string;
  certificado_emissor?: string;
  certificado_sujeito?: string;
  acbr_sincronizado: boolean;
  acbr_ultimo_status?: string;
}

type AcbrStatus =
  | { state: 'idle' }
  | { state: 'testing' }
  | { state: 'ok'; env: string; base_url: string; endpoint_status_code?: number }
  | { state: 'error'; message: string; etapa?: string };

export default function EmpresasList() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [loading, setLoading] = useState(true);
  const [acbrStatus, setAcbrStatus] = useState<AcbrStatus>({ state: 'idle' });

  useEffect(() => {
    carregarEmpresas();
  }, []);

  const carregarEmpresas = async () => {
    try {
      const res = await api.get('/empresas/');
      setEmpresas(res.data);
    } catch (error) {
      console.error("Erro ao carregar empresas:", error);
    } finally {
      setLoading(false);
    }
  };

  const testarAcbr = async () => {
    setAcbrStatus({ state: 'testing' });
    try {
      const res = await api.get('/empresas/acbr/status');
      setAcbrStatus({
        state: 'ok',
        env: res.data.env,
        base_url: res.data.base_url,
        endpoint_status_code: res.data.endpoint_status_code,
      });
    } catch (err: any) {
      const detail = err?.response?.data?.detail || {};
      setAcbrStatus({
        state: 'error',
        message: detail.erro || err?.message || 'Falha desconhecida',
        etapa: detail.etapa,
      });
    }
  };

  const getCertificadoStatus = (hasCert: boolean, validade?: string) => {
    if (!hasCert || !validade) {
      return (
        <span className="bg-red-500/10 text-red-400 border border-red-500/20 text-xs px-2.5 py-1 rounded-full font-semibold flex items-center w-fit gap-1.5">
          <AlertCircle size={14} /> Sem Certificado A1
        </span>
      );
    }
    
    const dataValidade = new Date(validade);
    const hoje = new Date();
    const difTempo = dataValidade.getTime() - hoje.getTime();
    const difDias = Math.ceil(difTempo / (1000 * 3600 * 24));
    
    if (difDias < 0) {
      return (
        <span className="bg-red-500/10 text-red-400 border border-red-500/20 text-xs px-2.5 py-1 rounded-full font-bold flex items-center w-fit gap-1.5">
          <AlertCircle size={14} /> Vencido em {dataValidade.toLocaleDateString('pt-BR')}
        </span>
      );
    } else if (difDias <= 30) {
      return (
        <span className="bg-amber-500/10 text-amber-400 border border-amber-500/20 text-xs px-2.5 py-1 rounded-full font-bold flex items-center w-fit gap-1.5">
          <AlertCircle size={14} /> Vence em {difDias} dias
        </span>
      );
    } else {
      return (
        <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs px-2.5 py-1 rounded-full font-bold flex items-center w-fit gap-1.5">
          <CheckCircle2 size={14} /> Válido até {dataValidade.toLocaleDateString('pt-BR')}
        </span>
      );
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Empresas & Certificados</h1>
          <p className="text-muted text-sm font-medium mt-1">Gerencie os emitentes e a vinculação direta com a ACBr API.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={testarAcbr}
            disabled={acbrStatus.state === 'testing'}
            className="bg-field border border-line hover:bg-line-soft transition-colors text-ink font-bold px-4 py-2 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50"
            title="Handshake real com a ACBr (OAuth2 + endpoint autenticado)"
          >
            <Wifi size={16} />
            {acbrStatus.state === 'testing' ? 'Testando...' : 'Testar Conexão ACBr'}
          </button>
          <Link
            to="/empresas/nova"
            className="bg-gradient-to-b from-ok to-[#1a7040] hover:opacity-90 transition-opacity text-white font-bold px-4 py-2 rounded-lg text-sm flex items-center gap-2 shadow-sm"
          >
            <Plus size={16} strokeWidth={3} />
            Nova Empresa
          </Link>
        </div>
      </div>

      {/* Painel de resultado do teste de conexão ACBr */}
      {acbrStatus.state === 'ok' && (
        <div className="mb-4 flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 text-sm font-semibold px-4 py-3 rounded-lg">
          <CheckCircle2 size={16} />
          Conectado com sucesso à ACBr ({acbrStatus.env}) — <span className="font-mono">{acbrStatus.base_url}</span>
          {typeof acbrStatus.endpoint_status_code === 'number' && (
            <span className="text-xs opacity-70">· HTTP {acbrStatus.endpoint_status_code}</span>
          )}
        </div>
      )}
      {acbrStatus.state === 'error' && (
        <div className="mb-4 flex items-start gap-2 bg-red-500/10 border border-red-500/30 text-red-500 text-sm font-semibold px-4 py-3 rounded-lg">
          <AlertCircle size={16} className="mt-0.5" />
          <div>
            Falha na conexão com a ACBr
            {acbrStatus.etapa && <span className="opacity-70"> (etapa: {acbrStatus.etapa})</span>}:
            <div className="font-mono text-xs mt-1 opacity-90 break-all">{acbrStatus.message}</div>
          </div>
        </div>
      )}

      <div className="bg-card border border-line rounded-DEFAULT shadow overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-muted font-bold">Carregando empresas...</div>
        ) : empresas.length === 0 ? (
          <div className="p-12 text-center">
            <Building2 size={48} className="mx-auto text-muted mb-4 opacity-50" />
            <h3 className="text-lg font-extrabold text-ink">Nenhuma empresa cadastrada</h3>
            <p className="text-muted text-sm mt-1 mb-6">Adicione a primeira empresa para conectar ao InnoFiscal e ao ACBr.</p>
            <Link 
              to="/empresas/nova" 
              className="bg-i9 text-white font-bold px-4 py-2 rounded-lg text-sm inline-flex items-center gap-2"
            >
              <Plus size={16} /> Cadastrar Empresa
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead>
                <tr className="bg-bg text-muted text-xs uppercase tracking-wider font-extrabold border-b border-line">
                  <th className="px-6 py-4">Empresa / Razão Social</th>
                  <th className="px-6 py-4">CNPJ</th>
                  <th className="px-6 py-4">Certificado Digital A1</th>
                  <th className="px-6 py-4">Integração ACBr</th>
                  <th className="px-6 py-4 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {empresas.map((emp) => (
                  <tr key={emp.id} className="hover:bg-i9-tint transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-bold text-ink">{emp.razao_social}</div>
                      {emp.nome_fantasia && (
                        <div className="text-xs text-muted font-medium">{emp.nome_fantasia}</div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-ink-soft font-mono">{emp.cnpj}</td>
                    <td className="px-6 py-4">
                      {getCertificadoStatus(emp.has_certificado, emp.certificado_vencimento)}
                    </td>
                    <td className="px-6 py-4">
                      {emp.acbr_sincronizado ? (
                        <span className="bg-blue-500/10 text-blue-400 border border-blue-500/20 text-xs px-2.5 py-1 rounded-full font-bold flex items-center w-fit gap-1.5" title={emp.acbr_ultimo_status}>
                          <Zap size={14} className="text-blue-400" /> ACBr Ativo
                        </span>
                      ) : (
                        <span className="bg-zinc-500/10 text-zinc-400 border border-zinc-500/20 text-xs px-2.5 py-1 rounded-full font-medium flex items-center w-fit gap-1.5" title={emp.acbr_ultimo_status}>
                          <ShieldCheck size={14} /> Pendente ACBr
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link to={`/empresas/${emp.id}`} className="text-i9 font-bold hover:underline bg-i9-tint px-3 py-1.5 rounded-md border border-i9/20">
                        Gerenciar / Certificado
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

