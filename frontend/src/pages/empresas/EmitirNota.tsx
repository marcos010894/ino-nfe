import { useEffect, useState } from 'react';
import { FileText, Play, CheckCircle2, XCircle, Loader2, Download, ExternalLink, AlertCircle, Coins, Plus, Trash2, Edit3 } from 'lucide-react';
import api from '../../lib/api';
import { useSearchParams } from 'react-router-dom';

interface Empresa {
  id: number;
  razao_social: string;
  nome_fantasia: string;
  cnpj: string;
  has_certificado?: boolean;
}

/**
 * Extrai a mensagem de rejeição da resposta_integradora da ACBr.
 * O motivo real vive em `autorizacao.motivo_status` (+ `codigo_status` como cStat).
 * Fallbacks: `error.message` (erros HTTP ACBr), `motivo_status` (raiz), `motivo`,
 * `mensagem`, `erro` string. Sem esses, devolve string vazia (deixa caller usar default).
 */
function extrairMotivoRejeicao(r: any): string {
  if (!r || typeof r !== 'object') return '';
  const aut = r.autorizacao || {};
  const cstat = aut.codigo_status || r.codigo_status;
  const motivoAut = aut.motivo_status || r.motivo_status;
  if (motivoAut) {
    return cstat ? `cStat ${cstat}: ${motivoAut}` : String(motivoAut);
  }
  const err = r.error;
  if (err && typeof err === 'object') {
    const code = err.code ? `[${err.code}] ` : '';
    if (err.message) return `${code}${err.message}`;
  }
  if (typeof r.erro === 'string') return r.erro;
  if (r.motivo) return String(r.motivo);
  if (r.mensagem) return String(r.mensagem);
  return '';
}

interface ItemManual {
  codigo: string;
  nome: string;
  quantidade: number;
  valor_unitario: number;
  unidade: string;
}

