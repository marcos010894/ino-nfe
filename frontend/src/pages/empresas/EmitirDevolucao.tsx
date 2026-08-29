import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Upload, KeyRound, Pencil, Plus, Trash2, Play, CheckCircle2, XCircle, Loader2, Download, ExternalLink, Settings } from 'lucide-react';
import api from '../../lib/api';

interface Empresa {
  id: number;
  razao_social: string;
  nome_fantasia: string;
  cnpj: string;
  uf?: string;
}

type ClasseCfop = 'auto' | '1' | '2' | '3' | '5' | '6' | '7';

const CLASSES_CFOP: { valor: ClasseCfop; label: string; hint: string }[] = [
  { valor: 'auto', label: 'Automático pela UF do destinatário',           hint: 'Compara UF da empresa com UF do destinatário. Sempre entrada (1xxx interna / 2xxx interestadual).' },
  { valor: '1',    label: '1xxx — Entrada · Interna (mesma UF)',           hint: 'Cliente devolveu pra loja, mesma UF.' },
  { valor: '2',    label: '2xxx — Entrada · Interestadual (UFs diferentes)', hint: 'Cliente devolveu pra loja, outra UF.' },
  { valor: '3',    label: '3xxx — Entrada · Exterior',                     hint: 'Devolução de importação recebida.' },
  { valor: '5',    label: '5xxx — Saída · Interna',                        hint: 'Loja devolve pro fornecedor, mesma UF.' },
  { valor: '6',    label: '6xxx — Saída · Interestadual',                  hint: 'Loja devolve pro fornecedor, outra UF.' },
  { valor: '7',    label: '7xxx — Saída · Exterior',                       hint: 'Devolução de mercadoria pra fornecedor no exterior.' },
];

interface Destinatario {
  cpf?: string;
  cnpj?: string;
  nome: string;
  ie?: string;
  logradouro?: string;
  numero?: string;
  complemento?: string;
  bairro?: string;
  cep?: string;
  municipio?: string;
  codigo_municipio?: string;
  uf?: string;
}

interface ItemDevolucao {
  codigo: string;
  descricao: string;
  ncm: string;
  cfop: string;
  quantidade: number;
  valor_unitario: number;
  unidade: string;
  cst_csosn: string;
  icms_aliquota?: number | null;
  pis_cst?: string | null;
  pis_aliquota?: number | null;
  cofins_cst?: string | null;
  cofins_aliquota?: number | null;
}

interface Transporte {
  mod_frete: number;  // 0=CIF, 1=FOB, 2=terceiros, 3=próprio emit, 4=próprio dest, 9=sem frete
  transportador_cnpj?: string;
  transportador_cpf?: string;
  transportador_nome?: string;
  transportador_ie?: string;
  transportador_endereco?: string;
  transportador_municipio?: string;
  transportador_uf?: string;
  veiculo_placa?: string;
  veiculo_uf?: string;
  veiculo_rntc?: string;
  volume_qtd?: number | null;
  volume_especie?: string;
  volume_peso_liquido?: number | null;
  volume_peso_bruto?: number | null;
}

type Origem = 'upload' | 'chave' | 'manual';

function extrairMotivoRejeicao(r: any): string {
  if (!r || typeof r !== 'object') return '';
  const aut = r.autorizacao || {};
  const cstat = aut.codigo_status || r.codigo_status;
  const motivoAut = aut.motivo_status || r.motivo_status;
  if (motivoAut) return cstat ? `cStat ${cstat}: ${motivoAut}` : String(motivoAut);
  if (r.error?.message) return `[${r.error.code || '?'}] ${r.error.message}`;
  if (typeof r.erro === 'string') return r.erro;
  if (r.motivo) return String(r.motivo);
  return '';
}

const itemVazio: ItemDevolucao = {
  codigo: '', descricao: '', ncm: '', cfop: '1202',
  quantidade: 1, valor_unitario: 0, unidade: 'UN', cst_csosn: '102',
  icms_aliquota: 0, pis_cst: '07', pis_aliquota: 0, cofins_cst: '07', cofins_aliquota: 0,
};

