import { useEffect, useState } from 'react';
import { FileText, Search, Download, ExternalLink, XOctagon, RefreshCw, AlertCircle, Calendar, ShieldCheck, HelpCircle, Eye, Loader2 } from 'lucide-react';
import api from '../../lib/api';

interface Nota {
  id: number;
  empresa_id: number;
  modelo: string;
  status: string;
  chave_acesso: string | null;
  numero: number | null;
  serie: number | null;
  valor_total: number;
  json_venda: string;
  resposta_integradora: string | null;
  xml_url: string | null;
  pdf_url: string | null;
  criado_em: string;
}

interface Empresa {
  id: number;
  razao_social: string;
  nome_fantasia: string;
  cnpj: string;
}

export default function CentralDocumentos() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaSelecionada, setEmpresaSelecionada] = useState<string>('');
  const [notas, setNotas] = useState<Nota[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Filtros
  const [filtroStatus, setFiltroStatus] = useState<string>('');
  const [filtroDataInicio, setFiltroDataInicio] = useState<string>('');
  const [filtroDataFim, setFiltroDataFim] = useState<string>('');

  // Modais
  const [notaSelecionadaCancel, setNotaSelecionadaCancel] = useState<Nota | null>(null);
  const [justificativa, setJustificativa] = useState<string>('');
  const [cancelando, setCancelando] = useState<boolean>(false);
  const [erroCancelamento, setErroCancelamento] = useState<string>('');

  const [notaSelecionadaReprocessar, setNotaSelecionadaReprocessar] = useState<Nota | null>(null);
  const [jsonEdicao, setJsonEdicao] = useState<string>('');
  const [reprocessando, setReprocessando] = useState<boolean>(false);
  const [erroReprocessar, setErroReprocessar] = useState<string>('');

  // Exportar Lote
  const [showExportModal, setShowExportModal] = useState<boolean>(false);
  const [exportIncluir, setExportIncluir] = useState<string>('ambos');
  const [exportando, setExportando] = useState<boolean>(false);
  const [erroExportacao, setErroExportacao] = useState<string>('');

  const executarExportacao = async () => {
    setExportando(true);
    setErroExportacao('');
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/exportar`, {
        params: {
          status: filtroStatus || undefined,
          data_inicio: filtroDataInicio || undefined,
          data_fim: filtroDataFim || undefined,
          incluir: exportIncluir
        },
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      
      const empresa = empresas.find(e => e.id.toString() === empresaSelecionada);
      const cnpj = empresa ? empresa.cnpj : 'lote';
      
      link.setAttribute('download', `notas_lote_${cnpj}_${new Date().toISOString().slice(0,10)}.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setShowExportModal(false);
    } catch (err: any) {
      console.error(err);
      setErroExportacao("Nenhuma nota autorizada/cancelada foi encontrada com os filtros atuais para gerar o ZIP.");
    } finally {
      setExportando(false);
    }
  };

  const [consultandoId, setConsultandoId] = useState<number | null>(null);

  const consultarStatus = async (notaId: number) => {
    setConsultandoId(notaId);
    try {
      await api.post(`/empresas/${empresaSelecionada}/notas/${notaId}/consultar-status`);
      carregarNotas();
    } catch (err) {
      console.error(err);
      alert("Erro ao consultar o status da nota na SEFAZ.");
    } finally {
      setConsultandoId(null);
    }
  };

  useEffect(() => {
    carregarEmpresas();
  }, []);

  useEffect(() => {
    if (empresaSelecionada) {
      carregarNotas();
    }
  }, [empresaSelecionada, filtroStatus, filtroDataInicio, filtroDataFim]);

  const carregarEmpresas = async () => {
    try {
      const res = await api.get('/empresas/');
      setEmpresas(res.data);
      if (res.data.length > 0) {
        setEmpresaSelecionada(res.data[0].id.toString());
      }
    } catch (error) {
      console.error("Erro ao carregar empresas:", error);
    }
  };

  const baixarXML = async (nota: Nota) => {
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/${nota.id}/xml`, {
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${nota.chave_acesso}.xml`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error(err);
      alert("Erro ao baixar o XML da nota.");
    }
  };

  const baixarPDF = async (nota: Nota) => {
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/${nota.id}/pdf`, {
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch (err) {
      console.error(err);
      alert("Erro ao abrir o PDF da nota.");
    }
  };

  const carregarNotas = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/`);
      let list: Nota[] = res.data;

      // Filtrar no frontend por status e datas se aplicável
      if (filtroStatus) {
        list = list.filter(n => n.status === filtroStatus);
      }
      if (filtroDataInicio) {
        const dInicio = new Date(filtroDataInicio);
        list = list.filter(n => new Date(n.criado_em) >= dInicio);
      }
      if (filtroDataFim) {
        const dFim = new Date(filtroDataFim);
        dFim.setHours(23, 59, 59, 999);
        list = list.filter(n => new Date(n.criado_em) <= dFim);
      }

      setNotas(list);
    } catch (error) {
      console.error("Erro ao carregar notas fiscais:", error);
    } finally {
      setLoading(false);
    }
  };

  const abrirModalCancelamento = (nota: Nota) => {
    setNotaSelecionadaCancel(nota);
    setJustificativa('');
    setErroCancelamento('');
  };

  const executarCancelamento = async () => {
    if (!notaSelecionadaCancel) return;
    if (justificativa.length < 15) {
      setErroCancelamento("A justificativa de cancelamento deve ter no mínimo 15 caracteres.");
      return;
    }

    setCancelando(true);
    setErroCancelamento('');
    try {
      await api.post(`/empresas/${empresaSelecionada}/notas/${notaSelecionadaCancel.id}/cancelar`, {
        justificativa
      });
      setNotaSelecionadaCancel(null);
      carregarNotas();
    } catch (err: any) {
      setErroCancelamento(err.response?.data?.detail || "Erro ao solicitar o cancelamento.");
    } finally {
      setCancelando(false);
    }
  };

  const abrirModalReprocessar = (nota: Nota) => {
    setNotaSelecionadaReprocessar(nota);
    setJsonEdicao(JSON.stringify(JSON.parse(nota.json_venda), null, 2));
    setErroReprocessar('');
  };

  const executarReprocessamento = async () => {
    if (!notaSelecionadaReprocessar) return;
    
    // Validar JSON antes de enviar
    try {
      JSON.parse(jsonEdicao);
    } catch (e: any) {
      setErroReprocessar(`JSON Inválido: ${e.message}`);
      return;
    }

    setReprocessando(true);
    setErroReprocessar('');
    try {
      await api.put(`/empresas/${empresaSelecionada}/notas/${notaSelecionadaReprocessar.id}/reprocessar`, {
        json_venda: jsonEdicao
      });
      setNotaSelecionadaReprocessar(null);
      carregarNotas();
    } catch (err: any) {
      setErroReprocessar(err.response?.data?.detail || "Erro ao reprocessar a nota.");
    } finally {
      setReprocessando(false);
    }
  };

  const extrairMotivoErro = (nota: Nota) => {
    if (!nota.resposta_integradora) return "Rejeição desconhecida";
    try {
      const parsed = JSON.parse(nota.resposta_integradora);
      return parsed.motivo || parsed.mensagem || parsed.erro || "Rejeitada pela SEFAZ";
    } catch {
      return nota.resposta_integradora;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'autorizada':
        return <span className="px-2 py-1 text-xs font-bold text-i9 bg-i9-tint rounded-full flex items-center gap-1 w-max"><ShieldCheck size={12} /> Autorizada</span>;
      case 'rejeitada':
        return <span className="px-2 py-1 text-xs font-bold text-warn bg-warn-tint rounded-full flex items-center gap-1 w-max"><AlertCircle size={12} /> Rejeitada</span>;
      case 'cancelada':
        return <span className="px-2 py-1 text-xs font-bold text-muted bg-line-soft rounded-full flex items-center gap-1 w-max"><XOctagon size={12} /> Cancelada</span>;
      default:
        return <span className="px-2 py-1 text-xs font-bold text-ink-soft bg-field border border-line rounded-full flex items-center gap-1 w-max"><RefreshCw size={12} className="animate-spin" /> Processando</span>;
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-12">
      
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">Central de Documentos</h1>
          <p className="text-muted text-sm font-medium mt-1">Gerencie, filtre, baixe ou cancele suas notas fiscais eletrônicas.</p>
        </div>

        {/* Seletor Empresa & Botão Exportar */}
        <div className="flex items-end gap-3 w-full md:w-auto">
          <div className="flex flex-col gap-1 w-full md:w-60">
            <label className="text-[10px] font-bold text-muted uppercase">Empresa Ativa</label>
            <select
              value={empresaSelecionada}
              onChange={(e) => setEmpresaSelecionada(e.target.value)}
              className="bg-card border border-line rounded-lg px-3 py-2 text-sm font-semibold text-ink focus:border-i9 outline-none shadow-sm w-full"
            >
              {empresas.map(emp => (
                <option key={emp.id} value={emp.id}>{emp.nome_fantasia || emp.razao_social}</option>
              ))}
            </select>
          </div>
          
          <button
            onClick={() => { setShowExportModal(true); setErroExportacao(''); }}
            className="bg-gradient-to-b from-i9 to-i9-dark hover:opacity-90 transition-opacity text-white font-bold px-4 py-2 rounded-lg text-sm flex items-center gap-2 shadow-sm h-[38px] flex-shrink-0"
          >
            <Download size={15} />
            Exportar Lote
          </button>
        </div>
      </div>

      {/* Barra de Filtros */}
      <div className="bg-card border border-line rounded-DEFAULT shadow p-5 grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] font-bold text-muted uppercase">Status</label>
          <select 
            value={filtroStatus} 
            onChange={(e) => setFiltroStatus(e.target.value)}
            className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none text-ink-soft"
          >
            <option value="">Todos os Status</option>
            <option value="autorizada">Autorizada</option>
            <option value="rejeitada">Rejeitada</option>
            <option value="cancelada">Cancelada</option>
            <option value="processando">Processando</option>
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] font-bold text-muted uppercase">Data Inicial</label>
          <div className="relative">
            <input 
              type="date" 
              value={filtroDataInicio} 
              onChange={(e) => setFiltroDataInicio(e.target.value)}
              className="w-full bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none text-ink-soft"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] font-bold text-muted uppercase">Data Final</label>
          <input 
            type="date" 
            value={filtroDataFim} 
            onChange={(e) => setFiltroDataFim(e.target.value)}
            className="w-full bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none text-ink-soft"
          />
        </div>
      </div>

      {/* Tabela de Notas */}
      <div className="bg-card border border-line rounded-DEFAULT shadow overflow-hidden">
        {loading ? (
          <div className="p-12 text-center font-bold text-muted flex items-center justify-center gap-2">
            <Loader2 className="animate-spin text-i9" size={20} /> Carregando documentos fiscais...
          </div>
        ) : notas.length === 0 ? (
          <div className="p-16 text-center">
            <FileText size={48} className="mx-auto text-muted mb-4 opacity-40" />
            <h3 className="text-lg font-extrabold text-ink">Nenhum documento encontrado</h3>
            <p className="text-muted text-sm mt-1">Tente ajustar seus filtros de pesquisa ou emita uma nova nota.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead>
                <tr className="bg-bg text-muted text-xs uppercase tracking-wider font-extrabold border-b border-line">
                  <th className="px-6 py-4">Data/Hora</th>
                  <th className="px-6 py-4">Número</th>
                  <th className="px-6 py-4">Modelo</th>
                  <th className="px-6 py-4">Valor Total</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {notas.map((nota) => (
                  <tr key={nota.id} className="hover:bg-i9-tint/10 transition-colors">
                    <td className="px-6 py-4 text-ink-soft">
                      {new Date(nota.criado_em).toLocaleString('pt-BR')}
                    </td>
                    <td className="px-6 py-4 font-mono font-bold text-ink">
                      {nota.numero ? `Nº ${nota.numero} (S. ${nota.serie})` : 'Pendente'}
                    </td>
                    <td className="px-6 py-4 text-xs font-bold text-muted">
                      {nota.modelo === '65' ? 'NFC-e (65)' : 'NF-e (55)'}
                    </td>
                    <td className="px-6 py-4 font-bold text-ink font-mono">
                      R$ {nota.valor_total.toFixed(2)}
                    </td>
                    <td className="px-6 py-4">
                      {getStatusBadge(nota.status)}
                    </td>
                    <td className="px-6 py-4 text-right flex justify-end gap-3 items-center">
                      {nota.status === 'autorizada' && (
                        <>
                          <button 
                            onClick={() => baixarPDF(nota)}
                            className="text-i9 hover:bg-i9-tint p-1.5 rounded-lg flex items-center gap-1 text-xs font-bold transition-colors"
                            title="Visualizar DANFE (PDF)"
                          >
                            <Eye size={14} /> DANFE
                          </button>
                          <button 
                            onClick={() => baixarXML(nota)}
                            className="text-ink-soft hover:bg-line-soft p-1.5 rounded-lg flex items-center gap-1 text-xs font-bold border border-line transition-colors"
                            title="Baixar XML"
                          >
                            <Download size={14} /> XML
                          </button>
                          <button
                            onClick={() => abrirModalCancelamento(nota)}
                            className="text-warn hover:bg-warn-tint p-1.5 rounded-lg text-xs font-bold transition-colors"
                          >
                            Cancelar
                          </button>
                        </>
                      )}

                      {nota.status === 'rejeitada' && (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => abrirModalReprocessar(nota)}
                            className="bg-i9 hover:opacity-90 text-white font-bold text-xs px-3 py-1.5 rounded-lg flex items-center gap-1 transition-opacity shadow-sm"
                          >
                            <RefreshCw size={12} />
                            Reprocessar
                          </button>
                          <button 
                            className="text-warn cursor-help p-1" 
                            title={extrairMotivoErro(nota)}
                          >
                            <HelpCircle size={15} />
                          </button>
                        </div>
                      )}

                      {nota.status === 'processando' && (
                        <button
                          onClick={() => consultarStatus(nota.id)}
                          disabled={consultandoId === nota.id}
                          className="bg-line-soft text-ink hover:bg-field border border-line font-bold text-xs px-3 py-1.5 rounded-lg flex items-center gap-1 transition-all shadow-sm disabled:opacity-50"
                        >
                          <RefreshCw size={12} className={consultandoId === nota.id ? "animate-spin" : ""} />
                          {consultandoId === nota.id ? "Consultando..." : "Consultar Status"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal Cancelamento */}
      {notaSelecionadaCancel && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-line rounded-xl shadow-lg max-w-md w-full p-6 flex flex-col gap-4 animate-in fade-in-50 zoom-in-95 duration-150">
            <div>
              <h3 className="text-lg font-extrabold text-ink">Cancelar Nota Fiscal</h3>
              <p className="text-xs text-muted mt-1">
                Chave: <span className="font-mono">{notaSelecionadaCancel.chave_acesso}</span>
              </p>
            </div>

            {erroCancelamento && (
              <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs font-semibold">
                {erroCancelamento}
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Justificativa *</label>
              <textarea
                value={justificativa}
                onChange={(e) => setJustificativa(e.target.value)}
                placeholder="Informe o motivo real do cancelamento da nota (mínimo 15 caracteres)..."
                rows={3}
                className="bg-field border border-line rounded-lg p-2.5 text-xs focus:border-i9 outline-none resize-none text-ink-soft"
              />
              <span className="text-[10px] text-muted text-right">
                {justificativa.length}/15 caracteres necessários
              </span>
            </div>

            <div className="flex justify-end gap-2 border-t border-line-soft pt-4 mt-1">
              <button
                onClick={() => setNotaSelecionadaCancel(null)}
                className="px-4 py-2 text-xs font-bold text-ink-soft bg-field border border-line rounded-lg hover:bg-line-soft transition-colors"
                disabled={cancelando}
              >
                Voltar
              </button>
              <button
                onClick={executarCancelamento}
                className="px-4 py-2 text-xs font-bold text-white bg-warn rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-1.5"
                disabled={cancelando || justificativa.length < 15}
              >
                {cancelando ? (
                  <>
                    <Loader2 size={12} className="animate-spin" />
                    Cancelando...
                  </>
                ) : 'Confirmar Cancelamento'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Reprocessar Erro */}
      {notaSelecionadaReprocessar && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-line rounded-xl shadow-lg max-w-xl w-full p-6 flex flex-col gap-4 animate-in fade-in-50 zoom-in-95 duration-150">
            <div>
              <h3 className="text-lg font-extrabold text-ink">Corrigir e Reprocessar Nota</h3>
              <p className="text-xs text-muted mt-1">Edite os dados da venda diretamente para submeter novamente à SEFAZ.</p>
            </div>

            {/* Banner de Erro da Rejeição */}
            <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs flex items-start gap-2">
              <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
              <div className="flex flex-col gap-0.5">
                <span className="font-bold">Motivo da Rejeição SEFAZ:</span>
                <span>{extrairMotivoErro(notaSelecionadaReprocessar)}</span>
              </div>
            </div>

            {erroReprocessar && (
              <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-2.5 rounded-lg text-xs font-semibold">
                {erroReprocessar}
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">JSON de Venda</label>
              <textarea
                value={jsonEdicao}
                onChange={(e) => setJsonEdicao(e.target.value)}
                rows={10}
                className="bg-field border border-line rounded-lg p-3 text-xs font-mono focus:border-i9 outline-none resize-none text-ink-soft leading-relaxed"
              />
            </div>

            <div className="flex justify-end gap-2 border-t border-line-soft pt-4 mt-1">
              <button
                onClick={() => setNotaSelecionadaReprocessar(null)}
                className="px-4 py-2 text-xs font-bold text-ink-soft bg-field border border-line rounded-lg hover:bg-line-soft transition-colors"
                disabled={reprocessando}
              >
                Cancelar
              </button>
              <button
                onClick={executarReprocessamento}
                className="px-4 py-2 text-xs font-bold text-white bg-gradient-to-b from-i9 to-i9-dark rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-1.5 shadow-sm"
                disabled={reprocessando}
              >
                {reprocessando ? (
                  <>
                    <Loader2 size={12} className="animate-spin" />
                    Enviando...
                  </>
                ) : (
                  <>
                    <RefreshCw size={12} />
                    Retransmitir Nota
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Modal Exportar em Lote */}
      {showExportModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-line rounded-xl shadow-lg max-w-md w-full p-6 flex flex-col gap-4 animate-in fade-in-50 zoom-in-95 duration-150">
            <div>
              <h3 className="text-lg font-extrabold text-ink">Exportar Lote de Notas (ZIP)</h3>
              <p className="text-xs text-muted mt-1">
                Gera um arquivo compactado contendo os documentos das notas fiscais de acordo com os filtros de status e data atuais.
              </p>
            </div>

            {erroExportacao && (
              <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs font-semibold">
                {erroExportacao}
              </div>
            )}

            {/* Opções de Inclusão */}
            <div className="flex flex-col gap-2.5">
              <span className="text-xs font-bold text-muted uppercase">Documentos a Incluir</span>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => setExportIncluir('ambos')}
                  className={`py-2 px-3 text-xs font-bold rounded-lg border transition-all ${
                    exportIncluir === 'ambos'
                      ? 'bg-i9 border-i9 text-white'
                      : 'bg-field border-line text-ink hover:bg-line-soft'
                  }`}
                >
                  XML & PDF
                </button>
                <button
                  type="button"
                  onClick={() => setExportIncluir('xml')}
                  className={`py-2 px-3 text-xs font-bold rounded-lg border transition-all ${
                    exportIncluir === 'xml'
                      ? 'bg-i9 border-i9 text-white'
                      : 'bg-field border-line text-ink hover:bg-line-soft'
                  }`}
                >
                  Apenas XML
                </button>
                <button
                  type="button"
                  onClick={() => setExportIncluir('pdf')}
                  className={`py-2 px-3 text-xs font-bold rounded-lg border transition-all ${
                    exportIncluir === 'pdf'
                      ? 'bg-i9 border-i9 text-white'
                      : 'bg-field border-line text-ink hover:bg-line-soft'
                  }`}
                >
                  Apenas PDF
                </button>
              </div>
            </div>

            {/* Sumário de Filtros Ativos */}
            <div className="bg-line-soft/50 border border-line-soft p-3 rounded-lg text-[11px] text-ink-soft flex flex-col gap-1.5">
              <span className="font-bold text-muted uppercase tracking-wider text-[9px]">Filtros que serão aplicados:</span>
              <div className="flex justify-between">
                <span>Status das Notas:</span>
                <span className="font-bold capitalize">{filtroStatus || "Todos"}</span>
              </div>
              <div className="flex justify-between">
                <span>Período:</span>
                <span className="font-bold">
                  {filtroDataInicio && filtroDataFim
                    ? `${new Date(filtroDataInicio).toLocaleDateString('pt-BR')} até ${new Date(filtroDataFim).toLocaleDateString('pt-BR')}`
                    : filtroDataInicio
                    ? `A partir de ${new Date(filtroDataInicio).toLocaleDateString('pt-BR')}`
                    : filtroDataFim
                    ? `Até ${new Date(filtroDataFim).toLocaleDateString('pt-BR')}`
                    : "Todo o histórico"}
                </span>
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-line-soft pt-4 mt-1">
              <button
                onClick={() => setShowExportModal(false)}
                className="px-4 py-2 text-xs font-bold text-ink-soft bg-field border border-line rounded-lg hover:bg-line-soft transition-colors"
                disabled={exportando}
              >
                Cancelar
              </button>
              <button
                onClick={executarExportacao}
                className="px-4 py-2 text-xs font-bold text-white bg-gradient-to-b from-i9 to-i9-dark rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-1.5 shadow-sm"
                disabled={exportando}
              >
                {exportando ? (
                  <>
                    <Loader2 size={12} className="animate-spin" />
                    Gerando ZIP...
                  </>
                ) : (
                  <>
                    <Download size={12} />
                    Iniciar Download
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