export default function EmitirNota() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaSelecionada, setEmpresaSelecionada] = useState<string>('');
  
  const empSelecionadaObj = empresas.find(e => e.id.toString() === empresaSelecionada);
  
  // Abas de Modo: 'json' ou 'manual'
  const [modoEntrada, setModoEntrada] = useState<'json' | 'manual'>('json');

  // Modo JSON
  const [jsonVenda, setJsonVenda] = useState<string>('');
  const [jsonValido, setJsonValido] = useState<boolean>(false);
  const [erroJson, setErroJson] = useState<string>('');

  // Modo Manual Form
  const [clienteNome, setClienteNome] = useState<string>('');
  const [clienteCpf, setClienteCpf] = useState<string>('');
  const [descontoManual, setDescontoManual] = useState<number>(0);
  const [meioPagamento, setMeioPagamento] = useState<string>('17'); // Pix
  const [itensManuais, setItensManuais] = useState<ItemManual[]>([
    { codigo: 'JOIA01', nome: 'Anel Solitário', quantidade: 1, valor_unitario: 100.00, unidade: 'UN' }
  ]);

  // Novo Item Form
  const [novoItem, setNovoItem] = useState<ItemManual>({
    codigo: '',
    nome: '',
    quantidade: 1,
    valor_unitario: 0,
    unidade: 'UN'
  });

  const [previewVenda, setPreviewVenda] = useState<any>(null);
  
  // Estados de Emissão
  const [emitindo, setEmitindo] = useState<boolean>(false);
  const [resultado, setResultado] = useState<any>(null);
  const [erroEmissao, setErroEmissao] = useState<string>('');
  const [pollingActive, setPollingActive] = useState<boolean>(false);
  
  const [searchParams] = useSearchParams();
  const rascunhoId = searchParams.get('rascunho');

  // Carregar Rascunho se existir
  useEffect(() => {
    if (rascunhoId) {
      api.get(`/integracao/rascunhos/${rascunhoId}`)
        .then(res => {
          if (res.data.json_venda) {
            setJsonVenda(res.data.json_venda);
            validarEPreview(res.data.json_venda);
            setModoEntrada('json');
          }
        })
        .catch(err => {
          console.error("Erro ao carregar rascunho:", err);
          alert("Erro ao carregar o rascunho.");
        });
    }
  }, [rascunhoId]);

  const jsonExemplo = {
    cliente: {
      nome: "Consumidor Exemplo",
      cpf: "12345678909"
    },
    itens: [
      {
        codigo: "JOIA001",
        nome: "Anel de Prata Solitário",
        quantidade: 1,
        valor_unitario: 150.00,
        unidade: "UN"
      },
      {
        codigo: "JOIA002",
        nome: "Brinco Ouro 18k Argola",
        quantidade: 2,
        valor_unitario: 450.00,
        unidade: "PR"
      }
    ],
    desconto: 50.00,
    pagamentos: [
      {
        meio_pagamento: "17", // Pix
        valor: 1000.00
      }
    ]
  };

  // Carregar lista de empresas e inicializar JSON de exemplo
  useEffect(() => {
    const exemploStr = JSON.stringify(jsonExemplo, null, 2);
    setJsonVenda(exemploStr);
    setJsonValido(true);
    setPreviewVenda(jsonExemplo);

    api.get('/empresas/')
      .then(res => {
        setEmpresas(res.data);
        if (res.data.length > 0) {
          setEmpresaSelecionada(res.data[0].id.toString());
        }
      })
      .catch(err => {
        console.error("Erro ao carregar empresas:", err);
      });
  }, []);

  // Sincronizar Preview no Modo Manual
  useEffect(() => {
    if (modoEntrada === 'manual') {
      const vendaObj = {
        cliente: clienteNome || clienteCpf ? { nome: clienteNome, cpf: clienteCpf } : undefined,
        itens: itensManuais,
        desconto: descontoManual,
        pagamentos: [
          {
            meio_pagamento: meioPagamento,
            valor: Math.max(0, itensManuais.reduce((acc, it) => acc + (it.quantidade * it.valor_unitario), 0) - descontoManual)
          }
        ]
      };
      setPreviewVenda(vendaObj);
      setJsonValido(itensManuais.length > 0);
    }
  }, [modoEntrada, clienteNome, clienteCpf, descontoManual, meioPagamento, itensManuais]);

  const usarExemplo = () => {
    const str = JSON.stringify(jsonExemplo, null, 2);
    setJsonVenda(str);
    validarEPreview(str);
  };

  const handleJsonChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setJsonVenda(val);
    validarEPreview(val);
  };

  const validarEPreview = (val: string) => {
    if (!val.trim()) {
      setJsonValido(false);
      setErroJson('');
      setPreviewVenda(null);
      return;
    }

    try {
      const parsed = JSON.parse(val);
      if (!parsed.itens || !Array.isArray(parsed.itens) || parsed.itens.length === 0) {
        setJsonValido(false);
        setErroJson("O JSON precisa de um array 'itens' válido com ao menos um item.");
        setPreviewVenda(null);
        return;
      }
      setJsonValido(true);
      setErroJson('');
      setPreviewVenda(parsed);
    } catch (e: any) {
      setJsonValido(false);
      setErroJson(`JSON Inválido: ${e.message}`);
      setPreviewVenda(null);
    }
  };

  const adicionarItemManual = () => {
    if (!novoItem.nome || novoItem.valor_unitario <= 0) {
      alert("Por favor, preencha o Nome e o Valor Unitário do produto.");
      return;
    }
    const cod = novoItem.codigo || `PROD${itensManuais.length + 1}`;
    setItensManuais([...itensManuais, { ...novoItem, codigo: cod }]);
    setNovoItem({ codigo: '', nome: '', quantidade: 1, valor_unitario: 0, unidade: 'UN' });
  };

  const removerItemManual = (index: number) => {
    setItensManuais(itensManuais.filter((_, idx) => idx !== index));
  };

  // Enviar para emissão
  const emitirDocumento = async (modelo: string) => {
    setErroEmissao('');
    setResultado(null);

    if (!empresaSelecionada) {
      setErroEmissao("Selecione uma empresa emissora antes de prosseguir.");
      return;
    }

    let jsonPayload = '';
    if (modoEntrada === 'json') {
      if (!jsonVenda.trim()) {
        setErroEmissao("Cole the JSON de venda antes de emitir.");
        return;
      }
      try {
        const parsed = JSON.parse(jsonVenda);
        if (!parsed.itens || !Array.isArray(parsed.itens) || parsed.itens.length === 0) {
          setErroEmissao("O JSON da venda precisa conter ao menos um item em 'itens'.");
          return;
        }
        jsonPayload = jsonVenda;
      } catch (e: any) {
        setErroEmissao(`JSON da Venda Inválido: ${e.message}`);
        return;
      }
    } else {
      if (itensManuais.length === 0) {
        setErroEmissao("Adicione ao menos um item na lista de itens.");
        return;
      }
      const totalNota = Math.max(0, itensManuais.reduce((acc, it) => acc + (it.quantidade * it.valor_unitario), 0) - descontoManual);
      jsonPayload = JSON.stringify({
        cliente: clienteNome || clienteCpf ? { nome: clienteNome, cpf: clienteCpf } : undefined,
        itens: itensManuais,
        desconto: descontoManual,
        pagamentos: [{ meio_pagamento: meioPagamento, valor: totalNota }]
      });
    }

    setEmitindo(true);

    try {
      const res = await api.post(`/empresas/${empresaSelecionada}/notas/`, {
        json_venda: jsonPayload,
        modelo: modelo,
        rascunho_id: rascunhoId ? parseInt(rascunhoId) : undefined
      });
      
      const nota = res.data;
      let parsedResposta: any = {};
      if (nota.resposta_integradora) {
        try {
          parsedResposta = JSON.parse(nota.resposta_integradora);
        } catch (e) {
          parsedResposta = { motivo: String(nota.resposta_integradora) };
        }
      }

      
      if (nota.status === 'autorizada') {
        setResultado({
          sucesso: true,
          id: nota.id,
          chave: nota.chave_acesso,
          numero: nota.numero,
          serie: nota.serie,
          status: 'autorizada',
          pdf: nota.pdf_url,
          xml: nota.xml_url
        });
      } else if (nota.status === 'processando') {
        setResultado({
          sucesso: true,
          id: nota.id,
          chave: nota.chave_acesso,
          numero: nota.numero,
          serie: nota.serie,
          status: 'processando',
          pdf: nota.pdf_url,
          xml: nota.xml_url
        });
        iniciarPollingNfe(nota.id);
      } else {
        const msgErro = extrairMotivoRejeicao(parsedResposta) || "Rejeitada pela SEFAZ (Verifique regras de ICMS/CSC)";

        setResultado({
          sucesso: false,
          mensagem: msgErro
        });
      }
    } catch (err: any) {
      console.error("Erro na emissao de nota:", err);
      let detailMsg = err.message || "Erro desconhecido ao transmitir a nota.";
      if (err.response?.data?.detail) {
        const d = err.response.data.detail;
        if (typeof d === 'string') detailMsg = d;
        else if (Array.isArray(d)) detailMsg = d.map((e: any) => `${e.loc?.join('.') || 'Campo'}: ${e.msg}`).join(' | ');
        else detailMsg = JSON.stringify(d);
      } else if (err.response?.status === 401) {
        detailMsg = "Sua sessão expirou ou credenciais inválidas. Faça login novamente em /login.";
      }
      setErroEmissao(detailMsg);
    } finally {
      setEmitindo(false);
    }
  };



  const iniciarPollingNfe = (notaId: number) => {
    setPollingActive(true);
    const interval = setInterval(async () => {
      try {
        const res = await api.post(`/empresas/${empresaSelecionada}/notas/${notaId}/consultar-status`);
        const nota = res.data;
        if (nota.status !== 'processando') {
          clearInterval(interval);
          setPollingActive(false);
          if (nota.status === 'autorizada') {
            setResultado({
              sucesso: true,
              id: nota.id,
              chave: nota.chave_acesso,
              numero: nota.numero,
              serie: nota.serie,
              status: 'autorizada',
              pdf: nota.pdf_url,
              xml: nota.xml_url
            });
          } else {
            let parsed: any = {};
            if (nota.resposta_integradora) {
              try {
                parsed = JSON.parse(nota.resposta_integradora);
              } catch (e) {
                parsed = { motivo: String(nota.resposta_integradora) };
              }
            }
            const msg = extrairMotivoRejeicao(parsed) || "Rejeitada pela SEFAZ";
            setResultado({
              sucesso: false,
              mensagem: msg
            });
          }

        }
      } catch (err) {
        console.error("Erro no polling de status:", err);
      }
    }, 5000);
  };



  const baixarXML = async () => {
    if (!resultado || !resultado.id) return;
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/${resultado.id}/xml`, {
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${resultado.chave}.xml`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error(err);
      alert("Erro ao baixar o XML.");
    }
  };

  const baixarPDF = async () => {
    if (!resultado || !resultado.id) return;
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/${resultado.id}/pdf`, {
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch (err) {
      console.error(err);
      alert("Erro ao abrir o PDF.");
    }
  };

  const calcularSubtotal = () => {
    if (modoEntrada === 'json') {
      if (!previewVenda) return 0;
      return previewVenda.itens.reduce((acc: number, item: any) => acc + (item.quantidade * item.valor_unitario), 0);
    }
    return itensManuais.reduce((acc, it) => acc + (it.quantidade * it.valor_unitario), 0);
  };

  const calcularTotal = () => {
    if (modoEntrada === 'json') {
      if (!previewVenda) return 0;
      const sub = calcularSubtotal();
      const desc = parseFloat(previewVenda.desconto) || 0;
      return Math.max(0, sub - desc);
    }
    return Math.max(0, calcularSubtotal() - descontoManual);
  };

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-12">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-ink to-ink-soft bg-clip-text text-transparent">
          Emitir Nota Fiscal (NFC-e)
        </h1>
        <p className="text-muted text-sm font-medium mt-1">
          Escolha entre colar o JSON de venda do InnoSystem ou digitar todas as informações manualmente.
        </p>
      </div>

      {/* Abas de Entrada */}
      <div className="flex gap-2 border-b border-line pb-px">
        <button
          onClick={() => { setModoEntrada('json'); setPreviewVenda(null); setJsonValido(false); }}
          className={`px-4 py-2.5 text-sm font-bold border-b-2 transition-all flex items-center gap-2 ${
            modoEntrada === 'json' ? 'border-i9 text-i9' : 'border-transparent text-muted hover:text-ink'
          }`}
        >
          <FileText size={16} />
          Colar JSON de Venda
        </button>
        <button
          onClick={() => { setModoEntrada('manual'); }}
          className={`px-4 py-2.5 text-sm font-bold border-b-2 transition-all flex items-center gap-2 ${
            modoEntrada === 'manual' ? 'border-i9 text-i9' : 'border-transparent text-muted hover:text-ink'
          }`}
        >
          <Edit3 size={16} />
          Digitação Manual (Formulário)
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        
        {/* Lado Esquerdo: Inputs / Form */}
        <div className="flex flex-col gap-6">
          
          {/* Seletor de Empresa */}
          <div className="bg-card border border-line rounded-DEFAULT shadow p-5 flex flex-col gap-3">
            <label className="text-xs font-bold text-muted uppercase tracking-wider">Empresa Emissora</label>
            <select
              value={empresaSelecionada}
              onChange={(e) => setEmpresaSelecionada(e.target.value)}
              className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none font-semibold text-ink"
            >
              {empresas.length === 0 ? (
                <option value="">Nenhuma empresa cadastrada...</option>
              ) : (
                empresas.map(emp => (
                  <option key={emp.id} value={emp.id}>
                    {emp.nome_fantasia || emp.razao_social} - {emp.cnpj} {!emp.has_certificado ? ' (Sem Certificado A1)' : ''}
                  </option>
                ))
              )}
            </select>

            {empSelecionadaObj && !empSelecionadaObj.has_certificado && (
              <div className="bg-red-500/10 border border-red-500/30 text-red-400 p-3 rounded-lg text-xs font-semibold flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <AlertCircle size={15} /> Empresa sem Certificado Digital A1 ativo.
                </span>
                <a href={`/empresas/${empSelecionadaObj.id}`} className="underline font-bold hover:text-white">
                  Cadastrar Certificado →
                </a>
              </div>
            )}
          </div>


          {modoEntrada === 'json' ? (
            /* Modo JSON Area */
            <div className="bg-card border border-line rounded-DEFAULT shadow p-6 flex flex-col gap-4 relative">
              <div className="flex justify-between items-center">
                <label className="text-xs font-bold text-muted uppercase tracking-wider flex items-center gap-2">
                  <FileText size={16} /> JSON da Venda
                </label>
                <button 
                  onClick={usarExemplo}
                  className="text-xs text-i9 font-bold hover:underline flex items-center gap-1"
                >
                  Usar Exemplo de Venda
                </button>
              </div>

              <div className="relative">
                <textarea
                  value={jsonVenda}
                  onChange={handleJsonChange}
                  placeholder='Cole o JSON da venda aqui...'
                  rows={12}
                  className="w-full bg-field border border-line rounded-lg p-3 text-sm font-mono focus:border-i9 outline-none resize-none leading-relaxed text-ink-soft placeholder:text-muted/60"
                />
                <div className="absolute bottom-3 right-3 flex items-center gap-1.5 bg-card border border-line px-2 py-1 rounded-md text-xs font-bold shadow-sm">
                  {jsonValido ? (
                    <span className="text-i9 flex items-center gap-1">
                      <CheckCircle2 size={14} /> JSON Pronto
                    </span>
                  ) : jsonVenda ? (
                    <span className="text-warn flex items-center gap-1">
                      <XCircle size={14} /> Erro de Sintaxe
                    </span>
                  ) : (
                    <span className="text-muted">Aguardando dados</span>
                  )}
                </div>
              </div>

              {erroJson && (
                <div className="text-xs text-warn font-semibold bg-warn-tint border border-[#f0c9c4] p-3 rounded-lg flex items-start gap-2">
                  <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
                  <span>{erroJson}</span>
                </div>
              )}
            </div>
          ) : (
            /* Modo Digitação Manual */
            <div className="flex flex-col gap-6">
              
              {/* Cliente Form */}
              <div className="bg-card border border-line rounded-DEFAULT shadow p-5 flex flex-col gap-4">
                <h3 className="text-xs font-extrabold text-i9 uppercase tracking-wider border-b border-line pb-2">Identificação do Consumidor (Opcional)</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold text-muted uppercase">Nome do Cliente</label>
                    <input
                      type="text"
                      value={clienteNome}
                      onChange={(e) => setClienteNome(e.target.value)}
                      placeholder="Ex: João da Silva"
                      className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold text-muted uppercase">CPF ou CNPJ</label>
                    <input
                      type="text"
                      value={clienteCpf}
                      onChange={(e) => setClienteCpf(e.target.value)}
                      placeholder="Ex: 000.000.000-00"
                      className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Adicionar Itens Form */}
              <div className="bg-card border border-line rounded-DEFAULT shadow p-5 flex flex-col gap-4">
                <h3 className="text-xs font-extrabold text-i9 uppercase tracking-wider border-b border-line pb-2">Itens da Nota</h3>
                
                {/* Lista de Itens Adicionados */}
                <div className="divide-y divide-line-soft border border-line rounded-lg max-h-48 overflow-y-auto bg-field">
                  {itensManuais.length === 0 ? (
                    <div className="p-4 text-center text-xs text-muted">Nenhum produto adicionado à nota ainda.</div>
                  ) : (
                    itensManuais.map((it, idx) => (
                      <div key={idx} className="p-3 flex justify-between items-center text-xs">
                        <div className="flex flex-col">
                          <span className="font-bold text-ink">{it.nome}</span>
                          <span className="text-[10px] text-muted">Código: {it.codigo} | {it.quantidade} {it.unidade} × R$ {it.valor_unitario.toFixed(2)}</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => removerItemManual(idx)}
                          className="text-warn hover:bg-warn-tint p-1.5 rounded-lg transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))
                  )}
                </div>

                {/* Linha do Form do Novo Item */}
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 border-t border-line-soft pt-4 items-end">
                  <div className="flex flex-col gap-1 sm:col-span-2">
                    <label className="text-[10px] font-bold text-muted uppercase">Nome do Item *</label>
                    <input
                      type="text"
                      value={novoItem.nome}
                      onChange={(e) => setNovoItem({ ...novoItem, nome: e.target.value })}
                      placeholder="Anel, brinco..."
                      className="bg-field border border-line rounded-lg px-2.5 py-1.5 text-xs focus:border-i9 outline-none"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold text-muted uppercase">Qtd *</label>
                    <input
                      type="number"
                      min={1}
                      value={novoItem.quantidade}
                      onChange={(e) => setNovoItem({ ...novoItem, quantidade: parseInt(e.target.value) || 1 })}
                      className="bg-field border border-line rounded-lg px-2.5 py-1.5 text-xs focus:border-i9 outline-none font-mono"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold text-muted uppercase">Preço Un. *</label>
                    <input
                      type="number"
                      step="0.01"
                      value={novoItem.valor_unitario || ''}
                      onChange={(e) => setNovoItem({ ...novoItem, valor_unitario: parseFloat(e.target.value) || 0 })}
                      placeholder="0,00"
                      className="bg-field border border-line rounded-lg px-2.5 py-1.5 text-xs focus:border-i9 outline-none font-mono"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={adicionarItemManual}
                    className="bg-bg border border-line hover:bg-line-soft text-ink font-bold text-xs py-2 px-3 rounded-lg flex items-center justify-center gap-1 transition-colors h-max"
                  >
                    <Plus size={14} /> Adicionar
                  </button>
                </div>
              </div>

              {/* Informações Gerais de Venda Form */}
              <div className="bg-card border border-line rounded-DEFAULT shadow p-5 flex flex-col gap-4">
                <h3 className="text-xs font-extrabold text-i9 uppercase tracking-wider border-b border-line pb-2">Pagamento & Totais</h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold text-muted uppercase">Meio de Pagamento</label>
                    <select
                      value={meioPagamento}
                      onChange={(e) => setMeioPagamento(e.target.value)}
                      className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                    >
                      <option value="17">Pix</option>
                      <option value="01">Dinheiro</option>
                      <option value="03">Cartão de Crédito</option>
                      <option value="04">Cartão de Débito</option>
                      <option value="99">Outros</option>
                    </select>
                  </div>
                  <div className="flex flex-col gap-1.5 sm:col-span-2">
                    <label className="text-[10px] font-bold text-muted uppercase">Desconto Global (R$)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={descontoManual || ''}
                      onChange={(e) => setDescontoManual(parseFloat(e.target.value) || 0)}
                      placeholder="0,00"
                      className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none font-mono"
                    />
                  </div>
                </div>
              </div>

            </div>
          )}
        </div>

        {/* Lado Direito: Preview & Emissão */}
        <div className="flex flex-col gap-6">
          
          {/* Prévia da Venda */}
          <div className="bg-card border border-line rounded-DEFAULT shadow overflow-hidden flex flex-col min-h-[300px]">
            <div className="bg-bg px-6 py-4 border-b border-line flex justify-between items-center">
              <span className="text-xs font-bold text-muted uppercase tracking-wider">Prévia do Cupom</span>
              <span className="text-xs font-bold text-ink-soft">Consumidor</span>
            </div>

            {!previewVenda ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
                <Coins size={40} className="text-muted opacity-40 mb-3" />
                <h4 className="text-sm font-bold text-ink-soft">Aguardando dados de venda</h4>
                <p className="text-xs text-muted mt-1 max-w-[280px]">Insira o JSON de venda ou insira itens manualmente para gerar a prévia.</p>
              </div>
            ) : (
              <div className="p-6 flex flex-col gap-6">
                
                {/* Cliente */}
                {previewVenda.cliente && (
                  <div className="bg-line-soft rounded-lg p-3 border border-line text-xs flex flex-col gap-1">
                    <span className="font-bold text-ink-soft">DESTINATÁRIO / CLIENTE</span>
                    <div className="flex justify-between text-ink mt-1">
                      <span className="font-semibold">{previewVenda.cliente.nome || 'Consumidor não identificado'}</span>
                      {previewVenda.cliente.cpf && <span className="font-mono">{previewVenda.cliente.cpf}</span>}
                    </div>
                  </div>
                )}

                {/* Itens */}
                <div className="flex flex-col gap-2">
                  <span className="text-[10px] font-bold text-muted uppercase tracking-wider">Itens do Cupom</span>
                  <div className="border border-line rounded-lg overflow-hidden divide-y divide-line-soft">
                    {previewVenda.itens.map((item: any, idx: number) => (
                      <div key={idx} className="p-3 flex justify-between items-center text-xs hover:bg-i9-tint/20">
                        <div className="flex flex-col">
                          <span className="text-ink">{item.descricao || item.nome}</span>
                          <span className="text-muted text-[10px] font-medium">Qtd: {item.quantidade} {item.unidade || 'UN'} × R$ {Number(item.valor_unitario || 0).toFixed(2)}</span>
                        </div>
                        <span className="font-mono text-ink">R$ {(Number(item.quantidade || 0) * Number(item.valor_unitario || 0)).toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Totais */}
                <div className="flex flex-col gap-2 border-t border-line-soft pt-4">
                  <div className="flex justify-between text-xs text-muted font-medium">
                    <span>Subtotal dos itens</span>
                    <span className="font-mono">R$ {calcularSubtotal().toFixed(2)}</span>
                  </div>
                  {Number(previewVenda.desconto || 0) > 0 && (
                    <div className="flex justify-between text-xs text-warn font-semibold">
                      <span>Desconto</span>
                      <span className="font-mono">- R$ {Number(previewVenda.desconto).toFixed(2)}</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center text-sm font-bold text-ink border-t border-line-soft pt-3 mt-1">
                    <span>Valor Líquido</span>
                    <span className="text-lg text-i9 font-mono">R$ {calcularTotal().toFixed(2)}</span>
                  </div>
                </div>

                {/* Pagamentos */}
                {previewVenda.pagamentos && previewVenda.pagamentos.length > 0 && (
                  <div className="flex flex-col gap-2 bg-line-soft/50 border border-line-soft p-3 rounded-lg">
                    <span className="text-[10px] font-bold text-muted uppercase tracking-wider">Meios de Pagamento</span>
                    {previewVenda.pagamentos.map((pag: any, idx: number) => (
                      <div key={idx} className="flex justify-between text-xs font-semibold text-ink-soft">
                        <span>
                          {pag.meio_pagamento === "17" ? "PIX" : pag.meio_pagamento === "01" ? "Dinheiro" : pag.meio_pagamento === "03" ? "Cartão Crédito" : pag.meio_pagamento === "04" ? "Cartão Débito" : "Outros"}
                        </span>
                        <span className="font-mono text-ink">R$ {Number(pag.valor || 0).toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Botões de Transmissão */}
                <div className="flex flex-col gap-2">
                  {!empSelecionadaObj?.has_certificado && (
                    <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-xl text-xs font-semibold flex items-center gap-2 mb-2">
                      <AlertCircle size={16} />
                      Você precisa configurar o Certificado Digital da empresa antes de emitir notas.
                    </div>
                  )}
                  <button
                    onClick={() => emitirDocumento('65')}
                    disabled={emitindo || pollingActive || !jsonValido || !empSelecionadaObj?.has_certificado}
                    className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-to-b from-i9 to-i9-dark text-white font-extrabold text-sm shadow hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {emitindo && !pollingActive ? (
                      <>
                        <Loader2 size={16} className="animate-spin" />
                        Transmitindo NFC-e...
                      </>
                    ) : (
                      <>
                        <Play size={16} fill="white" />
                        Transmitir NFC-e (modelo 65)
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => emitirDocumento('55')}
                    disabled={emitindo || pollingActive || !jsonValido || !empSelecionadaObj?.has_certificado}
                    className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-white border border-i9 text-i9 font-extrabold text-sm shadow hover:bg-i9-tint/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {pollingActive ? (
                      <>
                        <Loader2 size={16} className="animate-spin" />
                        Consultando Status NF-e (Polling)...
                      </>
                    ) : (
                      <>
                        <Play size={16} className="text-i9" />
                        Transmitir NF-e (modelo 55)
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
          
          {/* Resultados da Emissão */}
          {erroEmissao && (
            <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-4 rounded-xl text-sm font-semibold flex items-start gap-2.5 shadow-sm">
              <AlertCircle size={18} className="mt-0.5 flex-shrink-0" />
              <div className="flex flex-col gap-0.5">
                <span className="font-extrabold">Falha de Transmissão</span>
                <span>{erroEmissao}</span>
              </div>
            </div>
          )}

          {resultado && (
            <div className={`border rounded-xl p-5 shadow-sm flex flex-col gap-4 ${
              resultado.status === 'processando'
                ? 'bg-[#e8f0fe] border-[#b0cbfa] text-[#0d47a1]'
                : resultado.sucesso 
                ? 'bg-[#e6f4ea] border-[#a3cfbb] text-[#0f5132]' 
                : 'bg-warn-tint border-[#f0c9c4] text-warn'
            }`}>
              <div className="flex items-start gap-3">
                {resultado.status === 'processando' ? (
                  <Loader2 size={24} className="animate-spin text-i9 flex-shrink-0 mt-0.5" />
                ) : resultado.sucesso ? (
                  <CheckCircle2 size={24} className="text-i9 flex-shrink-0 mt-0.5" />
                ) : (
                  <XCircle size={24} className="text-warn flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1 flex flex-col gap-1">
                  <h3 className="text-md font-extrabold">
                    {resultado.status === 'processando' 
                      ? 'NF-e em Processamento' 
                      : resultado.sucesso 
                      ? 'Documento Autorizado com Sucesso!' 
                      : 'Documento Rejeitado'}
                  </h3>
                  <p className="text-xs opacity-90">
                    {resultado.status === 'processando'
                      ? 'A nota fiscal modelo 55 foi enviada para a SEFAZ. O sistema está consultando o status automaticamente...'
                      : resultado.sucesso 
                      ? 'O documento fiscal foi validado e assinado digitalmente perante a SEFAZ.' 
                      : resultado.mensagem
                    }
                  </p>
                </div>
              </div>

              {resultado.sucesso && resultado.status !== 'processando' && (
                <div className="flex flex-col gap-3 border-t border-[#a3cfbb] pt-4 mt-1 text-xs">
                  <div className="flex justify-between font-mono bg-white/55 p-2.5 rounded-lg border border-[#a3cfbb]/30">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[10px] text-muted-foreground uppercase font-bold">Chave de Acesso</span>
                      <span className="tracking-wider text-ink font-semibold">{resultado.chave}</span>
                    </div>
                    <div className="flex flex-col gap-0.5 text-right">
                      <span className="text-[10px] text-muted-foreground uppercase font-bold">Nota / Série</span>
                      <span className="text-ink font-bold">{resultado.numero} / S.{resultado.serie}</span>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={baixarPDF}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-i9 text-white font-bold hover:bg-i9-dark transition-colors text-center"
                    >
                      <ExternalLink size={14} />
                      Visualizar DANFE (PDF)
                    </button>
                    <button
                      onClick={baixarXML}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-white border border-[#a3cfbb] text-ink font-bold hover:bg-[#d1e7dd] transition-colors text-center"
                    >
                      <Download size={14} />
                      Baixar XML
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
