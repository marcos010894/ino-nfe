import { useEffect, useMemo, useState } from 'react';
import {
  FileText, Download, XOctagon, RefreshCw, AlertCircle, ShieldCheck, HelpCircle, Eye,
  Loader2, Ban, Clock, ShieldX, Search, ChevronLeft, ChevronRight, ChevronDown, Copy, X,
  Settings, Send, Package, Receipt, CalendarDays,
} from 'lucide-react';
import api from '../../lib/api';

// ---------------------------------------------------------------------------
// Central v3 — tabs no topo + banner alertas + contador
// ---------------------------------------------------------------------------
type Aba = 'nfce' | 'nfe' | 'inutilizadas';

interface AlertaItem {
  tipo: 'rejeitada' | 'aguardando' | 'inutilizar' | 'cert_vencendo';
  severidade: 'info' | 'warn' | 'erro';
  count: number | null;
  label: string;
}

interface AlertasResponse {
  empresa_id: number;
  total: number;
  itens: AlertaItem[];
}

interface ContadorConfig {
  nome_contador: string | null;
  email_contador: string | null;
  email_cc_contador: string | null;
  dia_envio_contador: number | null;
  envio_automatico_contador: boolean;
  assunto_email_contador: string | null;
  mensagem_email_contador: string | null;
  smtp_configurado: boolean;
}

interface PreviewExport {
  empresa: { id: number; cnpj: string; nome: string };
  periodo: { inicio: string; fim: string; label: string };
  qtd_nfce_autorizadas: number;
  qtd_nfe_autorizadas: number;
  qtd_canceladas: number;
  qtd_total: number;
  valor_total_autorizadas: number;
}

interface Nota {
  id: number;
  empresa_id: number;
  modelo: string;
  status: string;
  chave_acesso: string | null;
  numero: number | null;
  serie: number | null;
  numero_venda: string | null;  // Nº da venda de origem (InnoSystem → numero_pedido_externo)
  valor_total: number;
  json_venda: string;
  resposta_integradora: string | null;
  xml_url: string | null;
  pdf_url: string | null;
  criado_em: string;
  atualizado_em: string;  // Data do último evento (autorização, cancelamento…)
}

interface Empresa {
  id: number;
  razao_social: string;
  nome_fantasia: string;
  cnpj: string;
}

// ---------------------------------------------------------------------------
// Seletor de período — presets + helper
// ---------------------------------------------------------------------------
type Preset = 'este_mes' | 'mes_passado' | 'ultimos_7' | 'ontem' | 'hoje' | 'custom';

interface Intervalo {
  inicio: Date;
  fim: Date;
  labelCurto: string;   // "Setembro 2026", "Ontem"
  labelLongo: string;   // "01/09/2026 a 30/09/2026"
}

const NOME_MES_PT = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

const inicioDoDia = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
const fimDoDia = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);
const primeiroDiaMes = (d: Date) => new Date(d.getFullYear(), d.getMonth(), 1, 0, 0, 0, 0);
const ultimoDiaMes = (d: Date) => new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59, 999);
const fmtBR = (d: Date) => d.toLocaleDateString('pt-BR');

function resolverIntervalo(preset: Preset, ref: Date, customIni: string, customFim: string): Intervalo {
  const hoje = new Date();
  if (preset === 'hoje') {
    const ini = inicioDoDia(hoje);
    const fim = fimDoDia(hoje);
    return { inicio: ini, fim, labelCurto: 'Hoje', labelLongo: `${fmtBR(ini)} a ${fmtBR(fim)}` };
  }
  if (preset === 'ontem') {
    const ontem = new Date(hoje);
    ontem.setDate(hoje.getDate() - 1);
    const ini = inicioDoDia(ontem);
    const fim = fimDoDia(ontem);
    return { inicio: ini, fim, labelCurto: 'Ontem', labelLongo: `${fmtBR(ini)} a ${fmtBR(fim)}` };
  }
  if (preset === 'ultimos_7') {
    const inicio7 = new Date(hoje);
    inicio7.setDate(hoje.getDate() - 6);
    const ini = inicioDoDia(inicio7);
    const fim = fimDoDia(hoje);
    return { inicio: ini, fim, labelCurto: 'Últimos 7 dias', labelLongo: `${fmtBR(ini)} a ${fmtBR(fim)}` };
  }
  if (preset === 'mes_passado') {
    const mp = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
    const ini = primeiroDiaMes(mp);
    const fim = ultimoDiaMes(mp);
    return {
      inicio: ini, fim,
      labelCurto: `${NOME_MES_PT[mp.getMonth()]} ${mp.getFullYear()}`,
      labelLongo: `${fmtBR(ini)} a ${fmtBR(fim)}`,
    };
  }
  if (preset === 'custom') {
    // customIni/customFim vem no formato YYYY-MM-DD dos inputs date.
    const ini = customIni ? inicioDoDia(new Date(customIni + 'T00:00:00')) : primeiroDiaMes(ref);
    const fim = customFim ? fimDoDia(new Date(customFim + 'T00:00:00')) : ultimoDiaMes(ref);
    return {
      inicio: ini, fim,
      labelCurto: `${fmtBR(ini)} — ${fmtBR(fim)}`,
      labelLongo: `${fmtBR(ini)} a ${fmtBR(fim)}`,
    };
  }
  // este_mes (default) — usa ref (que pode ter sido navegado por setas ±mês)
  const ini = primeiroDiaMes(ref);
  const fim = ultimoDiaMes(ref);
  return {
    inicio: ini, fim,
    labelCurto: `${NOME_MES_PT[ref.getMonth()]} ${ref.getFullYear()}`,
    labelLongo: `${fmtBR(ini)} a ${fmtBR(fim)}`,
  };
}

// Tabela SEFAZ tPag — só os códigos relevantes pro varejo.
const MEIO_PAGAMENTO_LABEL: Record<string, string> = {
  '01': 'Dinheiro',
  '02': 'Cheque',
  '03': 'Cartão Crédito',
  '04': 'Cartão Débito',
  '05': 'Crédito Loja',
  '10': 'Vale Alimentação',
  '11': 'Vale Refeição',
  '15': 'Boleto',
  '17': 'PIX',
  '18': 'Transferência',
  '19': 'Programa Fidelidade',
  '90': 'Sem pagamento',
  '99': 'Outros',
};
const labelMeioPagamento = (cod: string) => MEIO_PAGAMENTO_LABEL[cod] || `Meio ${cod}`;

const parseJsonSafe = (raw: string | null | undefined): any | null => {
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
};

const extrairCliente = (nota: Nota): string => {
  const v = parseJsonSafe(nota.json_venda);
  return v?.cliente?.nome || '—';
};

// Formata data e hora em duas linhas — usado nas colunas de datas da tabela.
// Backend serializa datetimes UTC sem sufixo `Z`; JS interpretaria como local
// e mostraria horário 3h à frente. Anexamos `Z` quando falta tz info.
const parseUTC = (iso: string) =>
  new Date(/[Zz]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + 'Z');
const fmtDataHora = (iso: string) => {
  const d = parseUTC(iso);
  return {
    data: d.toLocaleDateString('pt-BR'),
    hora: d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
  };
};

