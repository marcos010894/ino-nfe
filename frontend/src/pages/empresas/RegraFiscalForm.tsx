import { useState, useEffect } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { ArrowLeft, Save, Trash2 } from 'lucide-react';
import api from '../../lib/api';

type AbaId = 'base' | 'icms' | 'st' | 'ipi' | 'pis' | 'reforma';

const ABAS: { id: AbaId; label: string; badge?: string }[] = [
  { id: 'base', label: 'Base' },
  { id: 'icms', label: 'ICMS' },
  { id: 'st', label: 'ICMS-ST / FCP / DIFAL' },
  { id: 'ipi', label: 'IPI / II' },
  { id: 'pis', label: 'PIS / COFINS' },
  { id: 'reforma', label: 'Reforma Tributária', badge: 'Vigente 01/08/2026' },
];

const ORIGENS_ICMS = [
  { v: '0', l: '0 - Nacional' },
  { v: '1', l: '1 - Estrangeira (Importação direta)' },
  { v: '2', l: '2 - Estrangeira (Mercado interno)' },
  { v: '3', l: '3 - Nacional (conteúdo importação > 40%)' },
  { v: '4', l: '4 - Nacional (processos produtivos básicos)' },
  { v: '5', l: '5 - Nacional (conteúdo importação < 40%)' },
  { v: '6', l: '6 - Estrangeira (Importação direta, sem similar nacional)' },
  { v: '7', l: '7 - Estrangeira (Mercado interno, sem similar nacional)' },
  { v: '8', l: '8 - Nacional (conteúdo importação > 70%)' },
];

const defaultForm = {
  nome: '',
  cfop: '',
  ncm_padrao: '',
  cest: '',
  cbenef: '',

  origem_icms: '0',
  cst_csosn: '',
  icms_aliquota: 0,
  mod_bc: '',
  p_red_bc: 0,
  mot_des_icms: '',
  v_icms_deson: 0,

  mod_bc_st: '',
  p_mva_st: 0,
  p_red_bc_st: 0,
  p_icms_st: 0,

  p_fcp: 0,
  p_fcp_st: 0,

  p_icms_uf_dest: 0,
  p_icms_interpart: 0,
  p_fcp_uf_dest: 0,

  ipi_cst: '',
  ipi_aliquota: 0,
  ipi_cenq: '',

  ii_aliquota: 0,

  pis_cst: '01',
  pis_aliquota: 0,
  cofins_cst: '01',
  cofins_aliquota: 0,

  cbs_cst: '',
  cbs_cclass_trib: '',
  cbs_aliquota: 0,

  ibs_uf_aliquota: 0,
  ibs_mun_aliquota: 0,

  is_cst: '',
  is_aliquota: 0,

  regime_monofasico: false,
  credito_presumido: false,
  diferimento: false,

  padrao: false,
};

