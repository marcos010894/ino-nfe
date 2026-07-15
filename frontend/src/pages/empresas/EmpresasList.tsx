import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Building2, Plus, AlertCircle, CheckCircle2 } from 'lucide-react';
import api from '../../lib/api';

interface Empresa {
  id: int;
  razao_social: string;
  cnpj: string;
  certificado?: {
    id: int;
    validade: string;
  };
}

export default function EmpresasList() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [loading, setLoading] = useState(true);

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

  const getCertificadoStatus = (validade?: string) => {
    if (!validade) return <span className="text-muted text-xs font-semibold flex items-center gap-1"><AlertCircle size={14} /> Sem certificado</span>;
    
    const dataValidade = new Date(validade);
    const hoje = new Date();
    const difTempo = dataValidade.getTime() - hoje.getTime();
    const difDias = Math.ceil(difTempo / (1000 * 3600 * 24));
    
    if (difDias < 0) {
      return <span className="text-warn text-xs font-bold flex items-center gap-1"><AlertCircle size={14} /> Vencido</span>;
    } else if (difDias <= 30) {
      return <span className="text-pend text-xs font-bold flex items-center gap-1"><AlertCircle size={14} /> Vence em {difDias} dias</span>;
    } else {
      return <span className="text-ok text-xs font-bold flex items-center gap-1"><CheckCircle2 size={14} /> Válido</span>;
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Empresas</h1>
          <p className="text-muted text-sm font-medium mt-1">Gerencie os emitentes e certificados digitais.</p>
        </div>
        <Link 
          to="/empresas/nova" 
          className="bg-gradient-to-b from-ok to-[#1a7040] hover:opacity-90 transition-opacity text-white font-bold px-4 py-2 rounded-lg text-sm flex items-center gap-2 shadow-sm"
        >
          <Plus size={16} strokeWidth={3} />
          Nova Empresa
        </Link>
      </div>

      <div className="bg-card border border-line rounded-DEFAULT shadow overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-muted font-bold">Carregando...</div>
        ) : empresas.length === 0 ? (
          <div className="p-12 text-center">
            <Building2 size={48} className="mx-auto text-muted mb-4 opacity-50" />
            <h3 className="text-lg font-extrabold text-ink">Nenhuma empresa cadastrada</h3>
            <p className="text-muted text-sm mt-1 mb-6">Adicione a primeira empresa para começar a emitir notas.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead>
                <tr className="bg-bg text-muted text-xs uppercase tracking-wider font-extrabold border-b border-line">
                  <th className="px-6 py-4">Razão Social</th>
                  <th className="px-6 py-4">CNPJ</th>
                  <th className="px-6 py-4">Certificado</th>
                  <th className="px-6 py-4 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {empresas.map((emp) => (
                  <tr key={emp.id} className="hover:bg-i9-tint transition-colors">
                    <td className="px-6 py-4 font-bold text-ink">{emp.razao_social}</td>
                    <td className="px-6 py-4 text-ink-soft">{emp.cnpj}</td>
                    <td className="px-6 py-4">
                      {getCertificadoStatus(emp.certificado?.validade)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link to={`/empresas/${emp.id}`} className="text-i9 font-bold hover:underline">Editar</Link>
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
