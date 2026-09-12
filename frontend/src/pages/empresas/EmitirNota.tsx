import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle, CheckCircle2, Loader2, Lock, Mail, Printer,
  Trash2, XCircle, Copy, ShieldAlert, Download, Send,
} from 'lucide-react';
import api from '../../lib/api';

/**
 * Tela de emissão v3 — orientada ao usuário final da loja.
 *
 * A venda vem pronta do InnoSystem (via /integracao/receber-venda) e chega aqui
 * como rascunho (?rascunho=<id>). O operador **não pode editar** — só confere,
 * emite ou exclui e refaz na origem. Editar aqui criaria divergência entre o que
 * o InnoSystem registrou e o que a SEFAZ autorizou.
 *
 * Fluxo dev (JSON colado / entrada manual) foi movido para /emitir/admin
 * (EmitirNotaAdmin.tsx). Cadeado no rodapé abre gaveta técnica com senha.
 */

const SENHA_TECNICA = '010894';

interface Empresa {
  id: number;
  razao_social: string;
  nome_fantasia: string;
  cnpj: string;
  has_certificado?: boolean;
  has_csc_token?: boolean;
}

interface Rascunho {
  id: number;
  status: string;
  modelo: string;
  chave_acesso?: string | null;
  numero?: number | null;
  serie?: number | null;
  valor_total: number;
  json_venda: string;
  payload_enviado?: string | null;
  resposta_integradora?: string | null;
  criado_em: string;
}

type Etapa =
  | 'ocioso'          // rascunho carregado, aguardando emissão
  | 'transmitindo'    // enviando pra SEFAZ
  | 'autorizada'
  | 'rejeitada'
  | 'processando'     // NF-e assíncrona, polling
  | 'invalidada';     // erro de validação backend (400)