export default function RegraFiscalForm() {
  const { id, regraId } = useParams();
  const navigate = useNavigate();
  const isEditing = Boolean(regraId);

  const [formData, setFormData] = useState<typeof defaultForm>(defaultForm);
  const [aba, setAba] = useState<AbaId>('base');
  const [loading, setLoading] = useState(isEditing);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  useEffect(() => {
    if (isEditing) {
      api.get(`/empresas/${id}/regras/`)
        .then(res => {
          const regra = res.data.find((r: any) => r.id === Number(regraId));
          if (regra) {
            // Mescla com defaults — campos novos ausentes viram default
            setFormData({ ...defaultForm, ...regra });
          } else {
            navigate(`/empresas/${id}/regras`);
          }
          setLoading(false);
        })
        .catch(() => {
          setErro('Erro ao carregar regra fiscal.');
          setLoading(false);
        });
    }
  }, [id, regraId, navigate, isEditing]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      setFormData(prev => ({ ...prev, [name]: (e.target as HTMLInputElement).checked }));
    } else {
      setFormData(prev => ({ ...prev, [name]: value }));
    }
  };

  const handleNumberChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData(prev => ({ ...prev, [e.target.name]: parseFloat(e.target.value) || 0 }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro('');

    if (formData.cfop.length !== 4) {
      setErro('O CFOP deve ter exatamente 4 dígitos.');
      setAba('base');
      return;
    }
    if (formData.ncm_padrao.length !== 8) {
      setErro('O NCM deve ter exatamente 8 dígitos.');
      setAba('base');
      return;
    }

    // Sanitizar strings vazias em campos opcionais para null antes de enviar
    const payload: any = { ...formData };
    Object.keys(payload).forEach(k => {
      if (payload[k] === '') payload[k] = null;
    });

    setSalvando(true);
    try {
      if (isEditing) {
        await api.put(`/empresas/${id}/regras/${regraId}`, payload);
      } else {
        await api.post(`/empresas/${id}/regras/`, payload);
      }
      navigate(`/empresas/${id}/regras`);
    } catch (err: any) {
      setErro(err.response?.data?.detail || 'Erro ao salvar a regra fiscal.');
    } finally {
      setSalvando(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Tem certeza que deseja excluir esta regra fiscal?')) return;
    try {
      await api.delete(`/empresas/${id}/regras/${regraId}`);
      navigate(`/empresas/${id}/regras`);
    } catch {
      setErro('Erro ao excluir regra fiscal.');
    }
  };

  if (loading) return <div className="p-8 text-center text-muted font-bold">Carregando...</div>;

  const inputClass = "bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none";
  const inputMonoClass = `${inputClass} font-mono`;
  const labelClass = "text-xs font-bold text-muted uppercase";

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <Link to={`/empresas/${id}/regras`} className="text-muted hover:text-ink transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-extrabold tracking-tight">
            {isEditing ? 'Editar Regra Fiscal' : 'Nova Regra Fiscal'}
          </h1>
        </div>
        {isEditing && (
          <button onClick={handleDelete} className="text-warn hover:bg-warn-tint px-3 py-2 rounded-lg font-bold text-sm flex items-center gap-2 transition-colors">
            <Trash2 size={16} /> Excluir
          </button>
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        {erro && (
          <div className="bg-warn-tint text-warn p-3 rounded-lg text-sm font-semibold border border-[#f0c9c4]">
            {erro}
          </div>
        )}

        {/* Tabs */}
        <div className="flex flex-wrap gap-1 border-b border-line">
          {ABAS.map(a => (
            <button
              key={a.id}
              type="button"
              onClick={() => setAba(a.id)}
              className={`px-4 py-2 text-sm font-bold transition-colors border-b-2 -mb-px flex items-center gap-2 ${
                aba === a.id
                  ? 'border-i9 text-i9'
                  : 'border-transparent text-muted hover:text-ink'
              }`}
            >
              {a.label}
              {a.badge && (
                <span className="text-[9px] uppercase tracking-wider bg-i9-tint text-i9 px-1.5 py-0.5 rounded font-bold">
                  {a.badge}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Aba Base */}
        {aba === 'base' && (
          <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
            <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">Informações Base</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5 md:col-span-2">
                <label className={labelClass}>Nome da Regra *</label>
                <input name="nome" value={formData.nome} onChange={handleChange} required placeholder="Ex: Venda dentro do Estado (Simples)" className={inputClass} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>CFOP *</label>
                <input name="cfop" value={formData.cfop} onChange={handleChange} required minLength={4} maxLength={4} placeholder="Ex: 5102" className={inputMonoClass} />
                <span className="text-[10px] text-muted">Apenas números (4 dígitos)</span>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>NCM Padrão *</label>
                <input name="ncm_padrao" value={formData.ncm_padrao} onChange={handleChange} required minLength={8} maxLength={8} placeholder="Ex: 71131900" className={inputMonoClass} />
                <span className="text-[10px] text-muted">Apenas números (8 dígitos)</span>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>CEST</label>
                <input name="cest" value={formData.cest} onChange={handleChange} maxLength={7} placeholder="Opcional (7 dígitos)" className={inputMonoClass} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>cBenef (Código de Benefício Fiscal)</label>
                <input name="cbenef" value={formData.cbenef} onChange={handleChange} maxLength={10} placeholder="Ex: PE800001 (obrigatório em RS/BA/PE/PB)" className={inputMonoClass} />
              </div>
              <div className="flex items-center gap-2 mt-2 md:col-span-2 bg-line-soft p-3 rounded-lg border border-line">
                <input type="checkbox" id="padrao" name="padrao" checked={formData.padrao} onChange={handleChange} className="w-4 h-4 text-i9 border-line rounded focus:ring-i9" />
                <label htmlFor="padrao" className="text-sm font-bold text-ink cursor-pointer">Definir como Regra Padrão do Sistema</label>
              </div>
            </div>
          </div>
        )}

        {/* Aba ICMS */}
        {aba === 'icms' && (
          <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
            <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">ICMS (Estadual)</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>Origem da Mercadoria</label>
                <select name="origem_icms" value={formData.origem_icms} onChange={handleChange} className={inputClass}>
                  {ORIGENS_ICMS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>CST ou CSOSN *</label>
                <input name="cst_csosn" value={formData.cst_csosn} onChange={handleChange} required placeholder="Ex: 102, 00, 10, 20, 60, 900" className={inputMonoClass} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>Alíquota ICMS (%)</label>
                <input type="number" step="0.01" name="icms_aliquota" value={formData.icms_aliquota} onChange={handleNumberChange} className={inputMonoClass} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>Modalidade BC</label>
                <select name="mod_bc" value={formData.mod_bc} onChange={handleChange} className={inputClass}>
                  <option value="">— não definir —</option>
                  <option value="0">0 - Margem Valor Agregado (%)</option>
                  <option value="1">1 - Pauta (Valor)</option>
                  <option value="2">2 - Preço Tabelado Máx. (valor)</option>
                  <option value="3">3 - Valor da operação</option>
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>% Redução BC</label>
                <input type="number" step="0.01" name="p_red_bc" value={formData.p_red_bc} onChange={handleNumberChange} className={inputMonoClass} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>Motivo Desoneração</label>
                <input name="mot_des_icms" value={formData.mot_des_icms} onChange={handleChange} maxLength={2} placeholder="Ex: 9 - Outros" className={inputMonoClass} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>Valor ICMS Desonerado (R$)</label>
                <input type="number" step="0.01" name="v_icms_deson" value={formData.v_icms_deson} onChange={handleNumberChange} className={inputMonoClass} />
              </div>
            </div>
          </div>
        )}

        {/* Aba ICMS-ST / FCP / DIFAL */}
        {aba === 'st' && (
          <div className="flex flex-col gap-6">
            <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
              <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">ICMS Substituição Tributária</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Modalidade BC ST</label>
                  <select name="mod_bc_st" value={formData.mod_bc_st} onChange={handleChange} className={inputClass}>
                    <option value="">— não definir —</option>
                    <option value="0">0 - Preço tabelado ou máx. sugerido</option>
                    <option value="1">1 - Lista Negativa (valor)</option>
                    <option value="2">2 - Lista Positiva (valor)</option>
                    <option value="3">3 - Lista Neutra (valor)</option>
                    <option value="4">4 - Margem Valor Agregado (%)</option>
                    <option value="5">5 - Pauta (valor)</option>
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>MVA (%)</label>
                  <input type="number" step="0.01" name="p_mva_st" value={formData.p_mva_st} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>% Redução BC ST</label>
                  <input type="number" step="0.01" name="p_red_bc_st" value={formData.p_red_bc_st} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Alíquota ICMS ST (%)</label>
                  <input type="number" step="0.01" name="p_icms_st" value={formData.p_icms_st} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
              </div>
            </div>
            <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
              <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">FCP — Fundo de Combate à Pobreza</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>% FCP</label>
                  <input type="number" step="0.01" name="p_fcp" value={formData.p_fcp} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>% FCP ST</label>
                  <input type="number" step="0.01" name="p_fcp_st" value={formData.p_fcp_st} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
              </div>
            </div>
            <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
              <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">DIFAL (EC 87/2015)</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>% ICMS UF Destino</label>
                  <input type="number" step="0.01" name="p_icms_uf_dest" value={formData.p_icms_uf_dest} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>% Partilha Interestadual</label>
                  <input type="number" step="0.01" name="p_icms_interpart" value={formData.p_icms_interpart} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>% FCP UF Destino</label>
                  <input type="number" step="0.01" name="p_fcp_uf_dest" value={formData.p_fcp_uf_dest} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Aba IPI / II */}
        {aba === 'ipi' && (
          <div className="flex flex-col gap-6">
            <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
              <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">IPI — Imposto sobre Produtos Industrializados</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>CST IPI</label>
                  <input name="ipi_cst" value={formData.ipi_cst} onChange={handleChange} maxLength={2} placeholder="Ex: 00, 49, 50, 99" className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Alíquota IPI (%)</label>
                  <input type="number" step="0.01" name="ipi_aliquota" value={formData.ipi_aliquota} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>cEnq (Enquadramento)</label>
                  <input name="ipi_cenq" value={formData.ipi_cenq} onChange={handleChange} maxLength={3} placeholder="Ex: 999" className={inputMonoClass} />
                </div>
              </div>
            </div>
            <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
              <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">II — Imposto de Importação</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Alíquota II (%)</label>
                  <input type="number" step="0.01" name="ii_aliquota" value={formData.ii_aliquota} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Aba PIS / COFINS */}
        {aba === 'pis' && (
          <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
            <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">PIS / COFINS (Federal)</h2>
            <p className="text-xs text-muted mb-4">Regime clássico — será gradualmente substituído por CBS a partir de 2027.</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
              <div className="flex flex-col gap-4 border-r border-line pr-4">
                <h3 className="text-sm font-bold text-ink">PIS</h3>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>CST PIS</label>
                  <input name="pis_cst" value={formData.pis_cst} onChange={handleChange} placeholder="Ex: 01, 04, 49, 99" className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Alíquota PIS (%)</label>
                  <input type="number" step="0.01" name="pis_aliquota" value={formData.pis_aliquota} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
              </div>
              <div className="flex flex-col gap-4">
                <h3 className="text-sm font-bold text-ink">COFINS</h3>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>CST COFINS</label>
                  <input name="cofins_cst" value={formData.cofins_cst} onChange={handleChange} placeholder="Ex: 01, 04, 49, 99" className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Alíquota COFINS (%)</label>
                  <input type="number" step="0.01" name="cofins_aliquota" value={formData.cofins_aliquota} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Aba Reforma Tributária */}
        {aba === 'reforma' && (
          <div className="flex flex-col gap-6">
            <div className="bg-i9-tint border border-i9 rounded-DEFAULT p-4 text-sm text-i9 font-semibold">
              Reforma Tributária (LC 214/2025) vigente desde <b>01/08/2026</b>. Configure aqui os
              novos tributos que aparecem no grupo <code>gIBSCBS</code> do layout NF-e/NFC-e.
            </div>

            <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
              <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">CBS — Contribuição sobre Bens e Serviços</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>CST CBS</label>
                  <input name="cbs_cst" value={formData.cbs_cst} onChange={handleChange} maxLength={3} placeholder="Ex: 000 (tributação padrão)" className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>cClassTrib</label>
                  <input name="cbs_cclass_trib" value={formData.cbs_cclass_trib} onChange={handleChange} maxLength={6} placeholder="Ex: 000001" className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Alíquota CBS (%)</label>
                  <input type="number" step="0.01" name="cbs_aliquota" value={formData.cbs_aliquota} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
              </div>
            </div>

            <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
              <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">IBS — Imposto sobre Bens e Serviços</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Alíquota IBS Estadual (%)</label>
                  <input type="number" step="0.01" name="ibs_uf_aliquota" value={formData.ibs_uf_aliquota} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Alíquota IBS Municipal (%)</label>
                  <input type="number" step="0.01" name="ibs_mun_aliquota" value={formData.ibs_mun_aliquota} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
              </div>
            </div>

            <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
              <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">IS — Imposto Seletivo</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>CST IS</label>
                  <input name="is_cst" value={formData.is_cst} onChange={handleChange} maxLength={3} placeholder="Deixe vazio se não aplicável" className={inputMonoClass} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>Alíquota IS (%)</label>
                  <input type="number" step="0.01" name="is_aliquota" value={formData.is_aliquota} onChange={handleNumberChange} className={inputMonoClass} />
                </div>
              </div>
            </div>

            <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
              <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">Regimes Especiais</h2>
              <div className="flex flex-col gap-3">
                <label className="flex items-center gap-2 text-sm font-semibold cursor-pointer">
                  <input type="checkbox" name="regime_monofasico" checked={formData.regime_monofasico} onChange={handleChange} className="w-4 h-4 text-i9 border-line rounded focus:ring-i9" />
                  Regime Monofásico
                </label>
                <label className="flex items-center gap-2 text-sm font-semibold cursor-pointer">
                  <input type="checkbox" name="credito_presumido" checked={formData.credito_presumido} onChange={handleChange} className="w-4 h-4 text-i9 border-line rounded focus:ring-i9" />
                  Crédito Presumido
                </label>
                <label className="flex items-center gap-2 text-sm font-semibold cursor-pointer">
                  <input type="checkbox" name="diferimento" checked={formData.diferimento} onChange={handleChange} className="w-4 h-4 text-i9 border-line rounded focus:ring-i9" />
                  Diferimento
                </label>
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Link to={`/empresas/${id}/regras`} className="px-5 py-2.5 rounded-lg text-sm font-bold text-ink-soft bg-field border border-line hover:bg-line-soft transition-colors">
            Cancelar
          </Link>
          <button type="submit" disabled={salvando} className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-bold text-white bg-gradient-to-b from-i9 to-i9-dark shadow-sm hover:opacity-90 disabled:opacity-50 transition-opacity">
            <Save size={16} />
            {salvando ? 'Salvando...' : 'Salvar Regra'}
          </button>
        </div>
      </form>
    </div>
  );
}
