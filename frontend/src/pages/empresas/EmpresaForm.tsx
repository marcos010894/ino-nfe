import { useState, useEffect } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { ArrowLeft, Save, UploadCloud, Search, Loader2 } from 'lucide-react';
import api from '../../lib/api';
import { formatCNPJ, formatCEP, unformat } from '../../lib/formatters';

export default function EmpresaForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isEditing = Boolean(id);

  const [formData, setFormData] = useState({
    razao_social: '',
    nome_fantasia: '',
    cnpj: '',
    inscricao_estadual: '',
    cep: '',
    logradouro: '',
    numero: '',
    bairro: '',
    cidade: '',
    uf: '',
    contato_telefone: '',
    contato_email: '',
    regime_tributario: 'Simples Nacional',
    csc_id: '',
    csc_token: ''
  });

  const [certFile, setCertFile] = useState<File | null>(null);
  const [certSenha, setCertSenha] = useState('');
  
  const [loading, setLoading] = useState(isEditing);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  useEffect(() => {
    if (isEditing) {
      api.get('/empresas/')
        .then(res => {
          const emp = res.data.find((e: any) => e.id === Number(id));
          if (emp) {
            setFormData({
              ...formData,
              ...emp,
              csc_token: '' // O token não vem do backend por segurança
            });
          } else {
            navigate('/empresas');
          }
          setLoading(false);
        })
        .catch(() => {
          setErro('Erro ao carregar empresa.');
          setLoading(false);
        });
    }
  }, [id, navigate]);

  const [buscandoCnpj, setBuscandoCnpj] = useState(false);
  const [buscandoCep, setBuscandoCep] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleCnpjChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = formatCNPJ(e.target.value);
    setFormData(prev => ({ ...prev, cnpj: val }));
    
    if (val.length === 18 && !isEditing) {
      buscarCnpj(val);
    }
  };

  const handleCepChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = formatCEP(e.target.value);
    setFormData(prev => ({ ...prev, cep: val }));
    
    if (val.length === 9) {
      buscarCep(val);
    }
  };

  const buscarCnpj = async (cnpjFormatado: string) => {
    const limpo = unformat(cnpjFormatado);
    if (limpo.length !== 14) return;
    
    setBuscandoCnpj(true);
    try {
      const res = await fetch(`https://brasilapi.com.br/api/cnpj/v1/${limpo}`);
      if (res.ok) {
        const data = await res.json();
        setFormData(prev => ({
          ...prev,
          razao_social: data.razao_social || prev.razao_social,
          nome_fantasia: data.nome_fantasia || data.razao_social || prev.nome_fantasia,
          cep: data.cep ? formatCEP(data.cep.toString()) : prev.cep,
          logradouro: data.logradouro || prev.logradouro,
          numero: data.numero || prev.numero,
          bairro: data.bairro || prev.bairro,
          cidade: data.municipio || prev.cidade,
          uf: data.uf || prev.uf
        }));
      }
    } catch (err) {
      console.error('Erro ao buscar CNPJ', err);
    } finally {
      setBuscandoCnpj(false);
    }
  };

  const buscarCep = async (cepFormatado: string) => {
    const limpo = unformat(cepFormatado);
    if (limpo.length !== 8) return;
    
    setBuscandoCep(true);
    try {
      const res = await fetch(`https://viacep.com.br/ws/${limpo}/json/`);
      if (res.ok) {
        const data = await res.json();
        if (!data.erro) {
          setFormData(prev => ({
            ...prev,
            logradouro: data.logradouro || prev.logradouro,
            bairro: data.bairro || prev.bairro,
            cidade: data.localidade || prev.cidade,
            uf: data.uf || prev.uf
          }));
        }
      }
    } catch (err) {
      console.error('Erro ao buscar CEP', err);
    } finally {
      setBuscandoCep(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setCertFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro('');
    setSalvando(true);

    try {
      let empresaId = id;
      
      // 1. Salvar Empresa (limpando máscaras)
      const dataToSave = {
        ...formData,
        cnpj: unformat(formData.cnpj),
        cep: unformat(formData.cep)
      };

      if (isEditing) {
        await api.put(`/empresas/${id}`, dataToSave);
      } else {
        const res = await api.post('/empresas/', dataToSave);
        empresaId = res.data.id;
      }

      // 2. Upload Certificado (se selecionado)
      if (certFile && certSenha && empresaId) {
        const formDataUpload = new FormData();
        formDataUpload.append('file', certFile);
        formDataUpload.append('senha', certSenha);
        
        await api.post(`/empresas/${empresaId}/certificado`, formDataUpload, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
      }

      navigate('/empresas');
    } catch (err: any) {
      setErro(err.response?.data?.detail || 'Erro ao salvar os dados.');
    } finally {
      setSalvando(false);
    }
  };

  if (loading) return <div className="p-8 text-center text-muted font-bold">Carregando...</div>;

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <Link to="/empresas" className="text-muted hover:text-ink transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1 flex items-center justify-between">
          <h1 className="text-2xl font-extrabold tracking-tight">
            {isEditing ? 'Editar Empresa' : 'Nova Empresa'}
          </h1>
          {isEditing && (
            <Link 
              to={`/empresas/${id}/regras`}
              className="bg-line-soft border border-line text-ink font-bold px-4 py-2 rounded-lg text-sm hover:bg-i9-tint hover:border-i9 hover:text-i9 transition-colors"
            >
              Ver Regras Fiscais
            </Link>
          )}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        {erro && (
          <div className="bg-warn-tint text-warn p-3 rounded-lg text-sm font-semibold border border-[#f0c9c4]">
            {erro}
          </div>
        )}

        {/* Bloco: Dados Gerais */}
        <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
          <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">Dados Gerais</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Razão Social *</label>
              <input name="razao_social" value={formData.razao_social} onChange={handleChange} required className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 focus:ring-1 focus:ring-i9 outline-none" />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Nome Fantasia *</label>
              <input name="nome_fantasia" value={formData.nome_fantasia} onChange={handleChange} required className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 focus:ring-1 focus:ring-i9 outline-none" />
            </div>
            <div className="flex flex-col gap-1.5 relative">
              <label className="text-xs font-bold text-muted uppercase">CNPJ *</label>
              <div className="relative">
                <input name="cnpj" value={formData.cnpj} onChange={handleCnpjChange} required className="w-full bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 focus:ring-1 focus:ring-i9 outline-none" placeholder="00.000.000/0000-00" />
                {buscandoCnpj && <Loader2 size={16} className="absolute right-3 top-2.5 text-muted animate-spin" />}
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Inscrição Estadual</label>
              <input name="inscricao_estadual" value={formData.inscricao_estadual} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 focus:ring-1 focus:ring-i9 outline-none" />
            </div>
          </div>
        </div>

        {/* Bloco: Endereço & Contato */}
        <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
          <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">Endereço & Contato</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="flex flex-col gap-1.5 md:col-span-1 relative">
              <label className="text-xs font-bold text-muted uppercase">CEP</label>
              <div className="relative">
                <input name="cep" value={formData.cep} onChange={handleCepChange} className="w-full bg-field border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-i9 outline-none" placeholder="00000-000" />
                {buscandoCep && <Loader2 size={16} className="absolute right-3 top-2.5 text-muted animate-spin" />}
              </div>
            </div>
            <div className="flex flex-col gap-1.5 md:col-span-2">
              <label className="text-xs font-bold text-muted uppercase">Logradouro</label>
              <input name="logradouro" value={formData.logradouro} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none" />
            </div>
            <div className="flex flex-col gap-1.5 md:col-span-1">
              <label className="text-xs font-bold text-muted uppercase">Número</label>
              <input name="numero" value={formData.numero} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none" />
            </div>
            <div className="flex flex-col gap-1.5 md:col-span-2">
              <label className="text-xs font-bold text-muted uppercase">Bairro</label>
              <input name="bairro" value={formData.bairro} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none" />
            </div>
            <div className="flex flex-col gap-1.5 md:col-span-1">
              <label className="text-xs font-bold text-muted uppercase">Cidade</label>
              <input name="cidade" value={formData.cidade} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none" />
            </div>
            <div className="flex flex-col gap-1.5 md:col-span-1">
              <label className="text-xs font-bold text-muted uppercase">UF</label>
              <input name="uf" value={formData.uf} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none" />
            </div>
          </div>
        </div>

        {/* Bloco: Fiscal e Certificado */}
        <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
          <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">Fiscal & Certificado Digital</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">Regime Tributário</label>
                <select name="regime_tributario" value={formData.regime_tributario} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none">
                  <option value="Simples Nacional">Simples Nacional</option>
                  <option value="Lucro Presumido">Lucro Presumido</option>
                  <option value="Lucro Real">Lucro Real</option>
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">CSC ID (NFC-e)</label>
                <input name="csc_id" value={formData.csc_id} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none" placeholder="Ex: 000001" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">CSC Token</label>
                <input name="csc_token" type="password" value={formData.csc_token} onChange={handleChange} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none" placeholder={isEditing ? "(Apenas se quiser alterar)" : "Token SEFAZ"} />
              </div>
            </div>

            <div className="bg-line-soft p-4 rounded-lg flex flex-col gap-4">
              <div className="text-sm font-bold text-ink flex items-center gap-2"><UploadCloud size={18} className="text-i9" /> Upload Certificado A1 (.pfx)</div>
              
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">Arquivo (.pfx ou .p12)</label>
                <input type="file" accept=".pfx,.p12" onChange={handleFileChange} className="text-sm file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-i9-tint file:text-i9 hover:file:bg-i9 hover:file:text-white transition-colors cursor-pointer" />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">Senha do Certificado</label>
                <input type="password" value={certSenha} onChange={(e) => setCertSenha(e.target.value)} className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none" placeholder={certFile ? "Senha obrigatória para upload" : "Senha"} required={!!certFile} />
                <span className="text-[10px] text-muted leading-tight mt-1">A senha é armazenada de forma segura com criptografia de ponta a ponta.</span>
              </div>
            </div>

          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Link to="/empresas" className="px-5 py-2.5 rounded-lg text-sm font-bold text-ink-soft bg-field border border-line hover:bg-line-soft transition-colors">
            Cancelar
          </Link>
          <button type="submit" disabled={salvando} className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-bold text-white bg-gradient-to-b from-i9 to-i9-dark shadow-sm hover:opacity-90 disabled:opacity-50 transition-opacity">
            <Save size={16} />
            {salvando ? 'Salvando...' : 'Salvar Empresa'}
          </button>
        </div>
      </form>
    </div>
  );
}
