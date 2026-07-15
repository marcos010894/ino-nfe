import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Plus, CheckCircle2, FileText } from 'lucide-react';
import api from '../../lib/api';

interface RegraFiscal {
  id: number;
  nome: string;
  cfop: string;
  ncm_padrao: string;
  padrao: boolean;
}

export default function RegrasFiscaisList() {
  const { id } = useParams(); // empresa_id
  const [regras, setRegras] = useState<RegraFiscal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    carregarRegras();
  }, [id]);

  const carregarRegras = async () => {
    try {
      const res = await api.get(`/empresas/${id}/regras/`);
      setRegras(res.data);
    } catch (error) {
      console.error("Erro ao carregar regras fiscais:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <Link to={`/empresas/${id}`} className="text-muted hover:text-ink transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-extrabold tracking-tight">Regras Fiscais</h1>
          <p className="text-muted text-sm font-medium mt-1">Configuração tributária base para emissão de notas.</p>
        </div>
        <Link 
          to={`/empresas/${id}/regras/nova`}
          className="bg-gradient-to-b from-i9 to-i9-dark hover:opacity-90 transition-opacity text-white font-bold px-4 py-2 rounded-lg text-sm flex items-center gap-2 shadow-sm"
        >
          <Plus size={16} strokeWidth={3} />
          Nova Regra
        </Link>
      </div>

      <div className="bg-card border border-line rounded-DEFAULT shadow overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-muted font-bold">Carregando...</div>
        ) : regras.length === 0 ? (
          <div className="p-12 text-center">
            <FileText size={48} className="mx-auto text-muted mb-4 opacity-50" />
            <h3 className="text-lg font-extrabold text-ink">Nenhuma regra fiscal configurada</h3>
            <p className="text-muted text-sm mt-1 mb-6">Adicione regras (como "Venda no Estado") para facilitar a emissão de notas.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead>
                <tr className="bg-bg text-muted text-xs uppercase tracking-wider font-extrabold border-b border-line">
                  <th className="px-6 py-4">Nome da Regra</th>
                  <th className="px-6 py-4">CFOP</th>
                  <th className="px-6 py-4">NCM Padrão</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {regras.map((regra) => (
                  <tr key={regra.id} className="hover:bg-i9-tint transition-colors">
                    <td className="px-6 py-4 font-bold text-ink">{regra.nome}</td>
                    <td className="px-6 py-4 font-mono text-ink-soft">{regra.cfop}</td>
                    <td className="px-6 py-4 font-mono text-ink-soft">{regra.ncm_padrao}</td>
                    <td className="px-6 py-4">
                      {regra.padrao ? (
                        <span className="text-i9 text-xs font-bold flex items-center gap-1 bg-i9-tint px-2 py-1 rounded-full w-max">
                          <CheckCircle2 size={14} /> Padrão
                        </span>
                      ) : (
                        <span className="text-muted text-xs">Opcional</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link to={`/empresas/${id}/regras/${regra.id}`} className="text-i9 font-bold hover:underline">Editar</Link>
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