const destinatarioVazio: Destinatario = {
  cpf: '', cnpj: '', nome: '', ie: '',
  logradouro: '', numero: '', complemento: '', bairro: '',
  cep: '', municipio: '', codigo_municipio: '', uf: '',
};

const transporteVazio: Transporte = {
  mod_frete: 9,
  transportador_cnpj: '', transportador_cpf: '', transportador_nome: '', transportador_ie: '',
  transportador_endereco: '', transportador_municipio: '', transportador_uf: '',
  veiculo_placa: '', veiculo_uf: '', veiculo_rntc: '',
  volume_qtd: null, volume_especie: '', volume_peso_liquido: null, volume_peso_bruto: null,
};

const MOD_FRETE_OPCOES = [
  { valor: 9, label: '9 — Sem frete' },
  { valor: 0, label: '0 — Por conta do emitente (CIF)' },
  { valor: 1, label: '1 — Por conta do destinatário (FOB)' },
  { valor: 2, label: '2 — Por conta de terceiros' },
  { valor: 3, label: '3 — Próprio do remetente' },
  { valor: 4, label: '4 — Próprio do destinatário' },
];

export default function EmitirDevolucao() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaSelecionada, setEmpresaSelecionada] = useState<string>('');
  const empSelObj = empresas.find(e => e.id.toString() === empresaSelecionada);

  const [origem, setOrigem] = useState<Origem>('upload');
  const [previewCarregado, setPreviewCarregado] = useState<boolean>(false);
  const [carregandoPreview, setCarregandoPreview] = useState<boolean>(false);
  const [erroPreview, setErroPreview] = useState<string>('');

  const [chaveInput, setChaveInput] = useState<string>('');

  // Seções do formulário
  const [chaveReferenciada, setChaveReferenciada] = useState<string>('');
  const [motivo, setMotivo] = useState<string>('');
  const [naturezaOperacao, setNaturezaOperacao] = useState<string>('DEVOLUCAO DE MERCADORIA');
  const [destinatario, setDestinatario] = useState<Destinatario>(destinatarioVazio);
  const [itens, setItens] = useState<ItemDevolucao[]>([{ ...itemVazio }]);
  const [transporte, setTransporte] = useState<Transporte>({ ...transporteVazio });
  const [classeCfop, setClasseCfop] = useState<ClasseCfop>('auto');

  // Emissão
  const [emitindo, setEmitindo] = useState<boolean>(false);
  const [resultado, setResultado] = useState<any>(null);
  const [erroEmissao, setErroEmissao] = useState<string>('');

  useEffect(() => {
    api.get('/empresas/').then(res => {
      setEmpresas(res.data || []);
      if (res.data?.length > 0 && !empresaSelecionada) {
        setEmpresaSelecionada(res.data[0].id.toString());
      }
    }).catch(() => {});
  }, []);

  const aplicarPreview = (data: any) => {
    setChaveReferenciada(data.chave_referenciada || '');
    setNaturezaOperacao(data.natureza_operacao_sugerida || 'DEVOLUCAO DE MERCADORIA');
    setDestinatario({ ...destinatarioVazio, ...(data.destinatario || {}) });
    setItens((data.itens || []).map((i: any) => ({ ...itemVazio, ...i })));
    setPreviewCarregado(true);
  };

  const uploadXml = async (file: File) => {
    if (!empresaSelecionada) {
      setErroPreview('Selecione uma empresa antes de subir o XML.');
      return;
    }
    setCarregandoPreview(true);
    setErroPreview('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await api.post(`/empresas/${empresaSelecionada}/notas/devolucao/preview`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      aplicarPreview(res.data);
    } catch (err: any) {
      setErroPreview(err?.response?.data?.detail || 'Falha ao processar XML.');
    } finally {
      setCarregandoPreview(false);
    }
  };

  const buscarPorChave = async () => {
    if (!empresaSelecionada) {
      setErroPreview('Selecione uma empresa.');
      return;
    }
    if (chaveInput.length !== 44 || !/^\d+$/.test(chaveInput)) {
      setErroPreview('Chave deve ter 44 dígitos.');
      return;
    }
    setCarregandoPreview(true);
    setErroPreview('');
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/devolucao/preview-chave`, {
        params: { chave: chaveInput },
      });
      aplicarPreview(res.data);
    } catch (err: any) {
      setErroPreview(err?.response?.data?.detail || 'Falha ao buscar chave.');
    } finally {
      setCarregandoPreview(false);
    }
  };

  const irParaManual = () => {
    setChaveReferenciada('');
    setDestinatario(destinatarioVazio);
    setItens([{ ...itemVazio }]);
    setPreviewCarregado(true);
  };

  const setItemField = (idx: number, field: keyof ItemDevolucao, value: any) => {
    setItens(prev => prev.map((it, i) => i === idx ? { ...it, [field]: value } : it));
  };
  const addItem = () => setItens(prev => [...prev, { ...itemVazio }]);
  const removeItem = (idx: number) => setItens(prev => prev.filter((_, i) => i !== idx));

  // Resolve o dígito da classe do CFOP conforme a seleção. 'auto' compara UFs.
  const resolverPrimeiroDigito = (): string | null => {
    if (classeCfop !== 'auto') return classeCfop;
    const ufEmit = (empSelObj?.uf || '').trim().toUpperCase();
    const ufDest = (destinatario.uf || '').trim().toUpperCase();
    if (!ufEmit || !ufDest) return null;
    return ufEmit === ufDest ? '1' : '2';
  };

  const aplicarClasseCfopAosItens = () => {
    const primeiro = resolverPrimeiroDigito();
    if (!primeiro) {
      alert('Preencha a UF da empresa e do destinatário pra usar o modo Automático.');
      return;
    }
    setItens(prev => prev.map(it => {
      const cfop = (it.cfop || '').trim();
      if (cfop.length !== 4 || !/^\d{4}$/.test(cfop)) return { ...it, cfop: `${primeiro}202` };
      return { ...it, cfop: `${primeiro}${cfop.slice(1)}` };
    }));
  };

  const totalNota = itens.reduce((acc, it) => acc + (Number(it.quantidade) * Number(it.valor_unitario)), 0);

  const transmitir = async () => {
    setErroEmissao('');
    setResultado(null);

    if (!empresaSelecionada) return setErroEmissao('Selecione uma empresa.');
    if (chaveReferenciada.length !== 44 || !/^\d+$/.test(chaveReferenciada))
      return setErroEmissao('Chave da nota original inválida (44 dígitos).');
    if (motivo.trim().length < 15)
      return setErroEmissao('Motivo da devolução precisa ter pelo menos 15 caracteres.');
    if (!destinatario.nome) return setErroEmissao('Informe o nome do destinatário.');
    if (itens.length === 0) return setErroEmissao('Adicione pelo menos um item.');

    setEmitindo(true);
    try {
      const body = {
        chave_referenciada: chaveReferenciada,
        motivo,
        natureza_operacao: naturezaOperacao,
        destinatario,
        itens,
        transporte,
      };
      const res = await api.post(`/empresas/${empresaSelecionada}/notas/devolucao`, body);
      setResultado(res.data);
    } catch (err: any) {
      setErroEmissao(err?.response?.data?.detail || err?.message || 'Erro na transmissão.');
    } finally {
      setEmitindo(false);
    }
  };

  const baixarXML = async () => {
    if (!resultado?.id) return;
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/${resultado.id}/xml`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${resultado.chave_acesso || 'devolucao'}.xml`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch {
      alert('Erro ao baixar o XML.');
    }
  };

  const baixarPDF = async () => {
    if (!resultado?.id) return;
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/${resultado.id}/pdf`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch {
      alert('Erro ao abrir o PDF.');
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-12">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-ink to-ink-soft bg-clip-text text-transparent">
          Emitir NF-e de Devolução
        </h1>
        <p className="text-sm text-muted mt-1">
          NF-e mod. 55, finalidade 4. Suba o XML da nota original ou preencha manualmente.
        </p>
        {previewCarregado && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-i9-tint text-i9 font-bold">
              finNFe = 4 · Devolução
            </span>
            {chaveReferenciada && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-line-soft text-ink font-mono">
                NFref: {chaveReferenciada}
              </span>
            )}
            {naturezaOperacao && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-line-soft text-muted">
                {naturezaOperacao}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Empresa */}
      <div className="bg-card border border-line rounded-xl p-5">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="text-sm font-bold text-ink mb-2 block">Empresa emissora</label>
            <select
              value={empresaSelecionada}
              onChange={e => setEmpresaSelecionada(e.target.value)}
              className="w-full px-3 py-2 border border-line rounded-lg bg-white text-sm"
            >
              <option value="">Selecione...</option>
              {empresas.map(e => (
                <option key={e.id} value={e.id}>
                  {e.razao_social} — {e.cnpj}
                </option>
              ))}
            </select>
          </div>
          {empresaSelecionada && (
            <Link
              to={`/empresas/${empresaSelecionada}/regras`}
              title="Ajustar CFOP, CST/CSOSN, alíquotas e demais regras fiscais dessa empresa"
              className="inline-flex items-center gap-2 px-4 py-2 border border-line rounded-lg text-sm text-ink hover:bg-line/30 transition whitespace-nowrap"
            >
              <Settings size={16} /> Regras fiscais
            </Link>
          )}
        </div>
        <p className="text-xs text-muted mt-2">
          Antes de emitir uma devolução, confirme se as regras fiscais dessa empresa (CFOP, CST/CSOSN, alíquotas) estão atualizadas.
        </p>
      </div>

      {/* Passo 1: Origem */}
      {!previewCarregado && (
        <div className="bg-card border border-line rounded-xl p-5">
          <h2 className="text-lg font-bold text-ink mb-4">1. Como preencher os dados?</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
            <button
              onClick={() => setOrigem('upload')}
              className={`p-4 rounded-lg border text-left flex flex-col gap-2 transition-colors ${origem === 'upload' ? 'border-i9 bg-i9-tint' : 'border-line hover:bg-line-soft'}`}
            >
              <Upload size={18} className="text-i9" />
              <span className="font-bold text-sm text-ink">Subir XML</span>
              <span className="text-xs text-muted">Parser preenche todas as seções</span>
            </button>
            <button
              onClick={() => setOrigem('chave')}
              className={`p-4 rounded-lg border text-left flex flex-col gap-2 transition-colors ${origem === 'chave' ? 'border-i9 bg-i9-tint' : 'border-line hover:bg-line-soft'}`}
            >
              <KeyRound size={18} className="text-i9" />
              <span className="font-bold text-sm text-ink">Chave de acesso</span>
              <span className="text-xs text-muted">Nota já emitida no InnoFiscal</span>
            </button>
            <button
              onClick={() => setOrigem('manual')}
              className={`p-4 rounded-lg border text-left flex flex-col gap-2 transition-colors ${origem === 'manual' ? 'border-i9 bg-i9-tint' : 'border-line hover:bg-line-soft'}`}
            >
              <Pencil size={18} className="text-i9" />
              <span className="font-bold text-sm text-ink">Manual</span>
              <span className="text-xs text-muted">Preencher tudo do zero</span>
            </button>
          </div>

          {origem === 'upload' && (
            <div>
              <input
                type="file"
                accept=".xml"
                onChange={e => e.target.files?.[0] && uploadXml(e.target.files[0])}
                className="block w-full text-sm text-muted file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:font-bold file:bg-i9-tint file:text-i9 hover:file:bg-i9-tint/80"
              />
              <p className="text-xs text-muted mt-2">Arquivo .xml de NF-e autorizada, até 2 MB.</p>
            </div>
          )}

          {origem === 'chave' && (
            <div className="flex flex-col gap-2">
              <input
                type="text"
                value={chaveInput}
                onChange={e => setChaveInput(e.target.value.replace(/\D/g, '').slice(0, 44))}
                placeholder="44 dígitos"
                className="px-3 py-2 border border-line rounded-lg font-mono text-sm"
              />
              <button
                onClick={buscarPorChave}
                disabled={carregandoPreview || chaveInput.length !== 44}
                className="self-start px-4 py-2 bg-i9 text-white rounded-lg font-bold text-sm disabled:opacity-50"
              >
                {carregandoPreview ? 'Buscando...' : 'Buscar'}
              </button>
            </div>
          )}

          {origem === 'manual' && (
            <button
              onClick={irParaManual}
              className="px-4 py-2 bg-i9 text-white rounded-lg font-bold text-sm"
            >
              Ir para o formulário
            </button>
          )}

          {carregandoPreview && (
            <div className="mt-3 flex items-center gap-2 text-sm text-muted">
              <Loader2 size={14} className="animate-spin" /> Processando...
            </div>
          )}
          {erroPreview && (
            <div className="mt-3 flex items-center gap-2 text-sm text-warn">
              <XCircle size={14} /> {erroPreview}
            </div>
          )}
        </div>
      )}

      {previewCarregado && (
        <>
          {/* Seção 1: Nota de origem */}
          <section className="bg-card border border-line rounded-xl p-5">
            <h2 className="text-lg font-bold text-ink mb-4">1. Nota de origem</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-bold text-muted block mb-1">Chave de acesso (44)</label>
                <input
                  type="text"
                  value={chaveReferenciada}
                  onChange={e => setChaveReferenciada(e.target.value.replace(/\D/g, '').slice(0, 44))}
                  className="w-full px-3 py-2 border border-line rounded-lg font-mono text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-bold text-muted block mb-1">Natureza da operação</label>
                <input
                  type="text"
                  value={naturezaOperacao}
                  onChange={e => setNaturezaOperacao(e.target.value)}
                  className="w-full px-3 py-2 border border-line rounded-lg text-sm"
                />
              </div>
              <div className="md:col-span-2">
                <label className="text-xs font-bold text-muted block mb-1">Motivo da devolução (mín. 15 caracteres)</label>
                <textarea
                  value={motivo}
                  onChange={e => setMotivo(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 border border-line rounded-lg text-sm"
                />
              </div>
            </div>
          </section>

          {/* Seção 2: Emitente */}
          <section className="bg-card border border-line rounded-xl p-5">
            <h2 className="text-lg font-bold text-ink mb-4">2. Emitente (loja)</h2>
            {empSelObj ? (
              <div className="text-sm text-muted">
                <div className="font-bold text-ink">{empSelObj.razao_social}</div>
                <div>CNPJ: {empSelObj.cnpj}</div>
              </div>
            ) : (
              <div className="text-sm text-warn">Selecione uma empresa acima.</div>
            )}
          </section>

          {/* Seção 3: Destinatário */}
          <section className="bg-card border border-line rounded-xl p-5">
            <h2 className="text-lg font-bold text-ink mb-4">3. Destinatário</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input placeholder="Nome/Razão Social" value={destinatario.nome}
                onChange={e => setDestinatario({ ...destinatario, nome: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm md:col-span-2" />
              <input placeholder="CNPJ" value={destinatario.cnpj || ''}
                onChange={e => setDestinatario({ ...destinatario, cnpj: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm" />
              <input placeholder="CPF" value={destinatario.cpf || ''}
                onChange={e => setDestinatario({ ...destinatario, cpf: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm" />
              <input placeholder="Inscrição Estadual (ou ISENTO)" value={destinatario.ie || ''}
                onChange={e => setDestinatario({ ...destinatario, ie: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm" />
              <input placeholder="CEP" value={destinatario.cep || ''}
                onChange={e => setDestinatario({ ...destinatario, cep: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm" />
              <input placeholder="Logradouro" value={destinatario.logradouro || ''}
                onChange={e => setDestinatario({ ...destinatario, logradouro: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm md:col-span-2" />
              <input placeholder="Número" value={destinatario.numero || ''}
                onChange={e => setDestinatario({ ...destinatario, numero: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm" />
              <input placeholder="Bairro" value={destinatario.bairro || ''}
                onChange={e => setDestinatario({ ...destinatario, bairro: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm" />
              <input placeholder="Município" value={destinatario.municipio || ''}
                onChange={e => setDestinatario({ ...destinatario, municipio: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm" />
              <input placeholder="UF" value={destinatario.uf || ''}
                onChange={e => setDestinatario({ ...destinatario, uf: e.target.value.toUpperCase().slice(0, 2) })}
                className="px-3 py-2 border border-line rounded-lg text-sm" />
              <input placeholder="Código Município (IBGE)" value={destinatario.codigo_municipio || ''}
                onChange={e => setDestinatario({ ...destinatario, codigo_municipio: e.target.value })}
                className="px-3 py-2 border border-line rounded-lg text-sm" />
            </div>
          </section>

          {/* Seção 4: Itens */}
          <section className="bg-card border border-line rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-ink">4. Itens ({itens.length})</h2>
              <button onClick={addItem} className="flex items-center gap-1 px-3 py-1.5 bg-i9-tint text-i9 rounded-lg text-sm font-bold hover:bg-i9-tint/70">
                <Plus size={14} /> Adicionar
              </button>
            </div>

            {/* Operação fiscal — sobrescreve o 1º dígito do CFOP de todos os itens */}
            <div className="mb-4 p-3 bg-line-soft rounded-lg">
              <label className="text-xs font-bold text-muted block mb-1">Operação fiscal (classe do CFOP)</label>
              <div className="flex flex-col md:flex-row gap-2 md:items-center">
                <select
                  value={classeCfop}
                  onChange={e => setClasseCfop(e.target.value as ClasseCfop)}
                  className="flex-1 px-3 py-2 border border-line rounded-lg bg-white text-sm"
                >
                  {CLASSES_CFOP.map(c => (
                    <option key={c.valor} value={c.valor}>{c.label}</option>
                  ))}
                </select>
                <button
                  onClick={aplicarClasseCfopAosItens}
                  className="px-4 py-2 bg-i9 text-white rounded-lg font-bold text-sm hover:bg-i9-dark"
                >
                  Aplicar aos {itens.length} {itens.length === 1 ? 'item' : 'itens'}
                </button>
              </div>
              <div className="text-xs text-muted mt-2">
                {CLASSES_CFOP.find(c => c.valor === classeCfop)?.hint}
                {classeCfop === 'auto' && empSelObj?.uf && destinatario.uf && (
                  <>
                    {' · '}
                    <b>
                      {empSelObj.uf.toUpperCase() === (destinatario.uf || '').toUpperCase()
                        ? `${empSelObj.uf}→${destinatario.uf} = 1xxx (interna)`
                        : `${empSelObj.uf}→${destinatario.uf} = 2xxx (interestadual)`}
                    </b>
                  </>
                )}
              </div>
              <div className="text-xs text-muted mt-1">
                Sobrescreve só o <b>primeiro dígito</b> do CFOP de cada item (sufixo 202/411/949… é preservado). Ainda dá pra editar item a item na tabela abaixo.
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-line-soft">
                  <tr>
                    <th className="p-2 text-left">Código</th>
                    <th className="p-2 text-left">Descrição</th>
                    <th className="p-2 text-left">NCM</th>
                    <th className="p-2 text-left">CFOP</th>
                    <th className="p-2 text-left">Qtd</th>
                    <th className="p-2 text-left">V.Unit</th>
                    <th className="p-2 text-left">Un</th>
                    <th className="p-2 text-left">CST</th>
                    <th className="p-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {itens.map((it, idx) => (
                    <tr key={idx} className="border-b border-line">
                      <td className="p-1"><input className="w-20 px-1 py-1 border border-line rounded text-xs" value={it.codigo} onChange={e => setItemField(idx, 'codigo', e.target.value)} /></td>
                      <td className="p-1"><input className="w-40 px-1 py-1 border border-line rounded text-xs" value={it.descricao} onChange={e => setItemField(idx, 'descricao', e.target.value)} /></td>
                      <td className="p-1"><input className="w-20 px-1 py-1 border border-line rounded text-xs" value={it.ncm} onChange={e => setItemField(idx, 'ncm', e.target.value)} /></td>
                      <td className="p-1"><input className="w-16 px-1 py-1 border border-line rounded text-xs" value={it.cfop} onChange={e => setItemField(idx, 'cfop', e.target.value)} /></td>
                      <td className="p-1"><input type="number" step="0.01" className="w-16 px-1 py-1 border border-line rounded text-xs" value={it.quantidade} onChange={e => setItemField(idx, 'quantidade', Number(e.target.value))} /></td>
                      <td className="p-1"><input type="number" step="0.01" className="w-20 px-1 py-1 border border-line rounded text-xs" value={it.valor_unitario} onChange={e => setItemField(idx, 'valor_unitario', Number(e.target.value))} /></td>
                      <td className="p-1"><input className="w-12 px-1 py-1 border border-line rounded text-xs" value={it.unidade} onChange={e => setItemField(idx, 'unidade', e.target.value)} /></td>
                      <td className="p-1"><input className="w-14 px-1 py-1 border border-line rounded text-xs" value={it.cst_csosn} onChange={e => setItemField(idx, 'cst_csosn', e.target.value)} /></td>
                      <td className="p-1">
                        <button onClick={() => removeItem(idx)} className="text-warn p-1 hover:bg-warn-tint rounded">
                          <Trash2 size={12} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Seção 5: Transporte */}
          <section className="bg-card border border-line rounded-xl p-5">
            <h2 className="text-lg font-bold text-ink mb-4">5. Transporte</h2>
            <p className="text-xs text-muted mb-4">
              Opcional. Deixe modalidade em <b>9 — Sem frete</b> se a devolução não envolve transporte próprio ou contratado (grupo `transp` na SEFAZ).
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="md:col-span-2">
                <label className="text-xs font-bold text-muted block mb-1">Modalidade do frete (modFrete)</label>
                <select
                  value={transporte.mod_frete}
                  onChange={e => setTransporte({ ...transporte, mod_frete: Number(e.target.value) })}
                  className="w-full px-3 py-2 border border-line rounded-lg bg-white text-sm"
                >
                  {MOD_FRETE_OPCOES.map(o => (
                    <option key={o.valor} value={o.valor}>{o.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {transporte.mod_frete !== 9 && (
              <>
                <div className="mt-4 pt-3 border-t border-line">
                  <div className="text-xs font-bold text-ink mb-2">Transportador</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <input placeholder="CNPJ (só dígitos)" value={transporte.transportador_cnpj || ''}
                      onChange={e => setTransporte({ ...transporte, transportador_cnpj: e.target.value.replace(/\D/g, '').slice(0, 14) })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                    <input placeholder="CPF (só dígitos, se não tiver CNPJ)" value={transporte.transportador_cpf || ''}
                      onChange={e => setTransporte({ ...transporte, transportador_cpf: e.target.value.replace(/\D/g, '').slice(0, 11) })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                    <input placeholder="Nome / Razão Social" value={transporte.transportador_nome || ''}
                      onChange={e => setTransporte({ ...transporte, transportador_nome: e.target.value })}
                      className="px-3 py-2 border border-line rounded-lg text-sm md:col-span-2" />
                    <input placeholder="Inscrição Estadual (ou ISENTO)" value={transporte.transportador_ie || ''}
                      onChange={e => setTransporte({ ...transporte, transportador_ie: e.target.value.toUpperCase() })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                    <input placeholder="UF" value={transporte.transportador_uf || ''}
                      onChange={e => setTransporte({ ...transporte, transportador_uf: e.target.value.toUpperCase().slice(0, 2) })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                    <input placeholder="Endereço" value={transporte.transportador_endereco || ''}
                      onChange={e => setTransporte({ ...transporte, transportador_endereco: e.target.value })}
                      className="px-3 py-2 border border-line rounded-lg text-sm md:col-span-2" />
                    <input placeholder="Município" value={transporte.transportador_municipio || ''}
                      onChange={e => setTransporte({ ...transporte, transportador_municipio: e.target.value })}
                      className="px-3 py-2 border border-line rounded-lg text-sm md:col-span-2" />
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-line">
                  <div className="text-xs font-bold text-ink mb-2">Veículo</div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <input placeholder="Placa (sem hífen)" value={transporte.veiculo_placa || ''}
                      onChange={e => setTransporte({ ...transporte, veiculo_placa: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 7) })}
                      className="px-3 py-2 border border-line rounded-lg text-sm font-mono" />
                    <input placeholder="UF" value={transporte.veiculo_uf || ''}
                      onChange={e => setTransporte({ ...transporte, veiculo_uf: e.target.value.toUpperCase().slice(0, 2) })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                    <input placeholder="RNTC (ANTT)" value={transporte.veiculo_rntc || ''}
                      onChange={e => setTransporte({ ...transporte, veiculo_rntc: e.target.value })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-line">
                  <div className="text-xs font-bold text-ink mb-2">Volume</div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <input type="number" min="0" step="1" placeholder="Quantidade"
                      value={transporte.volume_qtd ?? ''}
                      onChange={e => setTransporte({ ...transporte, volume_qtd: e.target.value === '' ? null : Number(e.target.value) })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                    <input placeholder="Espécie (CX, PC…)" value={transporte.volume_especie || ''}
                      onChange={e => setTransporte({ ...transporte, volume_especie: e.target.value.toUpperCase() })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                    <input type="number" min="0" step="0.001" placeholder="Peso líquido (kg)"
                      value={transporte.volume_peso_liquido ?? ''}
                      onChange={e => setTransporte({ ...transporte, volume_peso_liquido: e.target.value === '' ? null : Number(e.target.value) })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                    <input type="number" min="0" step="0.001" placeholder="Peso bruto (kg)"
                      value={transporte.volume_peso_bruto ?? ''}
                      onChange={e => setTransporte({ ...transporte, volume_peso_bruto: e.target.value === '' ? null : Number(e.target.value) })}
                      className="px-3 py-2 border border-line rounded-lg text-sm" />
                  </div>
                </div>
              </>
            )}
          </section>

          {/* Seção 6: Totais e transmissão */}
          <section className="bg-card border border-line rounded-xl p-5">
            <h2 className="text-lg font-bold text-ink mb-4">6. Totais e transmissão</h2>
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-sm text-muted">Valor total</div>
                <div className="text-2xl font-extrabold text-ink">R$ {totalNota.toFixed(2)}</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-muted">Finalidade</div>
                <div className="font-bold text-ink">4 — Devolução</div>
              </div>
            </div>

            <button
              onClick={transmitir}
              disabled={emitindo}
              className="w-full flex items-center justify-center gap-2 py-3 bg-i9 text-white rounded-lg font-bold hover:bg-i9-dark disabled:opacity-50"
            >
              {emitindo ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {emitindo ? 'Transmitindo...' : 'Transmitir SEFAZ'}
            </button>

            {erroEmissao && (
              <div className="mt-3 flex items-center gap-2 text-sm text-warn">
                <XCircle size={14} /> {erroEmissao}
              </div>
            )}
          </section>

          {resultado && (
            <section className="bg-card border border-line rounded-xl p-5">
              <h2 className="text-lg font-bold text-ink mb-4 flex items-center gap-2">
                {resultado.status === 'autorizada' ? (
                  <><CheckCircle2 className="text-ok" size={20} /> Autorizada</>
                ) : resultado.status === 'processando' ? (
                  <><Loader2 className="text-i9 animate-spin" size={20} /> Processando</>
                ) : (
                  <><XCircle className="text-warn" size={20} /> {resultado.status}</>
                )}
              </h2>
              {resultado.chave_acesso && (
                <div className="text-xs font-mono text-muted mb-3 break-all">Chave: {resultado.chave_acesso}</div>
              )}
              {resultado.status === 'rejeitada' && resultado.resposta_integradora && (
                <div className="text-sm text-warn mb-3">
                  {extrairMotivoRejeicao(JSON.parse(resultado.resposta_integradora))}
                </div>
              )}
              {resultado.status === 'autorizada' && (
                <div className="flex gap-2">
                  <button onClick={baixarXML} className="flex items-center gap-2 px-3 py-2 bg-i9-tint text-i9 rounded-lg text-sm font-bold">
                    <Download size={14} /> Baixar XML
                  </button>
                  <button onClick={baixarPDF} className="flex items-center gap-2 px-3 py-2 bg-i9-tint text-i9 rounded-lg text-sm font-bold">
                    <ExternalLink size={14} /> Abrir DANFE
                  </button>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
