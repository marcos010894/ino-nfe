import { useState, useEffect } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { ArrowLeft, Save, Trash2 } from 'lucide-react';
import api from '../../lib/api';

export default function RegraFiscalForm() {
  const { id, regraId } = useParams(); // id = empresa_id
  const navigate = useNavigate();
  const isEditing = Boolean(regraId);

  const [formData, setFormData] = useState({
    nome: '',
    cfop: '',
    ncm_padrao: '',
    origem_icms: '0',
    cst_csosn: '',
    icms_aliquota: 0,
    pis_cst: '01',
    pis_aliquota: 0,
    cofins_cst: '01',
    cofins_aliquota: 0,
    padrao: false
  });

  const [loading, setLoading] = useState(isEditing);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  useEffect(() => {
    if (isEditing) {
      api.get(`/empresas/${id}/regras/`)
        .then(res => {
          const regra = res.data.find((r: any) => r.id === Number(regraId));
          if (regra) {
            setFormData(regra);
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
  }, [id, regraId, navigate]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      setFormData({ ...formData, [name]: (e.target as HTMLInputElement).checked });
    } else {
      setFormData({ ...formData, [name]: value });
    }
  };

  const handleNumberChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: parseFloat(e.target.value) || 0 });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro('');

    // Validações Básicas
    if (formData.cfop.length !== 4) {
      setErro('O CFOP deve ter exatamente 4 dígitos.');
      return;
    }
    if (formData.ncm_padrao.length !== 8) {
      setErro('O NCM deve ter exatamente 8 dígitos.');
      return;
    }

    setSalvando(true);
    try {
      if (isEditing) {
        await api.put(`/empresas/${id}/regras/${regraId}`, formData);
      } else {
        await api.post(`/empresas/${id}/regras/`, formData);
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
    } catch (err) {
      setErro('Erro ao excluir regra fiscal.');
    }
  };

  if (loading) return <div className="p-8 text-center text-muted font-bold">Carregando...</div>;

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

        {/* Informações Básicas */}
        <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
          <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">Informações Base</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5 md:col-span-2">
              <label className="text-xs font-bold text-muted uppercase">Nome da Regra *</label>
              <input name="nome" value={formData.nome} onChange={handleChange} required placeholder="Ex: Venda dentro do Estado (Simples)" className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none" />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">CFOP *</label>
              <input name="cfop" value={formData.cfop} onChange={handleChange} required minLength={4} maxLength={4} placeholder="Ex: 5102" className="bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 outline-none" />
              <span className="text-[10px] text-muted">Apenas números (4 dígitos)</span>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">NCM Padrão *</label>
              <input name="ncm_padrao" value={formData.ncm_padrao} onChange={handleChange} required minLength={8} maxLength={8} placeholder="Ex: 71131900" className="bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 outline-none" />
              <span className="text-[10px] text-muted">Apenas números (8 dígitos)</span>
            </div>
            
            <div className="flex items-center gap-2 mt-2 md:col-span-2 bg-line-soft p-3 rounded-lg border border-line">
              <input type="checkbox" id="padrao" name="padrao" checked={formData.padrao} onChange={handleChange} className="w-4 h-4 text-i9 border-line rounded focus:ring-i9" />
              <label htmlFor="padrao" className="text-sm font-bold text-ink cursor-pointer">Definir como Regra Padrão do Sistema</label>
            </div>
          </div>
        </div>

        {/* ICMS */}
        <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
          <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">ICMS (Estadual)</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Origem da Mercadoria</label>
              <select name="origem_icms" value={formData.origem_icms} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none">
                <option value="0">0 - Nacional</option>
                <option value="1">1 - Estrangeira (Importação direta)</option>
                <option value="2">2 - Estrangeira (Adquirida no mercado interno)</option>
                {/* ... omitindo outras para MVP ... */}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">CST ou CSOSN *</label>
              <input name="cst_csosn" value={formData.cst_csosn} onChange={handleChange} required placeholder="Ex: 102 ou 00" className="bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 outline-none" />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Alíquota ICMS (%)</label>
              <input type="number" step="0.01" name="icms_aliquota" value={formData.icms_aliquota} onChange={handleNumberChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 outline-none" />
            </div>
          </div>
        </div>

        {/* PIS / COFINS */}
        <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
          <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">PIS / COFINS (Federal)</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
            
            {/* PIS */}
            <div className="flex flex-col gap-4 border-r border-line pr-4">
              <h3 className="text-sm font-bold text-ink">PIS</h3>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">CST PIS</label>
                <input name="pis_cst" value={formData.pis_cst} onChange={handleChange} placeholder="Ex: 01 ou 49" className="bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 outline-none" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">Alíquota PIS (%)</label>
                <input type="number" step="0.01" name="pis_aliquota" value={formData.pis_aliquota} onChange={handleNumberChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 outline-none" />
              </div>
            </div>

            {/* COFINS */}
            <div className="flex flex-col gap-4">
              <h3 className="text-sm font-bold text-ink">COFINS</h3>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">CST COFINS</label>
                <input name="cofins_cst" value={formData.cofins_cst} onChange={handleChange} placeholder="Ex: 01 ou 49" className="bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 outline-none" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">Alíquota COFINS (%)</label>
                <input type="number" step="0.01" name="cofins_aliquota" value={formData.cofins_aliquota} onChange={handleNumberChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 outline-none" />
              </div>
            </div>

          </div>
        </div>

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