export default function CentralDocumentos() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaSelecionada, setEmpresaSelecionada] = useState<string>('');
  const [notas, setNotas] = useState<Nota[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // v3 — aba ativa no topo (NFC-e / NF-e / Inutilizadas). Filtra `notas` no client
  // por modelo/status. Server-side já traz tudo do período — evita 3 requests.
  const [abaAtiva, setAbaAtiva] = useState<Aba>('nfce');

  // v3 — busca livre (nº nota, nº venda, cliente, CPF/CNPJ, chave)
  const [busca, setBusca] = useState<string>('');

  // v3 — alertas do banner ("N itens precisam de atenção")
  const [alertas, setAlertas] = useState<AlertasResponse | null>(null);

  // v3 — modal config contador (engrenagem)
  const [showConfigContador, setShowConfigContador] = useState<boolean>(false);
  const [contadorConfig, setContadorConfig] = useState<ContadorConfig | null>(null);
  const [salvandoContador, setSalvandoContador] = useState<boolean>(false);
  const [erroContador, setErroContador] = useState<string>('');

  // v3 — modal preview antes de exportar (V3.3)
  const [showPreview, setShowPreview] = useState<boolean>(false);
  const [preview, setPreview] = useState<PreviewExport | null>(null);
  const [carregandoPreview, setCarregandoPreview] = useState<boolean>(false);

  // v3 — modal enviar ao contador (dispara o email na hora)
  const [showEnviarContador, setShowEnviarContador] = useState<boolean>(false);
  const [enviandoContador, setEnviandoContador] = useState<boolean>(false);
  const [erroEnviarContador, setErroEnviarContador] = useState<string>('');
  const [sucessoEnviarContador, setSucessoEnviarContador] = useState<string>('');

  // Filtros
  const [filtroStatus, setFiltroStatus] = useState<string>('');
  const [preset, setPreset] = useState<Preset>('este_mes');
  const [periodoRef, setPeriodoRef] = useState<Date>(() => new Date());
  const [customInicio, setCustomInicio] = useState<string>('');
  const [customFim, setCustomFim] = useState<string>('');
  const [dropdownPeriodoAberto, setDropdownPeriodoAberto] = useState<boolean>(false);

  const intervalo = useMemo(
    () => resolverIntervalo(preset, periodoRef, customInicio, customFim),
    [preset, periodoRef, customInicio, customFim],
  );

  // ---------- Modais ----------
  const [notaSelecionadaCancel, setNotaSelecionadaCancel] = useState<Nota | null>(null);
  const [justificativa, setJustificativa] = useState<string>('');
  const [cancelando, setCancelando] = useState<boolean>(false);
  const [erroCancelamento, setErroCancelamento] = useState<string>('');

  const [notaSelecionadaReprocessar, setNotaSelecionadaReprocessar] = useState<Nota | null>(null);
  const [jsonEdicao, setJsonEdicao] = useState<string>('');
  const [reprocessando, setReprocessando] = useState<boolean>(false);
  const [erroReprocessar, setErroReprocessar] = useState<string>('');
  const [previewReprocessar, setPreviewReprocessar] = useState<{numero: number; serie: number; modelo: number} | null>(null);

  // Drawer de detalhes da venda (clicar no Nº Venda)
  const [notaDetalhe, setNotaDetalhe] = useState<Nota | null>(null);
  const vendaDetalhe = useMemo(
    () => notaDetalhe ? parseJsonSafe(notaDetalhe.json_venda) : null,
    [notaDetalhe],
  );

  // Exportar Lote (o "modal" agora é o preview — o download roda direto do preview)
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
          data_inicio: intervalo.inicio.toISOString().slice(0, 10),
          data_fim: intervalo.fim.toISOString().slice(0, 10),
          incluir: exportIncluir,
        },
        responseType: 'blob',
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
    } catch (err) {
      console.error(err);
      setErroExportacao('Nenhuma nota autorizada/cancelada foi encontrada com os filtros atuais para gerar o ZIP.');
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
      alert('Erro ao consultar o status da nota na SEFAZ.');
    } finally {
      setConsultandoId(null);
    }
  };

  // Inutilização por id — último recurso pra destravar a fila quando operador
  // desiste da venda rejeitada/pendente. Gera lastro fiscal permanente na SEFAZ.
  const [notaSelecionadaInutilizar, setNotaSelecionadaInutilizar] = useState<Nota | null>(null);
  const [justificativaInutilizar, setJustificativaInutilizar] = useState<string>('');
  const [inutilizando, setInutilizando] = useState<boolean>(false);
  const [erroInutilizar, setErroInutilizar] = useState<string>('');

  const abrirModalInutilizar = (nota: Nota) => {
    setNotaSelecionadaInutilizar(nota);
    setJustificativaInutilizar('');
    setErroInutilizar('');
  };

  const executarInutilizacao = async () => {
    if (!notaSelecionadaInutilizar) return;
    if (justificativaInutilizar.length < 15) {
      setErroInutilizar('A justificativa deve ter no mínimo 15 caracteres.');
      return;
    }
    setInutilizando(true);
    setErroInutilizar('');
    try {
      await api.post(`/empresas/${empresaSelecionada}/notas/${notaSelecionadaInutilizar.id}/inutilizar`, {
        justificativa: justificativaInutilizar,
      });
      setNotaSelecionadaInutilizar(null);
      carregarNotas();
    } catch (err: any) {
      setErroInutilizar(err.response?.data?.detail || 'Erro ao inutilizar a nota na SEFAZ.');
    } finally {
      setInutilizando(false);
    }
  };

  useEffect(() => {
    carregarEmpresas();
  }, []);

  useEffect(() => {
    if (empresaSelecionada) {
      carregarNotas();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empresaSelecionada, filtroStatus, preset, periodoRef, customInicio, customFim]);

  // Alertas do banner — recarrega junto com a troca de empresa/período
  useEffect(() => {
    if (empresaSelecionada) {
      carregarAlertas();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empresaSelecionada, notas.length]);

  const carregarEmpresas = async () => {
    try {
      const res = await api.get('/empresas/');
      setEmpresas(res.data);
      if (res.data.length > 0) {
        setEmpresaSelecionada(res.data[0].id.toString());
      }
    } catch (error) {
      console.error('Erro ao carregar empresas:', error);
    }
  };

  const baixarXML = async (nota: Nota) => {
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/${nota.id}/xml`, {
        responseType: 'blob',
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
      alert('Erro ao baixar o XML da nota.');
    }
  };

  const baixarPDF = async (nota: Nota) => {
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/${nota.id}/pdf`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch (err) {
      console.error(err);
      alert('Erro ao abrir o PDF da nota.');
    }
  };

  const copiarChave = async (chave: string | null) => {
    if (!chave) return;
    try {
      await navigator.clipboard.writeText(chave);
      alert('Chave de acesso copiada.');
    } catch {
      alert('Não foi possível copiar. Copie manualmente: ' + chave);
    }
  };

  const carregarNotas = async () => {
    setLoading(true);
    try {
      // Filtro server-side por data + status. O intervalo já vem resolvido no
      // useMemo (preset ou custom). Datetime em ISO é aceito pelo FastAPI.
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/`, {
        params: {
          data_inicio: intervalo.inicio.toISOString(),
          data_fim: intervalo.fim.toISOString(),
          status: filtroStatus || undefined,
        },
      });
      setNotas(res.data as Nota[]);
    } catch (error) {
      console.error('Erro ao carregar notas fiscais:', error);
    } finally {
      setLoading(false);
    }
  };

  // -------------------------------------------------------------------------
  // Central v3 — alertas, contador, preview export
  // -------------------------------------------------------------------------

  const carregarAlertas = async () => {
    if (!empresaSelecionada) return;
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/alertas`);
      setAlertas(res.data as AlertasResponse);
    } catch (err) {
      console.error('alertas:', err);
      setAlertas(null);
    }
  };

  const carregarContadorConfig = async () => {
    if (!empresaSelecionada) return;
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/contador`);
      setContadorConfig(res.data as ContadorConfig);
    } catch (err) {
      console.error('contador:', err);
      setContadorConfig(null);
    }
  };

  const abrirConfigContador = async () => {
    setErroContador('');
    await carregarContadorConfig();
    setShowConfigContador(true);
  };

  const salvarConfigContador = async () => {
    if (!contadorConfig) return;
    setSalvandoContador(true);
    setErroContador('');
    try {
      // Pydantic EmailStr rejeita "" com 422 — coerce vazio pra null (usuário
      // limpou o campo). Mesmo trato pra nome/templates pra ficar consistente.
      const naoVazio = (v: string | null | undefined) => (v && v.trim() ? v.trim() : null);
      const res = await api.put(`/empresas/${empresaSelecionada}/contador`, {
        nome_contador: naoVazio(contadorConfig.nome_contador),
        email_contador: naoVazio(contadorConfig.email_contador),
        email_cc_contador: naoVazio(contadorConfig.email_cc_contador),
        dia_envio_contador: contadorConfig.dia_envio_contador,
        envio_automatico_contador: contadorConfig.envio_automatico_contador,
        assunto_email_contador: naoVazio(contadorConfig.assunto_email_contador),
        mensagem_email_contador: naoVazio(contadorConfig.mensagem_email_contador),
      });
      setContadorConfig(res.data as ContadorConfig);
      setShowConfigContador(false);
    } catch (err: any) {
      setErroContador(err.response?.data?.detail || 'Erro ao salvar dados do contador.');
    } finally {
      setSalvandoContador(false);
    }
  };

  const abrirEnviarContador = async () => {
    setErroEnviarContador('');
    setSucessoEnviarContador('');
    if (!contadorConfig) await carregarContadorConfig();
    setShowEnviarContador(true);
  };

  const dispararEnvioContador = async () => {
    setEnviandoContador(true);
    setErroEnviarContador('');
    setSucessoEnviarContador('');
    try {
      const res = await api.post(`/empresas/${empresaSelecionada}/contador/enviar`, {
        data_inicio: intervalo.inicio.toISOString().slice(0, 10),
        data_fim: intervalo.fim.toISOString().slice(0, 10),
      });
      setSucessoEnviarContador(
        `E-mail enviado para ${res.data.destinatarios.join(', ')} (${res.data.qtd_notas} nota${res.data.qtd_notas === 1 ? '' : 's'}).`,
      );
    } catch (err: any) {
      setErroEnviarContador(err.response?.data?.detail || 'Erro ao enviar e-mail para o contador.');
    } finally {
      setEnviandoContador(false);
    }
  };

  const abrirPreviewExport = async () => {
    setShowPreview(true);
    setCarregandoPreview(true);
    setErroExportacao('');
    try {
      // Preview usa mesmo endpoint que o export, mas só conta — não bate na ACBr
      const modelo = abaAtiva === 'nfce' ? '65' : abaAtiva === 'nfe' ? '55' : undefined;
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/exportar-preview`, {
        params: {
          status: filtroStatus || undefined,
          modelo,
          data_inicio: intervalo.inicio.toISOString().slice(0, 10),
          data_fim: intervalo.fim.toISOString().slice(0, 10),
        },
      });
      setPreview(res.data as PreviewExport);
    } catch (err) {
      console.error(err);
      setPreview(null);
      setErroExportacao('Nenhuma nota autorizada/cancelada encontrada nesse filtro.');
    } finally {
      setCarregandoPreview(false);
    }
  };

  // "Exportar mês anterior" (V3.1) — atalho que muda pro preset e abre preview
  const exportarMesAnterior = () => {
    setPreset('mes_passado');
    // useEffect vai recarregar as notas — preview é aberto pelo próximo click
    // (não abrir automático pra não sobrepor com o LOAD)
    setTimeout(() => abrirPreviewExport(), 250);
  };

  // Período no mês atual? V3.2 — banner "período em aberto"
  const periodoEhMesAtual = useMemo(() => {
    const hoje = new Date();
    return (
      intervalo.inicio.getFullYear() === hoje.getFullYear() &&
      intervalo.inicio.getMonth() === hoje.getMonth() &&
      preset === 'este_mes'
    );
  }, [intervalo, preset]);

  const abrirModalCancelamento = (nota: Nota) => {
    setNotaSelecionadaCancel(nota);
    setJustificativa('');
    setErroCancelamento('');
  };

  const executarCancelamento = async () => {
    if (!notaSelecionadaCancel) return;
    if (justificativa.length < 15) {
      setErroCancelamento('A justificativa de cancelamento deve ter no mínimo 15 caracteres.');
      return;
    }

    setCancelando(true);
    setErroCancelamento('');
    try {
      await api.post(`/empresas/${empresaSelecionada}/notas/${notaSelecionadaCancel.id}/cancelar`, {
        justificativa,
      });
      setNotaSelecionadaCancel(null);
      carregarNotas();
    } catch (err: any) {
      setErroCancelamento(err.response?.data?.detail || 'Erro ao solicitar o cancelamento.');
    } finally {
      setCancelando(false);
    }
  };

  const abrirModalReprocessar = async (nota: Nota) => {
    setNotaSelecionadaReprocessar(nota);
    setJsonEdicao(JSON.stringify(JSON.parse(nota.json_venda), null, 2));
    setErroReprocessar('');
    setPreviewReprocessar(null);
    try {
      const res = await api.get(`/empresas/${empresaSelecionada}/notas/${nota.id}/reprocessar-preview`);
      setPreviewReprocessar({
        numero: res.data.numero,
        serie: res.data.serie,
        modelo: res.data.modelo,
      });
    } catch {
      // Preview falhou — não bloqueia o reprocessar; só some a caixinha
      setPreviewReprocessar(null);
    }
  };

  const executarReprocessamento = async () => {
    if (!notaSelecionadaReprocessar) return;
    try {
      JSON.parse(jsonEdicao);
    } catch (e: any) {
      setErroReprocessar(`JSON Inválido: ${e.message}`);
      return;
    }

    setReprocessando(true);
    setErroReprocessar('');
    try {
      const res = await api.put(`/empresas/${empresaSelecionada}/notas/${notaSelecionadaReprocessar.id}/reprocessar`, {
        json_venda: jsonEdicao,
      });
      const notaAtualizada = res.data as Nota;
      if (notaAtualizada.status === 'autorizada') {
        setNotaSelecionadaReprocessar(null);
        carregarNotas();
      } else {
        setErroReprocessar(`SEFAZ ${notaAtualizada.status}: ${extrairMotivoErro(notaAtualizada)}`);
        setNotaSelecionadaReprocessar(notaAtualizada);
        carregarNotas();
      }
    } catch (err: any) {
      setErroReprocessar(err.response?.data?.detail || 'Erro ao reprocessar a nota.');
    } finally {
      setReprocessando(false);
    }
  };

  const extrairMotivoErro = (nota: Nota) => {
    if (!nota.resposta_integradora) return 'Rejeição desconhecida';
    try {
      const parsed = JSON.parse(nota.resposta_integradora);
      if (parsed.error) {
        const inner = parsed.error.errors && parsed.error.errors[0];
        if (inner && inner.message) return `${parsed.error.code || ''}: ${inner.message}`.trim();
        if (parsed.error.message) return `${parsed.error.code || ''}: ${parsed.error.message}`.trim();
      }
      if (parsed.autorizacao?.motivo_status) return `${parsed.autorizacao.codigo_status || ''}: ${parsed.autorizacao.motivo_status}`.trim();
      if (parsed.autorizacao?.motivo) return `${parsed.autorizacao.codigo_status || ''}: ${parsed.autorizacao.motivo}`.trim();
      if (parsed.motivo) return parsed.motivo;
      if (parsed.mensagem) return parsed.mensagem;
      if (parsed.erro) return parsed.erro;
      return 'Rejeitada pela SEFAZ';
    } catch {
      return nota.resposta_integradora;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'autorizada':
        return <span className="px-2 py-1 text-xs font-bold text-i9 bg-i9-tint rounded-full flex items-center gap-1 w-max"><ShieldCheck size={12} /> Autorizado o uso</span>;
      case 'rejeitada':
        return <span className="px-2 py-1 text-xs font-bold text-warn bg-warn-tint rounded-full flex items-center gap-1 w-max"><AlertCircle size={12} /> Rejeitada</span>;
      case 'cancelada':
        return <span className="px-2 py-1 text-xs font-bold text-muted bg-line-soft rounded-full flex items-center gap-1 w-max"><XOctagon size={12} /> Cancelada</span>;
      case 'pendente_consulta':
        return <span className="px-2 py-1 text-xs font-bold text-[#8a6d0b] bg-[#fdf5d3] border border-[#f0dc80] rounded-full flex items-center gap-1 w-max"><Clock size={12} /> Pendente Consulta</span>;
      case 'denegada':
        return <span className="px-2 py-1 text-xs font-bold text-white bg-[#8f2c22] rounded-full flex items-center gap-1 w-max"><ShieldX size={12} /> Denegada</span>;
      case 'inutilizada':
        return <span className="px-2 py-1 text-xs font-bold text-white bg-ink rounded-full flex items-center gap-1 w-max"><Ban size={12} /> Inutilizada</span>;
      default:
        return <span className="px-2 py-1 text-xs font-bold text-ink-soft bg-field border border-line rounded-full flex items-center gap-1 w-max"><RefreshCw size={12} className="animate-spin" /> Processando</span>;
    }
  };

  // ----- Navegação por mês (setas ← →) -----
  const setaEsquerda = () => {
    // Ir pro mês anterior. Se estava em preset != este_mes, migra pra este_mes com ref no mês anterior.
    const proximoRef = new Date(periodoRef.getFullYear(), periodoRef.getMonth() - 1, 1);
    setPeriodoRef(proximoRef);
    setPreset('este_mes');
  };
  const setaDireita = () => {
    const proximoRef = new Date(periodoRef.getFullYear(), periodoRef.getMonth() + 1, 1);
    const hoje = new Date();
    // Bloqueia avançar além do mês atual.
    if (proximoRef > primeiroDiaMes(hoje)) return;
    setPeriodoRef(proximoRef);
    setPreset('este_mes');
  };
  const desabilitaSetaDireita = periodoRef.getFullYear() === new Date().getFullYear()
    && periodoRef.getMonth() === new Date().getMonth();

  const aplicarPreset = (p: Preset) => {
    setPreset(p);
    if (p === 'este_mes') setPeriodoRef(new Date());
    if (p === 'mes_passado') {
      const hoje = new Date();
      setPeriodoRef(new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1));
    }
    setDropdownPeriodoAberto(false);
  };

  // ----- v3 — recorte por aba ativa + busca livre -----
  // NFC-e: modelo 65, todos status EXCETO inutilizada.
  // NF-e:  modelo 55, todos status EXCETO inutilizada.
  // Inutilizadas: status inutilizada (qualquer modelo).
  const notasDaAba = useMemo(() => {
    let base: Nota[];
    if (abaAtiva === 'inutilizadas') {
      base = notas.filter(n => n.status === 'inutilizada');
    } else {
      const modelo = abaAtiva === 'nfce' ? '65' : '55';
      base = notas.filter(n => n.modelo === modelo && n.status !== 'inutilizada');
    }
    const q = busca.trim().toLowerCase();
    if (!q) return base;
    // Busca por nº nota, série, nº venda, cliente e chave de acesso (44 digitos)
    return base.filter(n => {
      const cliente = extrairCliente(n).toLowerCase();
      const venda = parseJsonSafe(n.json_venda);
      const doc = String(venda?.cliente?.cpf || venda?.cliente?.cnpj || '').toLowerCase();
      return (
        String(n.numero ?? '').includes(q)
        || (n.numero_venda || '').toLowerCase().includes(q)
        || cliente.includes(q)
        || (n.chave_acesso || '').includes(q)
        || doc.includes(q)
      );
    });
  }, [notas, abaAtiva, busca]);

  // Contadores por aba (mostrados no chip de cada tab)
  const contadoresAba = useMemo(() => ({
    nfce: notas.filter(n => n.modelo === '65' && n.status !== 'inutilizada').length,
    nfe: notas.filter(n => n.modelo === '55' && n.status !== 'inutilizada').length,
    inutilizadas: notas.filter(n => n.status === 'inutilizada').length,
  }), [notas]);

  // ----- Totais do período (só autorizadas entram na soma, dentro da aba) -----
  const notasAutorizadas = useMemo(
    () => notasDaAba.filter(n => n.status === 'autorizada'),
    [notasDaAba],
  );
  const totalPeriodo = useMemo(
    () => notasAutorizadas.reduce((s, n) => s + n.valor_total, 0),
    [notasAutorizadas],
  );

  return (
    <div className="flex flex-col gap-6 pb-12">

      {/* v3 — Tabs no topo (NFC-e / NF-e / Inutilizadas) */}
      <div className="border-b border-line flex items-center gap-1">
        {([
          ['nfce', 'NFC-e emitidas', Receipt, contadoresAba.nfce],
          ['nfe', 'NF-e emitidas', FileText, contadoresAba.nfe],
          ['inutilizadas', 'Notas inutilizadas', Ban, contadoresAba.inutilizadas],
        ] as [Aba, string, any, number][]).map(([key, label, Icon, count]) => {
          const ativo = abaAtiva === key;
          return (
            <button
              key={key}
              onClick={() => { setAbaAtiva(key); setFiltroStatus(''); }}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-bold border-b-2 -mb-px transition-colors ${
                ativo
                  ? 'text-i9-dark border-i9'
                  : 'text-muted border-transparent hover:text-ink hover:border-line'
              }`}
            >
              <Icon size={15} />
              {label}
              <span className={`text-[10px] font-extrabold rounded-full px-2 py-0.5 ${
                ativo ? 'bg-i9-tint text-i9-dark' : 'bg-line-soft text-muted'
              }`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Breadcrumb + Título dinâmico da aba (bate com o mockup do prototype) */}
      <div className="flex items-start">
        <div>
          <div className="text-xs font-semibold text-muted">Central de Documentos ›</div>
          <h1 className="text-3xl font-extrabold tracking-tight mt-1">
            {abaAtiva === 'nfce' ? 'NFC-e emitidas'
              : abaAtiva === 'nfe' ? 'NF-e emitidas'
              : 'Notas inutilizadas'}
          </h1>
        </div>
      </div>

      {/* Toolbar — Empresa ativa | Exportar lote | Exportar mês anterior | Enviar | Gear */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1 w-full md:w-64">
          <label className="text-[10px] font-bold text-muted uppercase">Empresa ativa</label>
          <select
            value={empresaSelecionada}
            onChange={(e) => setEmpresaSelecionada(e.target.value)}
            className="bg-card border border-line rounded-lg px-3 py-2.5 text-sm font-semibold text-ink focus:border-i9 outline-none shadow-sm w-full"
          >
            {empresas.map(emp => (
              <option key={emp.id} value={emp.id}>{emp.nome_fantasia || emp.razao_social}</option>
            ))}
          </select>
        </div>

        {/* Exportar lote — pastel azul, badge "NEW prévia" (V3.3 preview) */}
        <button
          onClick={abrirPreviewExport}
          className="relative bg-blue-50 hover:bg-blue-100 border border-blue-200 text-blue-900 font-bold px-5 py-3 rounded-lg text-sm flex items-center gap-2 flex-shrink-0 transition-colors"
        >
          <Download size={16} />
          Exportar lote
          <span className="ml-1 text-[10px] font-extrabold bg-white/70 border border-blue-200 text-blue-800 rounded px-1.5 py-0.5">
            NF-e + NFC-e
          </span>
          <span className="absolute -top-2 -right-2 text-[9px] font-extrabold bg-orange-500 text-white rounded px-1.5 py-0.5 shadow">
            NEW prévia
          </span>
        </button>

        {/* Exportar mês anterior — pastel verde, badge "NEW" (V3.1) */}
        <button
          onClick={exportarMesAnterior}
          className="relative bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-emerald-900 font-bold px-5 py-3 rounded-lg text-sm flex items-center gap-2 flex-shrink-0 transition-colors"
          title="Fecha o mês passado inteiro (V3.1)"
        >
          <CalendarDays size={16} />
          Exportar mês anterior
          <span className="ml-1 text-[10px] font-extrabold bg-white/70 border border-emerald-200 text-emerald-800 rounded px-1.5 py-0.5">
            p/ contador
          </span>
          <span className="absolute -top-2 -right-2 text-[9px] font-extrabold bg-orange-500 text-white rounded px-1.5 py-0.5 shadow">
            NEW
          </span>
        </button>

        {/* Enviar ao contador — ícone (dispara e-mail direto) */}
        <button
          onClick={abrirEnviarContador}
          className="relative bg-card border border-line hover:bg-line-soft text-ink-soft p-3 rounded-lg flex items-center shadow-sm flex-shrink-0"
          title="Enviar XMLs + relatório pro contador por e-mail"
        >
          <Send size={18} />
          <span className="absolute -top-2 -right-2 text-[9px] font-extrabold bg-orange-500 text-white rounded px-1.5 py-0.5 shadow">
            NEW
          </span>
        </button>

        {/* Engrenagem — dados do contador (V3.6) */}
        <button
          onClick={abrirConfigContador}
          className="relative bg-card border border-line hover:bg-line-soft text-ink-soft p-3 rounded-lg flex items-center shadow-sm flex-shrink-0"
          title="Dados do contador"
        >
          <Settings size={18} />
          <span className="absolute -top-2 -right-2 text-[9px] font-extrabold bg-orange-500 text-white rounded px-1.5 py-0.5 shadow">
            NEW
          </span>
        </button>
      </div>

      {/* v3 — Banner de alertas ("N itens precisam de atenção") */}
      {alertas && alertas.itens.length > 0 && (
        <div className="bg-warn-tint/60 border border-warn/40 rounded-DEFAULT shadow-sm px-4 py-3 flex flex-col md:flex-row items-start md:items-center gap-3">
          <div className="flex items-center gap-2 text-warn font-extrabold text-sm flex-shrink-0">
            <AlertCircle size={16} />
            {alertas.total} {alertas.total === 1 ? 'item precisa' : 'itens precisam'} de atenção
          </div>
          <div className="flex flex-wrap gap-2">
            {alertas.itens.map((a, i) => {
              const dot =
                a.severidade === 'erro' ? 'bg-warn'
                  : a.severidade === 'warn' ? 'bg-amber-500'
                  : 'bg-slate-400';
              return (
                <span
                  key={i}
                  className="inline-flex items-center gap-1.5 bg-card border border-line rounded-full px-3 py-1 text-xs font-semibold text-ink-soft"
                >
                  <span className={`w-2 h-2 rounded-full ${dot}`} />
                  {a.label}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Barra de Filtros + Card Total */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Status + Período (2 colunas) */}
        <div className="bg-card border border-line rounded-DEFAULT shadow p-5 lg:col-span-2 flex flex-col sm:flex-row gap-6">
          {/* Status — na aba Inutilizadas é redundante, esconde */}
          {abaAtiva !== 'inutilizadas' && (
            <div className="flex flex-col gap-1.5 sm:w-56">
              <label className="text-[10px] font-bold text-muted uppercase">Status</label>
              <select
                value={filtroStatus}
                onChange={(e) => setFiltroStatus(e.target.value)}
                className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none text-ink-soft"
              >
                <option value="">Todos os Status</option>
                <option value="autorizada">Autorizada</option>
                <option value="rejeitada">Rejeitada</option>
                <option value="pendente_consulta">Pendente Consulta</option>
                <option value="denegada">Denegada</option>
                <option value="cancelada">Cancelada</option>
                <option value="processando">Processando</option>
              </select>
            </div>
          )}

          {/* Período — seta ← nome_do_mês ▼ → */}
          <div className="flex flex-col gap-1.5 flex-1">
            <label className="text-[10px] font-bold text-muted uppercase text-center">Período</label>
            <div className="flex items-stretch border border-line rounded-lg overflow-hidden bg-field">
              <button
                type="button"
                onClick={setaEsquerda}
                className="px-3 hover:bg-line-soft transition-colors text-ink-soft"
                title="Mês anterior"
              >
                <ChevronLeft size={16} />
              </button>
              <div className="relative flex-1">
                <button
                  type="button"
                  onClick={() => setDropdownPeriodoAberto(o => !o)}
                  className="w-full h-full px-4 py-2 text-sm font-bold text-ink flex items-center justify-center gap-1.5 hover:bg-line-soft transition-colors"
                >
                  {intervalo.labelCurto}
                  <ChevronDown size={14} className="text-muted" />
                </button>
                {dropdownPeriodoAberto && (
                  <>
                    <div className="fixed inset-0 z-20" onClick={() => setDropdownPeriodoAberto(false)} />
                    <div className="absolute left-1/2 -translate-x-1/2 top-full mt-1 z-30 bg-card border border-line rounded-lg shadow-lg py-1 w-48">
                      {([
                        ['este_mes', 'Este mês'],
                        ['mes_passado', 'Mês passado'],
                        ['ultimos_7', 'Últimos 7 dias'],
                        ['ontem', 'Ontem'],
                        ['hoje', 'Hoje'],
                        ['custom', 'Escolher período'],
                      ] as [Preset, string][]).map(([key, label]) => (
                        <button
                          key={key}
                          onClick={() => aplicarPreset(key)}
                          className={`w-full text-left px-4 py-2 text-sm font-semibold transition-colors ${
                            preset === key ? 'bg-i9-tint text-i9-dark' : 'text-ink hover:bg-line-soft'
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              <button
                type="button"
                onClick={setaDireita}
                disabled={desabilitaSetaDireita && preset === 'este_mes'}
                className="px-3 hover:bg-line-soft transition-colors text-ink-soft disabled:opacity-30 disabled:cursor-not-allowed"
                title={desabilitaSetaDireita ? 'Já está no mês atual' : 'Próximo mês'}
              >
                <ChevronRight size={16} />
              </button>
            </div>
            <span className="text-[11px] text-muted text-center">{intervalo.labelLongo}</span>

            {/* Inputs custom só aparecem no preset custom */}
            {preset === 'custom' && (
              <div className="grid grid-cols-2 gap-2 mt-2">
                <input
                  type="date"
                  value={customInicio}
                  onChange={(e) => setCustomInicio(e.target.value)}
                  className="bg-field border border-line rounded-lg px-2 py-1.5 text-xs focus:border-i9 outline-none text-ink-soft"
                />
                <input
                  type="date"
                  value={customFim}
                  onChange={(e) => setCustomFim(e.target.value)}
                  className="bg-field border border-line rounded-lg px-2 py-1.5 text-xs focus:border-i9 outline-none text-ink-soft"
                />
              </div>
            )}
          </div>
        </div>

        {/* Card Total do Período */}
        <div className="bg-i9-tint/40 border border-i9/30 rounded-DEFAULT shadow p-5 flex flex-col justify-center gap-1">
          <span className="text-[10px] font-extrabold text-i9-dark uppercase tracking-wider text-center">Valor total no período</span>
          <span className="text-3xl font-extrabold text-i9-dark text-center font-mono">
            R$ {totalPeriodo.toFixed(2).replace('.', ',')}
          </span>
          <span className="text-[10px] text-muted text-center leading-relaxed">
            {notasAutorizadas.length} {notasAutorizadas.length === 1 ? 'nota autorizada' : 'notas autorizadas'} · canceladas, inutilizadas e rejeitadas não entram na soma
          </span>
        </div>
      </div>

      {/* v3 — Search bar + helper text (bate com o mockup) */}
      <div className="flex flex-col gap-2">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar nº da nota, venda, cliente, CPF/CNPJ ou chave"
            className="w-full bg-card border border-line rounded-lg pl-10 pr-4 py-3 text-sm focus:border-i9 outline-none shadow-sm placeholder:text-muted/70"
          />
        </div>
        <p className="text-[11px] text-muted text-center md:text-left">
          Clique no título da coluna para ordenar · no funil para filtrar · em "Nº Venda" para ver o histórico da venda
        </p>
      </div>

      {/* Tabela de Notas */}
      <div className="bg-card border border-line rounded-DEFAULT shadow overflow-hidden">
        {loading ? (
          <div className="p-12 text-center font-bold text-muted flex items-center justify-center gap-2">
            <Loader2 className="animate-spin text-i9" size={20} /> Carregando documentos fiscais...
          </div>
        ) : notasDaAba.length === 0 ? (
          <div className="p-16 text-center">
            <FileText size={48} className="mx-auto text-muted mb-4 opacity-40" />
            <h3 className="text-lg font-extrabold text-ink">Nenhum documento nesta aba</h3>
            <p className="text-muted text-sm mt-1">
              {abaAtiva === 'inutilizadas'
                ? 'Nenhuma numeração inutilizada no período.'
                : 'Nenhuma nota emitida nesse tipo no período selecionado.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="bg-bg text-muted text-[11px] uppercase tracking-wider font-extrabold border-b border-line">
                  <th className="px-4 py-3">Nº Venda</th>
                  <th className="px-4 py-3">Número</th>
                  <th className="px-4 py-3">Série</th>
                  <th className="px-4 py-3">Emissão</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Data do Status</th>
                  <th className="px-4 py-3">Cliente</th>
                  <th className="px-4 py-3">Valor da Nota</th>
                  <th className="px-4 py-3 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {notasDaAba.map((nota) => {
                  const emis = fmtDataHora(nota.criado_em);
                  const evento = fmtDataHora(nota.atualizado_em);
                  return (
                    <tr key={nota.id} className="hover:bg-i9-tint/10 transition-colors">
                      <td className="px-4 py-3">
                        {nota.numero_venda ? (
                          <button
                            onClick={() => setNotaDetalhe(nota)}
                            className="bg-line-soft hover:bg-i9-tint text-ink hover:text-i9-dark rounded px-2 py-1 font-mono text-xs font-bold transition-colors"
                            title="Ver detalhes da venda de origem"
                          >
                            {nota.numero_venda}
                          </button>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono font-bold text-ink">{nota.numero ?? '—'}</td>
                      <td className="px-4 py-3 font-mono text-ink-soft">{nota.serie ?? '—'}</td>
                      <td className="px-4 py-3 text-ink-soft whitespace-nowrap">
                        <div className="font-bold text-ink">{emis.data}</div>
                        <div className="text-[11px] text-muted">{emis.hora}</div>
                      </td>
                      <td className="px-4 py-3">
                        {getStatusBadge(nota.status)}
                      </td>
                      <td className="px-4 py-3 text-ink-soft whitespace-nowrap">
                        <div className="font-bold text-ink">{evento.data}</div>
                        <div className="text-[11px] text-muted">{evento.hora}</div>
                      </td>
                      <td className="px-4 py-3 text-ink-soft max-w-[200px]" title={extrairCliente(nota)}>
                        {/* V3.9 · nome do cliente em até 2 linhas (line-clamp) */}
                        <span className="block leading-tight" style={{
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}>
                          {extrairCliente(nota)}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-bold text-ink font-mono whitespace-nowrap">
                        R$ {nota.valor_total.toFixed(2).replace('.', ',')}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-2 items-center flex-wrap">
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
                                onClick={() => copiarChave(nota.chave_acesso)}
                                className="text-ink-soft hover:bg-line-soft p-1.5 rounded-lg flex items-center gap-1 text-xs font-bold border border-line transition-colors"
                                title="Copiar chave de acesso"
                              >
                                <Copy size={14} /> Copiar chave
                              </button>
                              <button
                                onClick={() => abrirModalCancelamento(nota)}
                                className="text-warn hover:bg-warn-tint p-1.5 rounded-lg text-xs font-bold transition-colors"
                              >
                                Cancelar
                              </button>
                            </>
                          )}

                          {nota.status === 'cancelada' && nota.chave_acesso && (
                            <button
                              onClick={() => copiarChave(nota.chave_acesso)}
                              className="text-ink-soft hover:bg-line-soft p-1.5 rounded-lg flex items-center gap-1 text-xs font-bold border border-line transition-colors"
                              title="Copiar chave de acesso"
                            >
                              <Copy size={14} /> Copiar chave
                            </button>
                          )}

                          {nota.status === 'rejeitada' && (
                            <>
                              <button
                                onClick={() => abrirModalReprocessar(nota)}
                                className="bg-i9 hover:opacity-90 text-white font-bold text-xs px-3 py-1.5 rounded-lg flex items-center gap-1 transition-opacity shadow-sm"
                                title="Corrigir e retransmitir (reusa o mesmo nNF)"
                              >
                                <RefreshCw size={12} />
                                Reprocessar
                              </button>
                              <button
                                onClick={() => abrirModalInutilizar(nota)}
                                className="text-ink-soft hover:bg-line-soft border border-line font-bold text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition-colors"
                                title="Último recurso: queima esse nNF na SEFAZ e destrava a fila (operador desistiu da venda)"
                              >
                                <Ban size={12} />
                                Inutilizar
                              </button>
                              <button
                                className="text-warn cursor-help p-1"
                                title={extrairMotivoErro(nota)}
                              >
                                <HelpCircle size={15} />
                              </button>
                            </>
                          )}

                          {nota.status === 'pendente_consulta' && (
                            <>
                              <button
                                onClick={() => consultarStatus(nota.id)}
                                disabled={consultandoId === nota.id}
                                className="bg-i9 hover:opacity-90 text-white font-bold text-xs px-3 py-1.5 rounded-lg flex items-center gap-1 transition-opacity shadow-sm disabled:opacity-50"
                                title="Pergunta à SEFAZ o veredito real dessa nota"
                              >
                                <Search size={12} className={consultandoId === nota.id ? 'animate-spin' : ''} />
                                {consultandoId === nota.id ? 'Consultando...' : 'Consultar SEFAZ'}
                              </button>
                              <button
                                onClick={() => abrirModalInutilizar(nota)}
                                className="text-ink-soft hover:bg-line-soft border border-line font-bold text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition-colors"
                                title="Último recurso: se operador desiste da venda"
                              >
                                <Ban size={12} />
                                Inutilizar
                              </button>
                            </>
                          )}

                          {nota.status === 'denegada' && (
                            <>
                              <span className="text-[10px] font-semibold text-muted italic">
                                nNF consumido — sem reenvio
                              </span>
                              <button
                                className="text-[#8f2c22] cursor-help p-1"
                                title={`SEFAZ denegou o uso desse número (cStat 110/301/302). ${extrairMotivoErro(nota)}`}
                              >
                                <HelpCircle size={15} />
                              </button>
                            </>
                          )}

                          {nota.status === 'inutilizada' && (
                            <span className="text-[10px] font-semibold text-muted italic">
                              Nº queimado na SEFAZ
                            </span>
                          )}

                          {nota.status === 'processando' && (
                            <button
                              onClick={() => consultarStatus(nota.id)}
                              disabled={consultandoId === nota.id}
                              className="bg-line-soft text-ink hover:bg-field border border-line font-bold text-xs px-3 py-1.5 rounded-lg flex items-center gap-1 transition-all shadow-sm disabled:opacity-50"
                            >
                              <RefreshCw size={12} className={consultandoId === nota.id ? 'animate-spin' : ''} />
                              {consultandoId === nota.id ? 'Consultando...' : 'Consultar Status'}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Drawer de Detalhes da Venda (clicar em Nº Venda) */}
      {notaDetalhe && (
        <div className="fixed inset-0 z-50 flex">
          <div className="flex-1 bg-ink/40 backdrop-blur-sm" onClick={() => setNotaDetalhe(null)} />
          <aside className="w-full max-w-md bg-card border-l border-line shadow-xl overflow-y-auto flex flex-col gap-5 p-6 animate-in slide-in-from-right duration-200">
            <div className="flex items-start justify-between border-b border-line-soft pb-4">
              <div>
                <div className="text-[10px] font-bold text-muted uppercase tracking-wider">Venda de origem</div>
                <h3 className="text-2xl font-extrabold text-ink font-mono mt-0.5">{notaDetalhe.numero_venda}</h3>
              </div>
              <button
                onClick={() => setNotaDetalhe(null)}
                className="text-muted hover:text-ink hover:bg-line-soft p-1.5 rounded-lg transition-colors"
                title="Fechar"
              >
                <X size={18} />
              </button>
            </div>

            {vendaDetalhe ? (
              <>
                {/* Cliente */}
                {vendaDetalhe.cliente && (
                  <section className="flex flex-col gap-1.5">
                    <div className="text-[10px] font-bold text-muted uppercase tracking-wider">Cliente</div>
                    <div className="text-sm font-bold text-ink">{vendaDetalhe.cliente.nome || '—'}</div>
                    {vendaDetalhe.cliente.cpf && <div className="text-xs text-ink-soft font-mono">CPF: {vendaDetalhe.cliente.cpf}</div>}
                    {vendaDetalhe.cliente.cnpj && <div className="text-xs text-ink-soft font-mono">CNPJ: {vendaDetalhe.cliente.cnpj}</div>}
                    {vendaDetalhe.cliente.endereco && (
                      <div className="text-xs text-ink-soft mt-1 leading-relaxed">
                        {[
                          vendaDetalhe.cliente.endereco.logradouro,
                          vendaDetalhe.cliente.endereco.numero,
                          vendaDetalhe.cliente.endereco.bairro,
                          vendaDetalhe.cliente.endereco.cidade,
                          vendaDetalhe.cliente.endereco.uf,
                        ].filter(Boolean).join(', ') || null}
                      </div>
                    )}
                  </section>
                )}

                {/* Itens */}
                {Array.isArray(vendaDetalhe.itens) && vendaDetalhe.itens.length > 0 && (
                  <section className="flex flex-col gap-2">
                    <div className="text-[10px] font-bold text-muted uppercase tracking-wider">Itens ({vendaDetalhe.itens.length})</div>
                    <div className="flex flex-col gap-1.5">
                      {vendaDetalhe.itens.map((it: any, i: number) => {
                        const qtd = Number(it.quantidade) || 0;
                        const unit = Number(it.valor_unitario) || 0;
                        const sub = qtd * unit;
                        return (
                          <div key={i} className="bg-field border border-line rounded p-2.5 flex flex-col gap-0.5">
                            <div className="flex items-start justify-between gap-2">
                              <span className="text-xs font-bold text-ink">{it.nome || it.codigo || '—'}</span>
                              <span className="text-xs font-mono font-bold text-ink whitespace-nowrap">
                                R$ {sub.toFixed(2).replace('.', ',')}
                              </span>
                            </div>
                            <div className="text-[10px] text-muted font-mono">
                              {qtd} {it.unidade || 'UN'} × R$ {unit.toFixed(2).replace('.', ',')}
                              {it.codigo && it.nome && it.codigo !== it.nome ? ` · ${it.codigo}` : ''}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                )}

                {/* Pagamentos */}
                {Array.isArray(vendaDetalhe.pagamentos) && vendaDetalhe.pagamentos.length > 0 && (
                  <section className="flex flex-col gap-2">
                    <div className="text-[10px] font-bold text-muted uppercase tracking-wider">Pagamentos</div>
                    <div className="flex flex-col gap-1">
                      {vendaDetalhe.pagamentos.map((p: any, i: number) => (
                        <div key={i} className="flex items-center justify-between text-xs">
                          <span className="text-ink-soft">{labelMeioPagamento(String(p.meio_pagamento))}</span>
                          <span className="font-mono font-bold text-ink">
                            R$ {Number(p.valor).toFixed(2).replace('.', ',')}
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </>
            ) : (
              <div className="text-xs text-muted italic">Detalhes da venda não disponíveis.</div>
            )}

            {/* Nota Fiscal */}
            <section className="flex flex-col gap-2 border-t border-line-soft pt-4">
              <div className="text-[10px] font-bold text-muted uppercase tracking-wider">Nota Fiscal</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <div className="text-[10px] text-muted uppercase">Número</div>
                  <div className="font-mono font-bold text-ink">{notaDetalhe.numero ?? '—'}</div>
                </div>
                <div>
                  <div className="text-[10px] text-muted uppercase">Série</div>
                  <div className="font-mono font-bold text-ink">{notaDetalhe.serie ?? '—'}</div>
                </div>
                <div>
                  <div className="text-[10px] text-muted uppercase">Modelo</div>
                  <div className="font-bold text-ink">{notaDetalhe.modelo === '65' ? 'NFC-e (65)' : 'NF-e (55)'}</div>
                </div>
                <div>
                  <div className="text-[10px] text-muted uppercase">Status</div>
                  <div>{getStatusBadge(notaDetalhe.status)}</div>
                </div>
              </div>
              {notaDetalhe.chave_acesso && (
                <div className="mt-1">
                  <div className="text-[10px] text-muted uppercase">Chave de Acesso</div>
                  <div className="font-mono text-[10px] text-ink-soft break-all leading-relaxed">
                    {notaDetalhe.chave_acesso}
                  </div>
                </div>
              )}
              {notaDetalhe.status === 'autorizada' && (
                <div className="flex gap-2 mt-2">
                  <button
                    onClick={() => baixarPDF(notaDetalhe)}
                    className="flex-1 bg-gradient-to-b from-i9 to-i9-dark text-white font-bold text-xs px-3 py-2 rounded-lg flex items-center justify-center gap-1.5 hover:opacity-90 transition-opacity shadow-sm"
                  >
                    <Eye size={14} /> Ver DANFE
                  </button>
                  <button
                    onClick={() => baixarXML(notaDetalhe)}
                    className="flex-1 text-ink-soft bg-field border border-line font-bold text-xs px-3 py-2 rounded-lg flex items-center justify-center gap-1.5 hover:bg-line-soft transition-colors"
                  >
                    <Download size={14} /> XML
                  </button>
                </div>
              )}
            </section>
          </aside>
        </div>
      )}

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
                  <><Loader2 size={12} className="animate-spin" /> Cancelando...</>
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

            <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs flex items-start gap-2">
              <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
              <div className="flex flex-col gap-0.5">
                <span className="font-bold">Motivo da Rejeição SEFAZ:</span>
                <span>{extrairMotivoErro(notaSelecionadaReprocessar)}</span>
              </div>
            </div>

            {previewReprocessar && (
              <div className="bg-field border border-line rounded-lg p-3 text-xs flex items-center justify-between">
                <span className="text-muted font-semibold uppercase">Próxima transmissão</span>
                <span className="font-mono font-bold text-ink">
                  {previewReprocessar.modelo === 55 ? 'NF-e' : 'NFC-e'} {previewReprocessar.modelo} · nº {previewReprocessar.numero} · série {previewReprocessar.serie}
                </span>
              </div>
            )}

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
                  <><Loader2 size={12} className="animate-spin" /> Enviando...</>
                ) : (
                  <><RefreshCw size={12} /> Retransmitir Nota</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Inutilizar */}
      {notaSelecionadaInutilizar && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-line rounded-xl shadow-lg max-w-md w-full p-6 flex flex-col gap-4 animate-in fade-in-50 zoom-in-95 duration-150">
            <div>
              <h3 className="text-lg font-extrabold text-ink flex items-center gap-2">
                <Ban size={18} className="text-[#8f2c22]" />
                Inutilizar Numeração
              </h3>
              <p className="text-xs text-muted mt-1">
                Nota Nº <span className="font-mono font-bold">{notaSelecionadaInutilizar.numero}</span> · Série {notaSelecionadaInutilizar.serie} · Modelo {notaSelecionadaInutilizar.modelo === '65' ? 'NFC-e' : 'NF-e'}
              </p>
            </div>

            <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs flex items-start gap-2">
              <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
              <div className="flex flex-col gap-1">
                <span className="font-bold">Ação irreversível.</span>
                <span>
                  Isso declara à SEFAZ que o número <strong>{notaSelecionadaInutilizar.numero}</strong> foi queimado sem virar documento fiscal.
                  Só use se o operador <strong>desistiu da venda</strong> — a preferência é sempre corrigir e reenviar (mesmo nNF).
                </span>
              </div>
            </div>

            {erroInutilizar && (
              <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs font-semibold">
                {erroInutilizar}
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Justificativa *</label>
              <textarea
                value={justificativaInutilizar}
                onChange={(e) => setJustificativaInutilizar(e.target.value)}
                placeholder="Motivo real da inutilização (mínimo 15 caracteres)..."
                rows={3}
                className="bg-field border border-line rounded-lg p-2.5 text-xs focus:border-i9 outline-none resize-none text-ink-soft"
              />
              <span className="text-[10px] text-muted text-right">
                {justificativaInutilizar.length}/15 caracteres necessários
              </span>
            </div>

            <div className="flex justify-end gap-2 border-t border-line-soft pt-4 mt-1">
              <button
                onClick={() => setNotaSelecionadaInutilizar(null)}
                className="px-4 py-2 text-xs font-bold text-ink-soft bg-field border border-line rounded-lg hover:bg-line-soft transition-colors"
                disabled={inutilizando}
              >
                Voltar
              </button>
              <button
                onClick={executarInutilizacao}
                className="px-4 py-2 text-xs font-bold text-white bg-[#8f2c22] rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-1.5"
                disabled={inutilizando || justificativaInutilizar.length < 15}
              >
                {inutilizando ? (
                  <><Loader2 size={12} className="animate-spin" /> Inutilizando...</>
                ) : (
                  <><Ban size={12} /> Confirmar Inutilização</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* v3.3 · Modal Preview antes de baixar (também é o modal Exportar lote) */}
      {showPreview && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-line rounded-xl shadow-lg max-w-lg w-full p-6 flex flex-col gap-4 animate-in fade-in-50 zoom-in-95 duration-150">
            <div>
              <h3 className="text-lg font-extrabold text-ink flex items-center gap-2">
                <Package size={18} className="text-i9" />
                Prévia do lote antes de baixar
              </h3>
              <p className="text-xs text-muted mt-1">
                Gera ZIP com pastas <b>NFC-e / NF-e / Canceladas</b> + <b>RELATORIO.pdf</b> resumindo o período.
              </p>
            </div>

            {/* V3.2 · alerta período do mês atual */}
            {periodoEhMesAtual && (
              <div className="bg-amber-50 border border-amber-200 text-amber-800 p-3 rounded-lg text-xs flex items-start gap-2">
                <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
                <span>
                  <b>Você está exportando o mês atual, que ainda está em aberto.</b> Novas notas
                  emitidas depois deste download não estarão no ZIP. Para envio ao contador, prefira
                  <b> "Exportar mês anterior"</b>.
                </span>
              </div>
            )}

            {erroExportacao && (
              <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs font-semibold">
                {erroExportacao}
              </div>
            )}

            {carregandoPreview ? (
              <div className="flex items-center gap-2 text-muted text-xs font-semibold">
                <Loader2 size={14} className="animate-spin" /> Calculando prévia...
              </div>
            ) : preview ? (
              <>
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-i9-tint/40 border border-i9/30 rounded-lg p-3 text-center">
                    <div className="text-[10px] font-extrabold text-i9-dark uppercase">NFC-e</div>
                    <div className="text-2xl font-extrabold text-i9-dark">{preview.qtd_nfce_autorizadas}</div>
                    <div className="text-[10px] text-muted">autorizadas</div>
                  </div>
                  <div className="bg-i9-tint/40 border border-i9/30 rounded-lg p-3 text-center">
                    <div className="text-[10px] font-extrabold text-i9-dark uppercase">NF-e</div>
                    <div className="text-2xl font-extrabold text-i9-dark">{preview.qtd_nfe_autorizadas}</div>
                    <div className="text-[10px] text-muted">autorizadas</div>
                  </div>
                  <div className="bg-line-soft border border-line rounded-lg p-3 text-center">
                    <div className="text-[10px] font-extrabold text-muted uppercase">Canceladas</div>
                    <div className="text-2xl font-extrabold text-ink">{preview.qtd_canceladas}</div>
                    <div className="text-[10px] text-muted">no ZIP também</div>
                  </div>
                </div>

                <div className="bg-line-soft/50 border border-line-soft p-3 rounded-lg text-[11px] text-ink-soft flex flex-col gap-1">
                  <div className="flex justify-between">
                    <span>Período:</span>
                    <span className="font-bold">{preview.periodo.label}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Valor autorizado:</span>
                    <span className="font-bold font-mono">
                      R$ {preview.valor_total_autorizadas.toFixed(2).replace('.', ',')}
                    </span>
                  </div>
                </div>
              </>
            ) : null}

            <div className="flex flex-col gap-2.5">
              <span className="text-xs font-bold text-muted uppercase">Documentos a incluir</span>
              <div className="grid grid-cols-3 gap-2">
                {(['ambos', 'xml', 'pdf'] as const).map(op => (
                  <button
                    key={op}
                    type="button"
                    onClick={() => setExportIncluir(op)}
                    className={`py-2 px-3 text-xs font-bold rounded-lg border transition-all ${
                      exportIncluir === op ? 'bg-i9 border-i9 text-white' : 'bg-field border-line text-ink hover:bg-line-soft'
                    }`}
                  >
                    {op === 'ambos' ? 'XML & PDF' : op === 'xml' ? 'Apenas XML' : 'Apenas PDF'}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-line-soft pt-4 mt-1">
              <button
                onClick={() => setShowPreview(false)}
                className="px-4 py-2 text-xs font-bold text-ink-soft bg-field border border-line rounded-lg hover:bg-line-soft transition-colors"
                disabled={exportando}
              >
                Fechar
              </button>
              <button
                onClick={() => executarExportacao().then(() => setShowPreview(false))}
                className="px-4 py-2 text-xs font-bold text-white bg-gradient-to-b from-i9 to-i9-dark rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-1.5 shadow-sm"
                disabled={exportando || carregandoPreview || !preview || preview.qtd_total === 0}
              >
                {exportando ? (
                  <><Loader2 size={12} className="animate-spin" /> Gerando ZIP...</>
                ) : (
                  <><Download size={12} /> Baixar ZIP</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* v3.6 · Modal Dados do contador (engrenagem) */}
      {showConfigContador && contadorConfig && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-line rounded-xl shadow-lg max-w-2xl w-full p-6 flex flex-col gap-4 animate-in fade-in-50 zoom-in-95 duration-150 max-h-[92vh] overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-extrabold text-ink flex items-center gap-2">
                  Dados do contador
                  <span className="text-[10px] bg-i9-tint text-i9-dark px-2 py-0.5 rounded-full font-extrabold uppercase">NEW</span>
                </h3>
                <p className="text-xs text-muted mt-1">Usados no botão "Enviar ao contador". Preenche uma vez só.</p>
              </div>
              <button onClick={() => setShowConfigContador(false)} className="text-muted hover:text-ink p-1.5 rounded-lg hover:bg-line-soft"><X size={16} /></button>
            </div>

            {erroContador && (
              <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs font-semibold">{erroContador}</div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">Nome do contador</label>
                <input
                  type="text"
                  value={contadorConfig.nome_contador || ''}
                  onChange={(e) => setContadorConfig({ ...contadorConfig, nome_contador: e.target.value })}
                  placeholder="Ex.: Escritório Contábil Silva"
                  className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">E-mail do contador</label>
                <input
                  type="email"
                  value={contadorConfig.email_contador || ''}
                  onChange={(e) => setContadorConfig({ ...contadorConfig, email_contador: e.target.value })}
                  placeholder="fiscal@escritorio.com.br"
                  className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Enviar cópia para (opcional)</label>
              <input
                type="email"
                value={contadorConfig.email_cc_contador || ''}
                onChange={(e) => setContadorConfig({ ...contadorConfig, email_cc_contador: e.target.value })}
                placeholder="Seu e-mail, para guardar uma cópia"
                className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Assunto</label>
              <input
                type="text"
                value={contadorConfig.assunto_email_contador || 'XMLs {empresa} · {periodo}'}
                onChange={(e) => setContadorConfig({ ...contadorConfig, assunto_email_contador: e.target.value })}
                className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none font-mono"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Mensagem padrão</label>
              <textarea
                value={contadorConfig.mensagem_email_contador || 'Olá, {contador}!\n\nSegue em anexo o lote de XMLs e o relatório fiscal da {empresa} referente a {periodo}.\n\nQualquer dúvida, é só responder este e-mail.'}
                onChange={(e) => setContadorConfig({ ...contadorConfig, mensagem_email_contador: e.target.value })}
                rows={6}
                className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none resize-none"
              />
              <span className="text-[10px] text-muted">
                Inserir: <span className="font-mono bg-line-soft px-1.5 py-0.5 rounded">{'{contador}'}</span>{' '}
                <span className="font-mono bg-line-soft px-1.5 py-0.5 rounded">{'{empresa}'}</span>{' '}
                <span className="font-mono bg-line-soft px-1.5 py-0.5 rounded">{'{periodo}'}</span>
              </span>
            </div>

            {/* Envio automático mensal */}
            <div className="border border-line rounded-lg p-4 bg-field/40 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-extrabold text-ink flex items-center gap-2">
                    <CalendarDays size={14} className="text-i9" />
                    Envio automático mensal
                  </div>
                  <p className="text-[11px] text-muted mt-0.5">
                    Todo mês, no dia escolhido, dispara automaticamente com o consolidado do mês anterior.
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={contadorConfig.envio_automatico_contador}
                    onChange={(e) => setContadorConfig({ ...contadorConfig, envio_automatico_contador: e.target.checked })}
                    className="sr-only peer"
                  />
                  <div className="w-10 h-5 bg-line rounded-full peer-checked:bg-i9 transition-colors relative">
                    <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${contadorConfig.envio_automatico_contador ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </div>
                </label>
              </div>

              {contadorConfig.envio_automatico_contador && (
                <div className="flex items-center gap-2">
                  <label className="text-xs font-bold text-muted uppercase">Dia do mês</label>
                  <select
                    value={contadorConfig.dia_envio_contador || ''}
                    onChange={(e) => setContadorConfig({ ...contadorConfig, dia_envio_contador: e.target.value ? parseInt(e.target.value) : null })}
                    className="bg-field border border-line rounded-lg px-3 py-1.5 text-sm focus:border-i9 outline-none"
                  >
                    <option value="">—</option>
                    {Array.from({ length: 28 }, (_, i) => i + 1).map(d => (
                      <option key={d} value={d}>{d.toString().padStart(2, '0')}</option>
                    ))}
                  </select>
                  <span className="text-[11px] text-muted">1 a 28 (evita fevereiro sem dia 29-31)</span>
                </div>
              )}

              {!contadorConfig.smtp_configurado && (
                <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-2 rounded-lg text-[11px] font-semibold">
                  SMTP do InnoFiscal não configurado — envio automático ficará inativo até o suporte configurar.
                </div>
              )}
            </div>

            {/* Remetente — bloqueado no e-mail InnoFiscal por enquanto (V3.10 futuro) */}
            <div className="border border-dashed border-amber-300 rounded-lg p-4 bg-amber-50 flex flex-col gap-2">
              <div className="text-xs font-extrabold text-amber-800 uppercase">Remetente do e-mail</div>
              <label className="flex items-center gap-2 text-sm font-semibold text-ink">
                <input type="radio" checked readOnly className="accent-i9" />
                E-mail do InnoFiscal (padrão)
              </label>
              <label className="flex items-center gap-2 text-sm text-muted cursor-not-allowed">
                <input type="radio" disabled className="opacity-40" />
                E-mail da loja <span className="text-[10px]">(em breve)</span>
              </label>
              <p className="text-[11px] text-amber-700 mt-1">
                Por enquanto sai pelo e-mail do InnoFiscal. A opção de enviar pelo e-mail da loja fica visível, porém desativada.
              </p>
            </div>

            <div className="flex justify-end gap-2 border-t border-line-soft pt-4 mt-1">
              <button onClick={() => setShowConfigContador(false)} disabled={salvandoContador} className="px-4 py-2 text-xs font-bold text-ink-soft bg-field border border-line rounded-lg hover:bg-line-soft transition-colors">
                Cancelar
              </button>
              <button onClick={salvarConfigContador} disabled={salvandoContador} className="px-4 py-2 text-xs font-bold text-white bg-gradient-to-b from-i9 to-i9-dark rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-1.5 shadow-sm">
                {salvandoContador ? <><Loader2 size={12} className="animate-spin" /> Salvando...</> : 'Salvar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Enviar ao contador (dispara e-mail na hora) */}
      {showEnviarContador && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-card border border-line rounded-xl shadow-lg max-w-md w-full p-6 flex flex-col gap-4 animate-in fade-in-50 zoom-in-95 duration-150">
            <div className="flex items-start justify-between">
              <h3 className="text-lg font-extrabold text-ink flex items-center gap-2">
                <Send size={18} className="text-i9" />
                Enviar ao contador
              </h3>
              <button onClick={() => setShowEnviarContador(false)} className="text-muted hover:text-ink p-1.5 rounded-lg hover:bg-line-soft"><X size={16} /></button>
            </div>

            {!contadorConfig?.email_contador ? (
              <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs">
                Configure o e-mail do contador na engrenagem antes de enviar.
              </div>
            ) : (
              <>
                <div className="bg-field border border-line rounded-lg p-3 text-xs flex flex-col gap-1">
                  <div><span className="text-muted">Para:</span> <b>{contadorConfig.email_contador}</b></div>
                  {contadorConfig.email_cc_contador && (
                    <div><span className="text-muted">Cc:</span> {contadorConfig.email_cc_contador}</div>
                  )}
                  <div><span className="text-muted">Período:</span> {intervalo.labelLongo}</div>
                  <div><span className="text-muted">Anexo:</span> ZIP (XMLs + PDFs + RELATORIO.pdf)</div>
                </div>

                {periodoEhMesAtual && (
                  <div className="bg-amber-50 border border-amber-200 text-amber-800 p-3 rounded-lg text-xs flex items-start gap-2">
                    <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
                    <span>O período selecionado é o <b>mês atual em aberto</b>. Para fechamento, prefira o botão "Exportar mês anterior" e envie a partir dele.</span>
                  </div>
                )}

                {erroEnviarContador && (
                  <div className="bg-warn-tint border border-[#f0c9c4] text-warn p-3 rounded-lg text-xs font-semibold">{erroEnviarContador}</div>
                )}
                {sucessoEnviarContador && (
                  <div className="bg-i9-tint border border-i9/30 text-i9-dark p-3 rounded-lg text-xs font-semibold">{sucessoEnviarContador}</div>
                )}
              </>
            )}

            <div className="flex justify-end gap-2 border-t border-line-soft pt-4 mt-1">
              <button onClick={() => setShowEnviarContador(false)} disabled={enviandoContador} className="px-4 py-2 text-xs font-bold text-ink-soft bg-field border border-line rounded-lg hover:bg-line-soft transition-colors">
                Fechar
              </button>
              <button
                onClick={dispararEnvioContador}
                disabled={enviandoContador || !contadorConfig?.email_contador || !!sucessoEnviarContador}
                className="px-4 py-2 text-xs font-bold text-white bg-gradient-to-b from-i9 to-i9-dark rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-1.5 shadow-sm"
              >
                {enviandoContador ? <><Loader2 size={12} className="animate-spin" /> Enviando...</> : <><Send size={12} /> Enviar agora</>}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
