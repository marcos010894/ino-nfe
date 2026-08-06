import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../lib/api';

export default function NotasRecebidas() {
  const [rascunhos, setRascunhos] = useState<any[]>([]);
  const [tokenIntegracao, setTokenIntegracao] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    carregarRascunhos();
  }, []);

  const carregarRascunhos = async () => {
    try {
      const res = await api.get('/integracao/rascunhos');
      setRascunhos(res.data);
      
      const userRes = await api.get('/auth/me');
      setTokenIntegracao(userRes.data.token_integracao);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleEmitir = (id: number) => {
    navigate(`/emitir?rascunho=${id}`);
  };

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Notas Recebidas (Rascunhos)</h1>
          <p className="text-gray-500 mt-1">
            Vendas enviadas via integração aguardando emissão fiscal.
          </p>
        </div>
        {tokenIntegracao && (
          <div className="bg-blue-50 border border-blue-200 p-3 rounded-lg text-sm text-blue-800">
            <span className="font-bold block mb-1">Seu Token de Integração (API Key):</span>
            <code className="bg-white px-2 py-1 rounded border border-blue-100 select-all font-mono text-xs">
              {tokenIntegracao}
            </code>
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-center text-gray-500">Carregando...</div>
      ) : rascunhos.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
          Nenhuma nota pendente de emissão.
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Data</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Cliente</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Valor</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Ações</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {rascunhos.map((r) => {
                const dados = JSON.parse(r.json_venda || '{}');
                const nomeCliente = dados.cliente?.nome || 'Consumidor Final';
                return (
                  <tr key={r.id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(r.criado_em))}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {nomeCliente}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      R$ {r.valor_total?.toFixed(2) || '0.00'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button
                        onClick={() => handleEmitir(r.id)}
                        className="text-primary-600 hover:text-primary-900 bg-primary-50 px-3 py-1 rounded-md"
                      >
                        Gerar Nota
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