function fmtMoeda(v: number) {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function agrupar(chave: string) {
  return chave.replace(/(.{4})/g, '$1 ').trim();
}
function motivoRejeicao(r: any): { motivo: string; cstat: string } {
  if (!r || typeof r !== 'object') return { motivo: '', cstat: '' };
  const aut = r.autorizacao || {};
  const cstat = aut.codigo_status || r.codigo_status || (r.error && r.error.code) || '';
  const motivo =
    aut.motivo_status || r.motivo_status || (r.error && r.error.message) ||
    r.motivo || r.mensagem || (typeof r.erro === 'string' ? r.erro : '') || '';
  return { motivo: String(motivo), cstat: String(cstat) };
}

export default function EmitirNota() {
  const [searchParams] = useSearchParams();
  const rascunhoId = searchParams.get('rascunho');

  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaId, setEmpresaId] = useState<string>('');
  const [rascunho, setRascunho] = useState<Rascunho | null>(null);
  const [carregandoRascunho, setCarregandoRascunho] = useState<boolean>(!!rascunhoId);
  const [etapa, setEtapa] = useState<Etapa>('ocioso');
  const [notaEmitida, setNotaEmitida] = useState<Rascunho | null>(null);
  const [erroMsg, setErroMsg] = useState<string>('');
  const [pollingActive, setPollingActive] = useState<boolean>(false);

  // Preview / confirmação antes de mandar SEFAZ
  const [previewOpen, setPreviewOpen] = useState<boolean>(false);
  const [previewModelo, setPreviewModelo] = useState<'55' | '65' | null>(null);
  const [previewNumero, setPreviewNumero] = useState<string>('');
  const [previewSerie, setPreviewSerie] = useState<number>(1);
  const [previewFonte, setPreviewFonte] = useState<string>('');
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);
  const [previewErro, setPreviewErro] = useState<string>('');

  // Cadeado técnico
  const [gavetaAberta, setGavetaAberta] = useState<boolean>(false);
  const [modalSenhaAberto, setModalSenhaAberto] = useState<boolean>(false);
  const [senhaInput, setSenhaInput] = useState<string>('');
  const [erroSenha, setErroSenha] = useState<string>('');
  const [abaGaveta, setAbaGaveta] = useState<'ent' | 'sai' | 'val' | 'log'>('ent');
  const senhaRef = useRef<HTMLInputElement>(null);

  // Toast simples
  const [toast, setToast] = useState<string>('');
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(''), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  // --- Carregamento inicial: empresas + rascunho (se houver) ---
  useEffect(() => {
    api.get('/empresas/').then((res) => {
      setEmpresas(res.data);
      if (res.data.length > 0) setEmpresaId(String(res.data[0].id));
    }).catch((e) => console.error('Erro empresas:', e));
  }, []);

  useEffect(() => {
    if (!rascunhoId) return;
    setCarregandoRascunho(true);
    api.get(`/integracao/rascunhos/${rascunhoId}`)
      .then((res) => setRascunho(res.data))
      .catch(() => setErroMsg('Não foi possível carregar o rascunho — verifique se ele ainda existe.'))
      .finally(() => setCarregandoRascunho(false));
  }, [rascunhoId]);

  // ESC fecha modal/gaveta
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (previewOpen) setPreviewOpen(false);
      else if (modalSenhaAberto) setModalSenhaAberto(false);
      else if (gavetaAberta) setGavetaAberta(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [previewOpen, modalSenhaAberto, gavetaAberta]);

  // Parse do json_venda pra render de conferência
  const venda = useMemo(() => {
    const fonte = notaEmitida || rascunho;
    if (!fonte) return null;
    try { return JSON.parse(fonte.json_venda); } catch { return null; }
  }, [rascunho, notaEmitida]);

  // --- Preview: pede o próximo nº ao backend e abre modal de confirmação ---
  async function abrirPreview(modelo: '55' | '65') {
    if (!empresaId) { setErroMsg('Selecione uma empresa emissora.'); return; }
    if (!rascunho) { setErroMsg('Nenhuma venda carregada para emitir.'); return; }
    setErroMsg('');
    setPreviewErro('');
    setPreviewModelo(modelo);
    setPreviewLoading(true);
    setPreviewOpen(true);
    try {
      const r = await api.get(`/empresas/${empresaId}/notas/proximo-numero`, { params: { modelo } });
      setPreviewNumero(String(r.data.proximo_numero));
      setPreviewSerie(Number(r.data.serie));
      setPreviewFonte(String(r.data.fonte));
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || 'Não foi possível calcular o próximo número.';
      setPreviewErro(String(detail));
    } finally {
      setPreviewLoading(false);
    }
  }

  // --- Emissão (chamada só após confirmação no modal de preview) ---
  async function emitir(modelo: '55' | '65', numeroOverride?: number) {
    if (!empresaId) { setErroMsg('Selecione uma empresa emissora.'); return; }
    if (!rascunho) { setErroMsg('Nenhuma venda carregada para emitir.'); return; }
    setErroMsg('');
    setEtapa('transmitindo');
    setPreviewOpen(false);
    try {
      const res = await api.post(`/empresas/${empresaId}/notas/`, {
        json_venda: rascunho.json_venda,
        modelo,
        rascunho_id: parseInt(String(rascunho.id), 10),
        ...(numeroOverride ? { numero_override: numeroOverride } : {}),
      });
      const nota = res.data as Rascunho;
      setNotaEmitida(nota);
      if (nota.status === 'autorizada') setEtapa('autorizada');
      else if (nota.status === 'processando') { setEtapa('processando'); iniciarPolling(nota.id); }
      else setEtapa('rejeitada');
    } catch (e: any) {
      // Erros 400 do backend (ValueError em montar_payload_nfce) chegam com detail
      const detail = e?.response?.data?.detail || e?.message || 'Erro desconhecido';
      setErroMsg(String(detail));
      setEtapa('invalidada');
    }
  }

  function confirmarEmissaoPreview() {
    if (!previewModelo) return;
    // Número é read-only no modal — sempre usa o calculado pelo backend (MAX+1 ou
    // proximo_nnf_inicial_*). Não envia numero_override pra não travar a lógica.
    emitir(previewModelo);
  }

  async function iniciarPolling(notaId: number) {
    setPollingActive(true);
    const tentar = async (i: number): Promise<void> => {
      if (i > 20) { setPollingActive(false); return; }
      await new Promise((r) => setTimeout(r, 3000));
      try {
        const r = await api.get(`/integracao/notas/${notaId}`);
        const nota = r.data as Rascunho;
        setNotaEmitida(nota);
        if (nota.status === 'autorizada') { setEtapa('autorizada'); setPollingActive(false); return; }
        if (nota.status === 'rejeitada' || nota.status === 'cancelada') { setEtapa('rejeitada'); setPollingActive(false); return; }
      } catch { /* ignora, tenta de novo */ }
      return tentar(i + 1);
    };
    tentar(0);
  }

  async function excluirRascunho() {
    if (!rascunho) return;
    if (!confirm(`Excluir a venda ${rascunho.id}? Ela volta a ficar editável no InnoSystem.`)) return;
    try {
      await api.delete(`/integracao/rascunhos/${rascunho.id}`);
      setToast('Venda devolvida ao InnoSystem.');
      setRascunho(null);
    } catch {
      setToast('Falha ao excluir — verifique se você tem permissão.');
    }
  }

  function abrirCadeado() {
    setSenhaInput(''); setErroSenha('');
    setModalSenhaAberto(true);
    setTimeout(() => senhaRef.current?.focus(), 50);
  }
  function validarSenha() {
    if (senhaInput === SENHA_TECNICA) {
      setModalSenhaAberto(false);
      setGavetaAberta(true);
      setAbaGaveta('ent');
    } else {
      setErroSenha('Senha incorreta. Tente novamente.');
      setSenhaInput('');
      senhaRef.current?.focus();
    }
  }

  // --- Render helpers ---
  const empresaAtual = empresas.find((e) => String(e.id) === empresaId);
  const fonteJson = notaEmitida || rascunho;
  const respostaObj = fonteJson?.resposta_integradora
    ? (() => { try { return JSON.parse(fonteJson.resposta_integradora!); } catch { return null; } })()
    : null;
  const rej = motivoRejeicao(respostaObj);

  return (
    <div className="min-h-screen bg-bg text-ink">
      {/* ===================== Cabeçalho ===================== */}
      <header className="sticky top-0 z-40 bg-ink text-white px-6 py-3 flex flex-wrap gap-4 items-center shadow-lg">
        <div className="font-extrabold text-sm tracking-tight">
          InnoFiscal <span className="text-[#7FA9F5]">/ emissão</span>
        </div>
        <div className="ml-auto flex items-center gap-3 text-xs">
          {empresaAtual && (
            <span className="opacity-80">
              {empresaAtual.nome_fantasia || empresaAtual.razao_social} · CNPJ {empresaAtual.cnpj}
            </span>
          )}
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider bg-ok/20 text-ok">
            <span className="w-1.5 h-1.5 rounded-full bg-ok" /> Produção
          </span>
        </div>
      </header>

      <main className="max-w-[1300px] mx-auto px-6 pt-6 pb-32">
        {/* Título */}
        <div className="mb-5">
          <div className="inline-block text-[10px] font-bold uppercase tracking-widest text-i9 bg-i9-tint px-2 py-1 rounded mb-2">
            Conferir e emitir
          </div>
          <h2 className="text-2xl font-extrabold tracking-tight">Emissão de Nota Fiscal</h2>
          <p className="text-sm text-ink-soft max-w-[76ch] mt-1">
            A venda chega pronta do InnoSystem e não pode ser alterada aqui. Confere, emite — ou
            exclui e refaz na origem.
          </p>
        </div>

        {/* Seletor de empresa (só relevante em multiempresa) */}
        {empresas.length > 1 && (
          <div className="mb-4 bg-card border border-line rounded-DEFAULT shadow p-3 flex items-center gap-3">
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted">Emissor</label>
            <select
              className="bg-field border border-line rounded-lg px-3 py-2 text-sm flex-1"
              value={empresaId}
              onChange={(e) => setEmpresaId(e.target.value)}
            >
              {empresas.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nome_fantasia || e.razao_social} · {e.cnpj}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Faixa-trava: aviso "não editável" */}
        {rascunho && !notaEmitida && (
          <div className="mb-5 flex gap-3 items-start bg-gradient-to-r from-[#FFF9EC] to-[#FDF4E2] border-l-4 border-gold rounded-r-DEFAULT px-4 py-3">
            <Lock size={18} className="text-gold flex-shrink-0 mt-0.5" />
            <div className="text-[13px] text-[#7A4E06]">
              <b className="font-extrabold block mb-0.5">Esta venda não pode ser editada aqui</b>
              Produtos, valores e formas de pagamento vieram do InnoSystem. Divergência? {' '}
              <button onClick={excluirRascunho} className="underline font-semibold hover:text-warn">
                exclua esta venda
              </button>{' '} — ela volta a ficar editável na origem.
            </div>
          </div>
        )}

        {/* --- Estado: sem rascunho carregado --- */}
        {!rascunho && !carregandoRascunho && !notaEmitida && (
          <div className="bg-card border border-line rounded-DEFAULT shadow p-8 text-center">
            <div className="mx-auto w-14 h-14 rounded-full bg-i9-tint grid place-items-center mb-3">
              <AlertTriangle className="text-i9" size={26} />
            </div>
            <h3 className="text-lg font-extrabold mb-1">Nenhuma venda carregada</h3>
            <p className="text-sm text-ink-soft max-w-md mx-auto">
              As vendas chegam do InnoSystem pela API de integração. Abra um rascunho pela lista
              de <a href="/documentos/rascunhos" className="text-i9 underline">notas recebidas</a>{' '}
              — ou, se você for da equipe técnica, use a <a href="/emitir/admin" className="text-i9 underline">tela dev</a>.
            </p>
          </div>
        )}

        {/* Loading rascunho */}
        {carregandoRascunho && (
          <div className="bg-card border border-line rounded-DEFAULT shadow p-6 flex items-center gap-3 text-sm text-ink-soft">
            <Loader2 className="animate-spin" size={18} /> Carregando venda…
          </div>
        )}

        {/* --- Painel principal: conferir + emitir --- */}
        {rascunho && venda && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 items-start">
            <div>
              <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
                {/* Topo */}
                <div className="flex justify-between items-start gap-4 mb-5">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1">
                      Venda #{rascunho.id} · recebida em {new Date(rascunho.criado_em).toLocaleString('pt-BR')}
                    </div>
                    <h3 className="text-xl font-extrabold tracking-tight">Conferir e emitir</h3>
                  </div>
                </div>

                {/* Destinatário */}
                <ClienteCard cliente={venda.cliente} />

                {/* Lista de itens */}
                <div className="border-t border-line">
                  {(venda.itens || []).map((it: any, i: number) => (
                    <div key={i} className="grid grid-cols-[auto_1fr_auto] gap-4 py-3 border-b border-line items-baseline">
                      <span className="text-xs text-muted font-mono">{i + 1}</span>
                      <div>
                        <div className="font-semibold text-sm leading-snug">
                          {(it.nome || it.descricao || 'Item sem nome').toString()}
                        </div>
                        <div className="text-xs text-muted mt-0.5">
                          {it.codigo && <>Código {it.codigo} · </>}
                          {it.quantidade} {it.unidade || 'UN'} × R$ {fmtMoeda(Number(it.valor_unitario || 0))}
                        </div>
                      </div>
                      <span className="font-mono text-sm">
                        {fmtMoeda(Number(it.quantidade || 0) * Number(it.valor_unitario || 0))}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Totais — unit já vem LÍQUIDO do InnoSystem, desconto é decorativo */}
                {(() => {
                  const somaItens = (venda.itens || []).reduce(
                    (s: number, it: any) => s + Number(it.quantidade || 0) * Number(it.valor_unitario || 0),
                    0
                  );
                  const descontoInfo = Number(venda.desconto || 0);
                  return (
                    <div className="py-4 space-y-1.5">
                      <LinhaTotal rotulo="Soma dos produtos" valor={somaItens} />
                      {descontoInfo > 0 && (
                        <div className="flex justify-between text-xs text-muted">
                          <span>Desconto (informativo — já aplicado nos preços)</span>
                          <span>R$ {fmtMoeda(descontoInfo)}</span>
                        </div>
                      )}
                      {(venda.pagamentos || []).map((p: any, i: number) => (
                        <LinhaTotal key={i} rotulo={`Pagamento · ${labelPagamento(p.meio_pagamento)}`} valor={Number(p.valor || 0)} />
                      ))}
                      <div className="flex justify-between items-baseline pt-3 border-t-2 border-ink mt-2">
                        <span className="font-extrabold text-base">Total da nota</span>
                        <b className="text-3xl font-extrabold tracking-tight">R$ {fmtMoeda(somaItens)}</b>
                      </div>
                    </div>
                  );
                })()}

                {/* Botões — NFC-e só aparece se empresa tem CSC cadastrado (evita
                    ConfigNfceNotFound/cStat 464 na SEFAZ). Sem CSC, só NF-e. */}
                <div className={`grid grid-cols-1 gap-3 mt-5 ${empresaAtual?.has_csc_token ? 'sm:grid-cols-[1.35fr_1fr]' : ''}`}>
                  {empresaAtual?.has_csc_token && (
                    <BotaoEmitir
                      disabled={etapa === 'transmitindo' || etapa === 'processando' || !!notaEmitida}
                      onClick={() => abrirPreview('65')}
                      primaria
                      titulo="Emitir NFC-e"
                      sub="Cupom para o consumidor · modelo 65"
                    />
                  )}
                  <BotaoEmitir
                    disabled={etapa === 'transmitindo' || etapa === 'processando' || !!notaEmitida}
                    onClick={() => abrirPreview('55')}
                    primaria={!empresaAtual?.has_csc_token}
                    titulo="Emitir NF-e"
                    sub="Nota modelo 55"
                  />
                </div>

                {/* Rodapé painel */}
                <div className="flex justify-between items-center gap-3 mt-5 pt-4 border-t border-line flex-wrap">
                  <button
                    onClick={excluirRascunho}
                    disabled={!!notaEmitida}
                    className="inline-flex items-center gap-2 text-sm font-semibold text-warn px-3 py-2 rounded-lg border border-warn/30 hover:bg-warn-tint disabled:opacity-40"
                  >
                    <Trash2 size={14} /> Excluir venda e refazer no InnoSystem
                  </button>
                </div>
              </div>

              {/* Resultado embaixo */}
              <div className="mt-5">
                {etapa === 'transmitindo' && <ResultadoTransmitindo />}
                {etapa === 'processando' && <ResultadoProcessando active={pollingActive} />}
                {etapa === 'autorizada' && notaEmitida && (
                  <ResultadoAutorizada nota={notaEmitida} />
                )}
                {etapa === 'rejeitada' && (
                  <ResultadoRejeitada motivo={rej.motivo} cstat={rej.cstat} onExcluir={excluirRascunho} />
                )}
                {etapa === 'invalidada' && (
                  <ResultadoInvalidada erro={erroMsg} onExcluir={excluirRascunho} />
                )}
              </div>
            </div>

            {/* Preview HTML real do documento — toggle 65/55 */}
            <aside className="hidden lg:block">
              <PreviewArea
                autorizada={etapa === 'autorizada'}
                nota={notaEmitida}
                empresa={empresaAtual}
                venda={venda}
                valorTotal={rascunho.valor_total}
              />
            </aside>
          </div>
        )}

        {erroMsg && etapa !== 'invalidada' && (
          <div className="mt-4 bg-warn-tint border border-warn/30 text-warn text-sm p-3 rounded-DEFAULT flex items-start gap-2">
            <AlertCircle size={14} className="mt-0.5" /><span>{erroMsg}</span>
          </div>
        )}
      </main>

      {/* ===================== Cadeado JSON (bottom-left) ===================== */}
      <button
        onClick={abrirCadeado}
        title="Área técnica"
        className="fixed left-4 bottom-4 z-50 inline-flex items-center gap-1.5 font-mono text-[11px] font-medium text-muted/70 px-2.5 py-1.5 rounded-lg hover:bg-card hover:text-ink-soft hover:shadow-md transition-colors"
      >
        <Lock size={11} /> JSON
      </button>

      {/* Modal preview: mostra numero/serie/valor antes de mandar SEFAZ.
          Operador pode editar o numero (ex: bater com a numeracao real da empresa
          se migrou de outro ERP). */}
      {previewOpen && (
        <div className="fixed inset-0 bg-ink/60 backdrop-blur-sm z-[100] grid place-items-center p-6"
             onClick={(e) => { if (e.target === e.currentTarget) setPreviewOpen(false); }}>
          <div className="bg-card rounded-DEFAULT p-7 shadow-2xl w-[min(520px,100%)]">
            <div className="w-12 h-12 rounded-xl bg-bg grid place-items-center mb-4">
              <Send size={22} />
            </div>
            <h4 className="text-xl font-extrabold tracking-tight mb-1">
              Confirmar emissão · {previewModelo === '55' ? 'NF-e (mod 55)' : 'NFC-e (mod 65)'}
            </h4>
            <p className="text-sm text-ink-soft mb-5">
              Revise o número. Após enviar à SEFAZ, ele não pode ser reutilizado.
            </p>

            {previewLoading ? (
              <div className="flex items-center gap-2 py-6 text-ink-soft">
                <Loader2 size={16} className="animate-spin" /> Calculando próximo número…
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-muted">
                      Número (nNF)
                    </label>
                    <input
                      type="text"
                      value={previewNumero}
                      disabled
                      className="bg-line-soft border border-line rounded-lg px-3 py-2.5 text-lg font-mono font-bold text-ink-soft"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-muted">
                      Série
                    </label>
                    <input
                      type="text"
                      value={previewSerie}
                      disabled
                      className="bg-line-soft border border-line rounded-lg px-3 py-2.5 text-lg font-mono font-bold text-ink-soft"
                    />
                  </div>
                </div>

                {previewFonte === 'migracao' && (
                  <div className="text-[11px] text-ink-soft mb-3 bg-i9-tint border border-i9/20 rounded-lg px-3 py-2">
                    Usando o número inicial cadastrado na empresa (migração de ERP).
                  </div>
                )}

                <div className="bg-bg rounded-lg p-3 mb-4 text-sm">
                  <div className="flex justify-between mb-1">
                    <span className="text-muted">Emissor</span>
                    <b className="text-ink">{empresaAtual?.nome_fantasia || empresaAtual?.razao_social || '—'}</b>
                  </div>
                  <div className="flex justify-between mb-1">
                    <span className="text-muted">Cliente</span>
                    <b className="text-ink">{(venda?.cliente?.nome || 'Consumidor').toString().slice(0, 40)}</b>
                  </div>
                  <div className="flex justify-between pt-1 border-t border-line mt-2">
                    <span className="text-muted font-bold">Valor total</span>
                    <b className="text-lg font-extrabold">R$ {fmtMoeda(Number(rascunho?.valor_total || 0))}</b>
                  </div>
                </div>

                {previewErro && (
                  <div className="text-warn text-xs mb-3 bg-warn-tint border border-warn/30 rounded-lg px-3 py-2">
                    {previewErro}
                  </div>
                )}

                <div className="flex gap-2">
                  <button onClick={() => setPreviewOpen(false)}
                          className="flex-1 py-3 rounded-lg bg-bg text-ink-soft font-extrabold text-sm">
                    Cancelar
                  </button>
                  <button onClick={confirmarEmissaoPreview}
                          disabled={!previewNumero}
                          className="flex-1 py-3 rounded-lg bg-ink text-white font-extrabold text-sm inline-flex items-center justify-center gap-2 disabled:opacity-40">
                    <Send size={14} /> Enviar SEFAZ
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Modal senha */}
      {modalSenhaAberto && (
        <div className="fixed inset-0 bg-ink/60 backdrop-blur-sm z-[100] grid place-items-center p-6"
             onClick={(e) => { if (e.target === e.currentTarget) setModalSenhaAberto(false); }}>
          <div className="bg-card rounded-DEFAULT p-7 shadow-2xl w-[min(460px,100%)]">
            <div className="w-12 h-12 rounded-xl bg-bg grid place-items-center mb-4">
              <Lock size={22} />
            </div>
            <h4 className="text-xl font-extrabold tracking-tight mb-2">Área técnica</h4>
            <p className="text-sm text-ink-soft mb-4">
              Aqui ficam os dados que o InnoSystem enviou e o payload transmitido à SEFAZ. Só
              leitura — nada aqui altera a nota.
            </p>
            <input
              ref={senhaRef}
              type="password"
              inputMode="numeric"
              maxLength={12}
              value={senhaInput}
              onChange={(e) => { setSenhaInput(e.target.value); setErroSenha(''); }}
              onKeyDown={(e) => e.key === 'Enter' && validarSenha()}
              placeholder="••••••"
              className="w-full font-mono text-lg text-center tracking-[0.3em] p-3.5 rounded-lg border-2 border-line bg-field focus:border-i9 focus:bg-white outline-none"
              aria-label="Senha técnica"
              autoComplete="off"
            />
            {erroSenha && <div className="text-warn text-xs mt-2 text-center">{erroSenha}</div>}
            <div className="flex gap-2 mt-5">
              <button onClick={() => setModalSenhaAberto(false)}
                      className="flex-1 py-3 rounded-lg bg-bg text-ink-soft font-extrabold text-sm">
                Cancelar
              </button>
              <button onClick={validarSenha}
                      className="flex-1 py-3 rounded-lg bg-ink text-white font-extrabold text-sm">
                Entrar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Gaveta técnica */}
      {gavetaAberta && (
        <GavetaTecnica
          jsonEntrada={rascunho?.json_venda || notaEmitida?.json_venda || ''}
          payloadSaida={notaEmitida?.payload_enviado || rascunho?.payload_enviado || ''}
          resposta={notaEmitida?.resposta_integradora || rascunho?.resposta_integradora || ''}
          rascunhoId={rascunho?.id || notaEmitida?.id}
          aba={abaGaveta}
          onAba={setAbaGaveta}
          onFechar={() => setGavetaAberta(false)}
          onCopiar={(txt: string) => {
            navigator.clipboard?.writeText(txt);
            setToast('Copiado para a área de transferência.');
          }}
        />
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed left-1/2 -translate-x-1/2 bottom-20 z-[130] bg-ink text-white px-5 py-3 rounded-DEFAULT text-sm shadow-2xl">
          {toast}
        </div>
      )}
    </div>
  );
}

// ==================== Subcomponentes ====================

function AlertCircle(props: any) {
  // reuso do lucide (evita import duplo)
  return <AlertTriangle {...props} />;
}

function ClienteCard({ cliente }: { cliente: any }) {
  if (!cliente) {
    return (
      <div className="bg-i9-tint rounded-lg p-4 mb-4 text-sm text-ink-soft italic">
        Consumidor não identificado (venda anônima).
      </div>
    );
  }
  const end = cliente.endereco || {};
  return (
    <div className="bg-i9-tint rounded-lg p-4 mb-4 flex justify-between items-start gap-4 flex-wrap">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-0.5">Destinatário</div>
        <strong className="text-base font-extrabold">{cliente.nome || '—'}</strong>
        {(end.logradouro || end.cidade) && (
          <div className="text-xs text-ink-soft mt-1">
            {[end.logradouro, end.numero].filter(Boolean).join(', ')}
            {end.bairro && ` · ${end.bairro}`}
            {end.cidade && ` · ${end.cidade}/${(end.uf || '').toUpperCase()}`}
            {end.cep && ` · CEP ${end.cep}`}
          </div>
        )}
        {cliente.email && (
          <div className="inline-flex items-center gap-1.5 text-xs text-i9-dark mt-1.5">
            <Mail size={12} /> {cliente.email}
          </div>
        )}
      </div>
      <div className="font-mono text-xs text-i9-dark whitespace-nowrap">
        {cliente.cpf && <>CPF {cliente.cpf}</>}
        {cliente.cnpj && <>CNPJ {cliente.cnpj}</>}
      </div>
    </div>
  );
}

function LinhaTotal({ rotulo, valor }: { rotulo: string; valor: number }) {
  return (
    <div className="flex justify-between text-sm text-ink-soft">
      <span>{rotulo}</span>
      <span className="font-mono">R$ {fmtMoeda(valor)}</span>
    </div>
  );
}

function BotaoEmitir({ disabled, onClick, primaria, titulo, sub }: any) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className={
        'flex flex-col items-center justify-center gap-0.5 font-extrabold rounded-lg py-4 px-4 transition-all disabled:opacity-40 disabled:cursor-not-allowed ' +
        (primaria
          ? 'bg-i9 text-white shadow-lg hover:bg-i9-dark active:translate-y-px'
          : 'bg-white text-i9 border-[1.5px] border-line hover:border-i9 hover:bg-i9-tint')
      }
    >
      <span className="text-base">{titulo}</span>
      <small className="font-medium text-[11px] opacity-70 tracking-normal">{sub}</small>
    </button>
  );
}

function ResultadoTransmitindo() {
  const passos = [
    'Conferindo os dados da venda',
    'Assinando com o certificado digital',
    'Enviando para a SEFAZ',
    'Aguardando o número de autorização',
  ];
  return (
    <div className="bg-card border border-line rounded-DEFAULT shadow p-5">
      <h4 className="text-lg font-extrabold tracking-tight mb-1">Transmitindo…</h4>
      <p className="text-sm text-ink-soft mb-4">Não feche esta tela. Leva poucos segundos.</p>
      <ul className="space-y-2">
        {passos.map((p, i) => (
          <li key={i} className="flex items-center gap-2.5 text-sm text-i9">
            <Loader2 size={14} className="animate-spin" /> {p}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ResultadoProcessando({ active }: { active: boolean }) {
  return (
    <div className="bg-pend-tint border border-pend/20 rounded-DEFAULT p-5">
      <h4 className="text-lg font-extrabold tracking-tight text-pend mb-1">Aguardando SEFAZ processar</h4>
      <p className="text-sm text-ink-soft">
        A nota foi enviada e está em fila na SEFAZ. Consulta automática a cada 3 segundos {active && '(polling ativo)'}.
      </p>
    </div>
  );
}

function ResultadoAutorizada({ nota }: { nota: Rascunho }) {
  const chave = nota.chave_acesso || '';
  return (
    <div className="bg-ok-tint border border-ok/30 rounded-DEFAULT p-5">
      <h4 className="text-lg font-extrabold tracking-tight text-ok mb-1 inline-flex items-center gap-2">
        <CheckCircle2 size={20} /> {nota.modelo === '55' ? 'NF-e' : 'NFC-e'} autorizada
      </h4>
      <p className="text-sm text-ink-soft mb-3">
        Nota {nota.numero} · série {nota.serie} · autorizada pela SEFAZ.
      </p>
      {chave && (
        <div className="bg-white/70 rounded-lg p-3">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted mb-1">Chave de acesso</div>
          <div className="font-mono text-xs tracking-wider break-all">{agrupar(chave)}</div>
        </div>
      )}
      <div className="flex gap-2 flex-wrap mt-4">
        <a href={`/documentos`} className="inline-flex items-center gap-1.5 bg-white text-ink px-3 py-2 rounded-lg text-sm font-semibold shadow-sm hover:shadow-md">
          Ir para Central de Documentos
        </a>
        {chave && (
          <button
            onClick={() => navigator.clipboard?.writeText(chave)}
            className="inline-flex items-center gap-1.5 bg-white text-ink px-3 py-2 rounded-lg text-sm font-semibold shadow-sm hover:shadow-md"
          >
            <Copy size={14} /> Copiar chave
          </button>
        )}
      </div>
    </div>
  );
}

function ResultadoRejeitada({ motivo, cstat, onExcluir }: { motivo: string; cstat: string; onExcluir: () => void }) {
  return (
    <div className="bg-warn-tint border border-warn/30 rounded-DEFAULT p-5">
      <h4 className="text-lg font-extrabold tracking-tight text-warn mb-1 inline-flex items-center gap-2">
        <XCircle size={20} /> A SEFAZ não autorizou esta nota
      </h4>
      <p className="text-sm text-ink-soft mb-3">Nenhum documento foi gerado e nenhum número foi consumido.</p>
      <div className="bg-white/70 rounded-lg p-3">
        {cstat && <div className="font-mono text-[11px] text-warn font-semibold uppercase tracking-wider mb-1">Rejeição {cstat}</div>}
        <div className="text-sm">{motivo || 'Motivo não informado pela SEFAZ.'}</div>
      </div>
      <div className="flex gap-2 flex-wrap mt-4">
        <button onClick={onExcluir}
          className="inline-flex items-center gap-1.5 bg-warn text-white px-3 py-2 rounded-lg text-sm font-semibold">
          Excluir e refazer no InnoSystem
        </button>
      </div>
    </div>
  );
}

function ResultadoInvalidada({ erro, onExcluir }: { erro: string; onExcluir: () => void }) {
  return (
    <div className="bg-warn-tint border border-warn/30 rounded-DEFAULT p-5">
      <h4 className="text-lg font-extrabold tracking-tight text-warn mb-1 inline-flex items-center gap-2">
        <ShieldAlert size={20} /> Esta venda não pôde ser transmitida
      </h4>
      <p className="text-sm text-ink-soft mb-3">Problema detectado antes do envio. A SEFAZ nem foi acionada.</p>
      <div className="bg-white/70 rounded-lg p-3">
        <div className="font-mono text-[11px] text-warn font-semibold uppercase tracking-wider mb-1">Validação interna</div>
        <div className="text-sm whitespace-pre-wrap">{erro}</div>
      </div>
      <div className="flex gap-2 flex-wrap mt-4">
        <button onClick={onExcluir}
          className="inline-flex items-center gap-1.5 bg-warn text-white px-3 py-2 rounded-lg text-sm font-semibold">
          Excluir e refazer no InnoSystem
        </button>
      </div>
    </div>
  );
}

/**
 * Área de preview lateral com toggle Cupom (NFC-e mod 65) / DANFE (NF-e mod 55).
 * Renderiza HTML espelhando o layout real do documento. Antes da autorização
 * é uma PRÉVIA do que vai sair; após autorização mostra chave/protocolo reais.
 */
function PreviewArea({ autorizada, nota, empresa, venda, valorTotal }: any) {
  // Após emissão, força o modelo emitido; antes disso deixa o usuário escolher
  const emitedModelo = (autorizada && nota?.modelo) ? String(nota.modelo) : null;
  const [modelo, setModelo] = useState<'65' | '55'>(
    (emitedModelo === '55' ? '55' : '65')
  );
  useEffect(() => {
    if (emitedModelo === '55' || emitedModelo === '65') setModelo(emitedModelo as any);
  }, [emitedModelo]);

  return (
    <div className="space-y-3">
      {/* Toggle */}
      <div className="bg-card border border-line rounded-DEFAULT shadow p-1 flex gap-1">
        <button
          onClick={() => setModelo('65')}
          disabled={emitedModelo === '55'}
          className={`flex-1 py-2 px-3 rounded text-xs font-bold uppercase tracking-wider transition ${
            modelo === '65' ? 'bg-ink text-white' : 'text-muted hover:bg-bg disabled:opacity-40'
          }`}
        >
          Cupom (NFC-e)
        </button>
        <button
          onClick={() => setModelo('55')}
          disabled={emitedModelo === '65'}
          className={`flex-1 py-2 px-3 rounded text-xs font-bold uppercase tracking-wider transition ${
            modelo === '55' ? 'bg-ink text-white' : 'text-muted hover:bg-bg disabled:opacity-40'
          }`}
        >
          DANFE (NF-e)
        </button>
      </div>

      {/* Selo do estado */}
      <div className="text-[10px] font-bold uppercase tracking-wider text-center">
        {autorizada
          ? <span className="text-ok">✓ Autorizada — como saiu na SEFAZ</span>
          : <span className="text-muted">Prévia — como vai sair ao emitir</span>}
      </div>

      {/* Documento */}
      {modelo === '65'
        ? <CupomNFCePreview autorizada={autorizada} nota={nota} empresa={empresa} venda={venda} valorTotal={valorTotal} />
        : <DanfePreview autorizada={autorizada} nota={nota} empresa={empresa} venda={venda} valorTotal={valorTotal} />
      }

      {/* Ações pós-autorização */}
      {autorizada && (
        <div className="flex justify-center gap-1 flex-wrap">
          <button className="inline-flex items-center gap-1 text-[11px] font-semibold text-ink-soft hover:text-ink px-2.5 py-1.5 rounded hover:bg-card">
            <Printer size={12} /> Imprimir
          </button>
          <button className="inline-flex items-center gap-1 text-[11px] font-semibold text-ink-soft hover:text-ink px-2.5 py-1.5 rounded hover:bg-card">
            <Download size={12} /> PDF
          </button>
          <button className="inline-flex items-center gap-1 text-[11px] font-semibold text-ink-soft hover:text-ink px-2.5 py-1.5 rounded hover:bg-card">
            <Mail size={12} /> E-mail
          </button>
        </div>
      )}
    </div>
  );
}

// -------------- Cupom NFC-e (estilo térmico) --------------
function CupomNFCePreview({ autorizada, nota, empresa, venda }: any) {
  const nomeEmp = (empresa?.nome_fantasia || empresa?.razao_social || 'EMPRESA').toString().toUpperCase();
  const cnpj = empresa?.cnpj || '—';
  const endereco = [empresa?.logradouro, empresa?.numero].filter(Boolean).join(', ');
  const cidade = [empresa?.cidade, empresa?.uf].filter(Boolean).join('/');
  const itens = (venda?.itens || []) as any[];
  const pagamentos = (venda?.pagamentos || []) as any[];
  // Unit vem LÍQUIDO — subtotal = total = Σ(qty × unit). Desconto é decorativo,
  // não sai no cupom fiscal (sairia como -vDesc, mas emissão manda vDesc=0).
  const subtotal = itens.reduce((s, it) => s + Number(it.quantidade || 0) * Number(it.valor_unitario || 0), 0);
  const valorTotal = subtotal;
  const cliente = venda?.cliente;

  return (
    <div className="bg-[#FBFAF7] px-5 py-6 font-mono text-[11px] leading-relaxed text-[#2A2A28] shadow-2xl relative">
      {/* Serrilha superior */}
      <div className="absolute -top-1.5 left-0 right-0 h-1.5"
           style={{ background: 'radial-gradient(circle at 6px -1px, transparent 5px, #FBFAF7 5.5px) 0 0/12px 7px repeat-x' }} />

      {/* Cabeçalho */}
      <div className="text-center pb-2 border-b border-dashed border-[#C9C5BA]">
        <b className="block text-[13px] tracking-wide">{nomeEmp}</b>
        <span className="block text-[10px] text-[#6D6A62]">CNPJ {cnpj}</span>
        {endereco && <span className="block text-[10px] text-[#6D6A62]">{endereco}</span>}
        {cidade && <span className="block text-[10px] text-[#6D6A62]">{cidade}</span>}
      </div>

      {/* Título do documento */}
      <div className="text-center py-2 text-[10px] text-[#6D6A62]">
        DOCUMENTO AUXILIAR DA<br/>NOTA FISCAL DE CONSUMIDOR ELETRÔNICA
      </div>
      <div className="border-b border-dashed border-[#C9C5BA]" />

      {/* Itens */}
      <div className="py-2">
        <div className="flex justify-between text-[10px] text-[#6D6A62] mb-1.5">
          <span>ITEM · CÓD · DESCRIÇÃO</span><span>VALOR</span>
        </div>
        {itens.length === 0
          ? <div className="text-[10px] text-[#6D6A62] italic">(sem itens)</div>
          : itens.map((it, i) => {
            const nome = (it.nome || it.descricao || 'ITEM').toString().toUpperCase().slice(0, 34);
            const qtd = Number(it.quantidade || 0);
            const vu = Number(it.valor_unitario || 0);
            return (
              <div key={i} className="mb-1.5">
                <div>{String(i + 1).padStart(3, '0')} {it.codigo || '—'} {nome}</div>
                <div className="flex justify-between">
                  <span className="pl-4">{qtd} {(it.unidade || 'UN').toUpperCase()} x {fmtMoeda(vu)}</span>
                  <span>{fmtMoeda(qtd * vu)}</span>
                </div>
              </div>
            );
          })}
      </div>
      <div className="border-b border-dashed border-[#C9C5BA]" />

      {/* Totais */}
      <div className="py-2 text-[11px]">
        <div className="flex justify-between"><span>Qtd. total de itens</span><span>{itens.length}</span></div>
        <div className="flex justify-between"><span>Subtotal</span><span>R$ {fmtMoeda(subtotal)}</span></div>
        <div className="flex justify-between font-bold text-[14px] pt-1 mt-1 border-t border-dashed border-[#C9C5BA]">
          <span>TOTAL R$</span><span>{fmtMoeda(valorTotal)}</span>
        </div>
        <div className="mt-1">
          {pagamentos.map((p, i) => (
            <div key={i} className="flex justify-between text-[10px]">
              <span>{labelPagamento(p.meio_pagamento)}</span>
              <span>{fmtMoeda(Number(p.valor || 0))}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="border-b border-dashed border-[#C9C5BA]" />

      {/* Cliente */}
      {cliente && (
        <div className="py-2 text-[10px] text-center">
          CONSUMIDOR: {(cliente.nome || 'NÃO IDENTIFICADO').toUpperCase()}
          {cliente.cpf && <><br/>CPF {cliente.cpf}</>}
          {cliente.cnpj && <><br/>CNPJ {cliente.cnpj}</>}
        </div>
      )}

      {/* Rodapé — chave e QR */}
      <div className="pt-2 text-[10px] text-center text-[#6D6A62] border-t border-dashed border-[#C9C5BA]">
        {autorizada && nota?.chave_acesso ? (
          <>
            <div>Consulte pela chave de acesso em<br/>www.fazenda.<span>[uf]</span>.gov.br/nfce</div>
            <div className="my-2 inline-block bg-white border border-[#DCD8CE] p-1.5">
              <MiniQR />
            </div>
            <div className="tracking-wider break-all text-[9px]">{agrupar(nota.chave_acesso)}</div>
            {nota.numero && <div className="mt-1">Nº {nota.numero} · SÉRIE {nota.serie || 1}</div>}
          </>
        ) : (
          <div className="italic">Chave de acesso, QR e número virão após a autorização</div>
        )}
      </div>

      {/* Selo autorizado */}
      {autorizada && (
        <div className="absolute top-[38%] left-1/2 -translate-x-1/2 -rotate-12 border-4 border-ok text-ok font-extrabold text-lg px-3 py-1 rounded opacity-90 bg-[#FBFAF7]/60 pointer-events-none tracking-wider">
          AUTORIZADA
        </div>
      )}

      {/* Serrilha inferior */}
      <div className="absolute -bottom-1.5 left-0 right-0 h-1.5"
           style={{ background: 'radial-gradient(circle at 6px 8px, transparent 5px, #FBFAF7 5.5px) 0 0/12px 7px repeat-x' }} />
    </div>
  );
}

// -------------- DANFE NF-e mod 55 (simplificado) --------------
function DanfePreview({ autorizada, nota, empresa, venda }: any) {
  const cliente = venda?.cliente;
  const end = cliente?.endereco || {};
  const itens = (venda?.itens || []) as any[];
  // Unit LÍQUIDO — subtotal = total = Σ itens; desconto decorativo não vai no DANFE
  const subtotal = itens.reduce((s, it) => s + Number(it.quantidade || 0) * Number(it.valor_unitario || 0), 0);
  const valorTotal = subtotal;
  const chave = nota?.chave_acesso || '';

  return (
    <div className="bg-white p-2.5 font-mono text-[8.5px] leading-tight text-[#1a1a1a] shadow-2xl relative">
      {/* Canhoto */}
      <div className="border border-[#444] px-2 py-1.5 text-[6.5px] leading-relaxed mb-0.5">
        RECEBEMOS DE <b>{(empresa?.razao_social || 'EMPRESA').toUpperCase()}</b> OS PRODUTOS CONSTANTES DA NOTA FISCAL INDICADA AO LADO
        <div className="flex gap-1 mt-1">
          <div className="border-t border-[#888] flex-1 pt-0.5 text-[5.5px] text-[#666]">DATA</div>
          <div className="border-t border-[#888] flex-[2] pt-0.5 text-[5.5px] text-[#666]">IDENTIFICAÇÃO E ASSINATURA</div>
        </div>
      </div>
      <div className="border-t border-dashed border-[#999] my-1" />

      {/* Cabeçalho principal */}
      <div className="grid grid-cols-[1.5fr_1.1fr_1.9fr] gap-0.5 mb-0.5">
        <div className="border border-[#444] px-1.5 py-1 text-center">
          <b className="block text-[10px]">{(empresa?.nome_fantasia || empresa?.razao_social || 'EMPRESA').toUpperCase()}</b>
          <span className="block text-[6px] text-[#555]">{empresa?.logradouro || '—'}</span>
          <span className="block text-[6px] text-[#555]">
            {[empresa?.cidade, empresa?.uf].filter(Boolean).join('/')}
            {empresa?.cep && ` — ${empresa.cep}`}
          </span>
        </div>
        <div className="border border-[#444] p-1 text-center">
          <b className="block text-[13px] tracking-wider">DANFE</b>
          <span className="block text-[5.5px] text-[#555] leading-tight">Documento Auxiliar da<br/>Nota Fiscal Eletrônica</span>
          <div className="flex justify-center gap-1 text-[6px] my-1 items-center">
            <span>0-ENTRADA</span><span>1-SAÍDA</span>
            <b className="border border-[#444] px-0.5">1</b>
          </div>
          <div className="text-[7px]">
            Nº {nota?.numero ? String(nota.numero).padStart(9, '0') : '—'}<br/>
            SÉRIE {nota?.serie || 1} · FOLHA 1/1
          </div>
        </div>
        <div className="border border-[#444] p-1 flex flex-col justify-between">
          <div className="flex gap-px h-6 mb-1 items-stretch">
            {/* Barras fake determinísticas */}
            {Array.from({ length: 60 }).map((_, i) => (
              <i key={i} className="block bg-black"
                 style={{ width: (i * 7 + 3) % 3 === 0 ? '2px' : '1px', opacity: (i * 11) % 5 === 0 ? 0.3 : 1 }} />
            ))}
          </div>
          <div className="text-[7px] text-center break-all">{chave ? agrupar(chave) : '—'}</div>
          <div className="text-[5.5px] text-[#555] text-center mt-1 leading-tight">
            Consulta em www.nfe.fazenda.gov.br/portal
          </div>
        </div>
      </div>

      {/* Protocolo */}
      <div className="border border-[#444] px-1.5 py-0.5 text-center text-[6.5px] bg-[#F4FAF6] mb-0.5">
        {autorizada
          ? 'PROTOCOLO DE AUTORIZAÇÃO DE USO — autorizada pela SEFAZ'
          : 'PROTOCOLO DE AUTORIZAÇÃO DE USO — aguardando transmissão'}
      </div>

      {/* Destinatário */}
      <div className="bg-[#e8e8e8] border border-[#444] border-b-0 text-[6px] font-bold px-1.5 py-0.5 uppercase tracking-wider mt-1">
        Destinatário / Remetente
      </div>
      <div className="grid grid-cols-[2fr_1fr_1fr] gap-0.5">
        <BoxDanfe rot="Nome / Razão Social" val={(cliente?.nome || '—').toUpperCase()} />
        <BoxDanfe rot={cliente?.cnpj ? 'CNPJ' : 'CPF'} val={cliente?.cnpj || cliente?.cpf || '—'} />
        <BoxDanfe rot="Data de emissão" val={new Date().toLocaleDateString('pt-BR')} />
      </div>
      <div className="grid grid-cols-[2.2fr_1fr_1fr_.9fr] gap-0.5 mt-0.5">
        <BoxDanfe rot="Endereço" val={[end.logradouro, end.numero].filter(Boolean).join(', ') || '—'} />
        <BoxDanfe rot="Município" val={(end.cidade || '—').toUpperCase()} />
        <BoxDanfe rot="CEP" val={end.cep || '—'} />
        <BoxDanfe rot="UF" val={(end.uf || '—').toUpperCase()} />
      </div>

      {/* Cálculo do imposto (simplificado) */}
      <div className="bg-[#e8e8e8] border border-[#444] border-b-0 text-[6px] font-bold px-1.5 py-0.5 uppercase tracking-wider mt-1">
        Cálculo do Imposto
      </div>
      <div className="grid grid-cols-4 gap-0.5">
        <BoxDanfe rot="Base de cálculo ICMS" val="0,00" />
        <BoxDanfe rot="Valor do ICMS" val="0,00" />
        <BoxDanfe rot="Valor dos produtos" val={fmtMoeda(subtotal)} />
        <BoxDanfe rot="Desconto" val="0,00" />
      </div>
      <div className="grid grid-cols-4 gap-0.5 mt-0.5">
        <BoxDanfe rot="Valor do frete" val="0,00" />
        <BoxDanfe rot="Outras despesas" val="0,00" />
        <BoxDanfe rot="Valor do IPI" val="0,00" />
        <BoxDanfe rot="Total da nota" val={fmtMoeda(valorTotal)} destaque />
      </div>

      {/* Produtos */}
      <div className="bg-[#e8e8e8] border border-[#444] border-b-0 text-[6px] font-bold px-1.5 py-0.5 uppercase tracking-wider mt-1">
        Dados dos Produtos / Serviços
      </div>
      <table className="w-full border-collapse text-[6.5px]">
        <thead>
          <tr>
            {['Código', 'Descrição', 'NCM', 'CFOP', 'Un', 'Qtd', 'V.Unit', 'V.Total'].map((h) => (
              <th key={h} className="bg-[#eee] border border-[#444] px-1 py-0.5 font-bold text-[5.5px] uppercase">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {itens.length === 0 ? (
            <tr><td colSpan={8} className="border border-[#444] px-1 py-0.5 italic text-center text-[#666]">(sem itens)</td></tr>
          ) : itens.map((it, i) => {
            const qtd = Number(it.quantidade || 0);
            const vu = Number(it.valor_unitario || 0);
            return (
              <tr key={i}>
                <td className="border border-[#444] px-1 py-0.5">{it.codigo || '—'}</td>
                <td className="border border-[#444] px-1 py-0.5">{(it.nome || it.descricao || 'ITEM').toString().toUpperCase()}</td>
                <td className="border border-[#444] px-1 py-0.5">{(it.ncm || '').toString().slice(0, 8) || '—'}</td>
                <td className="border border-[#444] px-1 py-0.5">{it.cfop || '—'}</td>
                <td className="border border-[#444] px-1 py-0.5">{(it.unidade || 'UN').toUpperCase()}</td>
                <td className="border border-[#444] px-1 py-0.5 text-right">{qtd}</td>
                <td className="border border-[#444] px-1 py-0.5 text-right">{fmtMoeda(vu)}</td>
                <td className="border border-[#444] px-1 py-0.5 text-right">{fmtMoeda(qtd * vu)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Selo autorizado */}
      {autorizada && (
        <div className="absolute top-[42%] left-1/2 -translate-x-1/2 -rotate-12 border-4 border-ok text-ok font-extrabold text-xl px-4 py-1 rounded opacity-90 bg-white/70 pointer-events-none tracking-wider">
          AUTORIZADA
        </div>
      )}
    </div>
  );
}

function BoxDanfe({ rot, val, destaque }: { rot: string; val: string; destaque?: boolean }) {
  return (
    <div className={`border border-[#444] px-1 py-0.5 ${destaque ? 'bg-[#F2F5FA]' : ''}`}>
      <span className="block text-[5.5px] text-[#555] uppercase tracking-wider leading-none">{rot}</span>
      <span className={`block text-[8px] whitespace-nowrap overflow-hidden text-ellipsis ${destaque ? 'font-bold' : ''}`}>{val}</span>
    </div>
  );
}

// QR fake determinístico — só visual, não escaneável
function MiniQR() {
  const s = 21;
  let seed = 7;
  const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  const cels: ReactElement[] = [];
  for (let y = 0; y < s; y++) for (let x = 0; x < s; x++) {
    const canto = (x < 7 && y < 7) || (x > s - 8 && y < 7) || (x < 7 && y > s - 8);
    const on = canto
      ? (x % 6 === 0 || y % 6 === 0 || (x > 1 && x < 5 && y > 1 && y < 5) || (x > s - 7 && x < s - 2 && y > 1 && y < 5) || (x > 1 && x < 5 && y > s - 7 && y < s - 2))
      : rnd() > 0.52;
    if (on) cels.push(<rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} />);
  }
  return <svg viewBox={`0 0 ${s} ${s}`} width={68} height={68} fill="#111">{cels}</svg>;
}

function labelPagamento(cod: string): string {
  const map: Record<string, string> = {
    '01': 'Dinheiro', '02': 'Cheque', '03': 'Crédito', '04': 'Débito', '05': 'Crédito Loja',
    '10': 'Vale Alimentação', '11': 'Vale Refeição', '12': 'Vale Presente', '13': 'Vale Combustível',
    '15': 'Boleto', '17': 'PIX', '18': 'Transferência bancária', '19': 'Cashback', '90': 'Sem pagamento', '99': 'Outros',
  };
  return map[String(cod)] || `Meio ${cod}`;
}

// ==================== Gaveta técnica ====================
function GavetaTecnica({
  jsonEntrada, payloadSaida, resposta, rascunhoId, aba, onAba, onFechar, onCopiar,
}: {
  jsonEntrada: string;
  payloadSaida: string;
  resposta: string;
  rascunhoId?: number;
  aba: 'ent' | 'sai' | 'val' | 'log';
  onAba: (a: 'ent' | 'sai' | 'val' | 'log') => void;
  onFechar: () => void;
  onCopiar: (txt: string) => void;
}) {
  const pretty = (raw: string) => {
    try { return JSON.stringify(JSON.parse(raw), null, 2); } catch { return raw || '(vazio)'; }
  };
  const respostaJson = pretty(resposta);
  const respostaObj = resposta ? (() => { try { return JSON.parse(resposta); } catch { return {}; } })() : {};

  const validacoes = [
    ['INN-101', 'Forma de pagamento na tabela tPag', check(!!jsonEntrada && !!getIn(jsonEntrada, ['pagamentos', 0, 'meio_pagamento']))],
    ['INN-102', 'NCM presente em todos os itens', check(false, 'depende da regra fiscal — validado no montar_payload_nfce')],
    ['INN-103', 'CPF/CNPJ do destinatário válido', check(!!getIn(jsonEntrada, ['cliente', 'cpf']) || !!getIn(jsonEntrada, ['cliente', 'cnpj']))],
    ['INN-109', 'Endereço completo (só NF-e)', check(!!getIn(jsonEntrada, ['cliente', 'endereco', 'logradouro']))],
    ['INN-110', 'Rascunho existente', check(!!rascunhoId)],
  ];

  return (
    <div className="fixed top-0 right-0 bottom-0 w-[min(620px,100%)] bg-[#0A1729] text-[#DCE6F5] z-[110] flex flex-col shadow-2xl animate-slide-in">
      <header className="px-6 py-5 border-b border-white/10 flex items-center gap-3">
        <div>
          <h4 className="font-extrabold text-base tracking-tight m-0">
            Área técnica {rascunhoId ? `· venda #${rascunhoId}` : ''}
          </h4>
          <div className="text-xs text-[#7D93B4] mt-0.5">
            Acesso registrado · {new Date().toLocaleString('pt-BR')}
          </div>
        </div>
        <button onClick={onFechar} className="ml-auto text-[#7D93B4] hover:text-white text-2xl px-2 rounded">×</button>
      </header>

      <div className="flex gap-1 px-6 pt-3 flex-wrap">
        {[
          ['ent', 'Como chegou'],
          ['sai', 'Como foi enviado'],
          ['val', 'Validações'],
          ['log', 'Linha do tempo'],
        ].map(([id, label]) => (
          <button
            key={id}
            onClick={() => onAba(id as any)}
            className={`text-xs font-semibold px-3 py-2 rounded-lg ${
              aba === id ? 'bg-white/10 text-white' : 'text-[#7D93B4] hover:text-white'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto px-6 py-4">
        {aba === 'ent' && (
          <>
            <div className="bg-gold/20 text-[#E8B45E] rounded-lg p-3 text-xs mb-3 leading-relaxed">
              Payload bruto recebido do InnoSystem. Só leitura — pra corrigir, exclua a venda e refaça na origem.
            </div>
            <pre className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words bg-black/30 rounded-DEFAULT p-4 text-[#C8D6EC] max-h-full">
              {pretty(jsonEntrada)}
            </pre>
          </>
        )}
        {aba === 'sai' && (
          <>
            <div className="bg-i9/25 text-[#9DBEFB] rounded-lg p-3 text-xs mb-3 leading-relaxed">
              Payload já mapeado para o layout da SEFAZ. Só existe depois de tentar emitir.
            </div>
            <pre className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words bg-black/30 rounded-DEFAULT p-4 text-[#C8D6EC] max-h-full">
              {payloadSaida ? pretty(payloadSaida) : '(ainda não transmitido)'}
            </pre>
          </>
        )}
        {aba === 'val' && (
          <>
            <div className="bg-gold/20 text-[#E8B45E] rounded-lg p-3 text-xs mb-3 leading-relaxed">
              Checagens rápidas do payload. Regras completas (INN-101..110) rodam no backend.
            </div>
            <div className="space-y-0">
              {validacoes.map(([cod, desc, res]: any, i) => (
                <div key={i} className={`flex gap-3 items-start py-2.5 border-b border-white/5 text-xs ${res.ok ? '' : 'text-[#F0B0A4]'}`}>
                  <span className={`w-5 h-5 rounded-full grid place-items-center flex-shrink-0 mt-0.5 ${res.ok ? 'bg-ok/20 text-ok' : 'bg-warn/25 text-[#F08D7E]'}`}>
                    {res.ok ? <CheckCircle2 size={12}/> : <XCircle size={12}/>}
                  </span>
                  <span className="font-mono text-[#7D93B4] w-16 flex-shrink-0">{cod}</span>
                  <span className="flex-1">
                    {desc}
                    <span className="block text-[#7D93B4] text-[11px] mt-0.5">{res.detalhe}</span>
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
        {aba === 'log' && (
          <>
            <div className="bg-white/5 text-[#9DB3D1] rounded-lg p-3 text-xs mb-3 leading-relaxed">
              Resposta da ACBr/SEFAZ (bruta). Vazia se ainda não transmitiu.
            </div>
            <pre className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words bg-black/30 rounded-DEFAULT p-4 text-[#C8D6EC] max-h-full">
              {resposta ? respostaJson : '(sem resposta ainda)'}
            </pre>
            {respostaObj?.autorizacao?.motivo_status && (
              <div className="mt-3 text-xs text-[#B7C9E4]">
                <b>cStat {respostaObj.autorizacao.codigo_status}:</b> {respostaObj.autorizacao.motivo_status}
              </div>
            )}
          </>
        )}
      </div>

      <div className="px-6 py-4 border-t border-white/10 flex gap-2 flex-wrap">
        <button
          onClick={() => onCopiar(aba === 'ent' ? pretty(jsonEntrada) : aba === 'sai' ? pretty(payloadSaida) : respostaJson)}
          className="text-xs font-semibold px-3 py-2 rounded-lg bg-white/10 text-[#C8D6EC] hover:bg-white/20"
        >
          Copiar JSON desta aba
        </button>
      </div>
    </div>
  );
}

function getIn(rawJson: string, path: (string | number)[]) {
  try {
    let cur: any = JSON.parse(rawJson);
    for (const k of path) {
      if (cur == null) return null;
      cur = cur[k as any];
    }
    return cur;
  } catch {
    return null;
  }
}
function check(ok: boolean, detalhe?: string) { return { ok, detalhe: detalhe || (ok ? 'OK' : 'Verificar') }; }
