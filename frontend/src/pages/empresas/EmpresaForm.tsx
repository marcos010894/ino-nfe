import { useState, useEffect } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { ArrowLeft, Save, UploadCloud, Loader2, Zap } from 'lucide-react';

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
    csc_token: '',
    serie_nfe: 1,
    serie_nfce: 1
  });

  const [certFile, setCertFile] = useState<File | null>(null);
  const [certSenha, setCertSenha] = useState('');
  
  const [loading, setLoading] = useState(isEditing);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  // Inutilização de faixa de numeração (Etapa G do MVP).
  // Só faz sentido em modo edição — precisa da empresa já criada.
  const [inutModelo, setInutModelo] = useState<'55' | '65'>('55');
  const [inutIni, setInutIni] = useState<string>('');
  const [inutFin, setInutFin] = useState<string>('');
  const [inutJust, setInutJust] = useState<string>('Correcao de sequencia por gap na numeracao do sistema emissor');
  const [inutLoading, setInutLoading] = useState(false);
  const [inutStatus, setInutStatus] = useState<string>('');

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
        cep: unformat(formData.cep),
        // inputs type=number vêm como string do DOM — coagir pra int aqui.
        serie_nfe: Number(formData.serie_nfe) || 1,
        serie_nfce: Number(formData.serie_nfce) || 1,
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
      if (err.response?.data?.detail) {
        if (Array.isArray(err.response.data.detail)) {
          setErro(err.response.data.detail.map((e: any) => `${e.loc.join('.')}: ${e.msg}`).join(' | '));
        } else {
          setErro(err.response.data.detail);
        }
      } else {
        setErro('Erro ao salvar os dados.');
      }
    } finally {
      setSalvando(false);
    }
  };

  const [sincronizandoAcbr, setSincronizandoAcbr] = useState(false);
  const [acbrStatusMsg, setAcbrStatusMsg] = useState('');

  const handleInutilizar = async () => {
    if (!id) return;
    const ini = Number(inutIni);
    const fin = Number(inutFin);
    if (!Number.isInteger(ini) || !Number.isInteger(fin) || ini < 1 || fin < ini) {
      setInutStatus('Faixa inválida — número final precisa ser ≥ inicial e ambos > 0.');
      return;
    }
    if (inutJust.trim().length < 15) {
      setInutStatus('Justificativa precisa ter no mínimo 15 caracteres.');
      return;
    }
    // SEFAZ limita 999 números por lote — se a faixa for maior, chunk em vários lotes.
    const CHUNK = 999;
    const total = fin - ini + 1;
    const lotes: Array<[number, number]> = [];
    for (let s = ini; s <= fin; s += CHUNK) {
      lotes.push([s, Math.min(s + CHUNK - 1, fin)]);
    }
    if (lotes.length > 5) {
      const ok = window.confirm(
        `Vou fazer ${lotes.length} chamadas SEFAZ (${total} números). Isso pode levar alguns minutos. Continuar?`
      );
      if (!ok) return;
    }

    setInutLoading(true);
    setInutStatus('');
    let sucesso = 0;
    let falha = 0;
    let ultimoErro = '';
    for (let i = 0; i < lotes.length; i++) {
      const [a, b] = lotes[i];
      setInutStatus(`Lote ${i + 1}/${lotes.length}: inutilizando ${a}–${b}...`);
      try {
        await api.post(`/empresas/${id}/notas/inutilizacoes`, {
          modelo: inutModelo,
          serie: inutModelo === '55' ? Number(formData.serie_nfe) || 1 : Number(formData.serie_nfce) || 1,
          numero_inicial: a,
          numero_final: b,
          justificativa: inutJust.trim(),
        });
        sucesso++;
      } catch (err: any) {
        falha++;
        ultimoErro = err?.response?.data?.detail || err?.message || 'erro desconhecido';
      }
    }
    setInutLoading(false);
    setInutStatus(
      falha === 0
        ? `✅ ${sucesso} lote(s) inutilizado(s) — ${total} números.`
        : `⚠️ Concluído com falhas: ${sucesso} ok, ${falha} erro. Último erro: ${ultimoErro}`
    );
  };

  const handleSincronizarAcbr = async () => {
    if (!id) return;
    setSincronizandoAcbr(true);
    setAcbrStatusMsg('');
    try {
      const res = await api.post(`/empresas/${id}/sincronizar-acbr`);
      setFormData(prev => ({
        ...prev,
        ...res.data
      }));
      setAcbrStatusMsg(res.data.acbr_ultimo_status || 'Sincronizado com sucesso com ACBr!');
    } catch (err: any) {
      setAcbrStatusMsg('Erro ao comunicar com a ACBr API.');
    } finally {
      setSincronizandoAcbr(false);
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
            {isEditing ? 'Editar Empresa & Certificado' : 'Nova Empresa'}
          </h1>
          {isEditing && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSincronizarAcbr}
                disabled={sincronizandoAcbr}
                className="bg-blue-500/10 border border-blue-500/30 text-blue-400 font-bold px-3 py-2 rounded-lg text-sm hover:bg-blue-500/20 transition-colors flex items-center gap-1.5"
              >
                {sincronizandoAcbr ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
                Testar & Sincronizar ACBr
              </button>
              <Link 
                to={`/empresas/${id}/regras`}
                className="bg-line-soft border border-line text-ink font-bold px-4 py-2 rounded-lg text-sm hover:bg-i9-tint hover:border-i9 hover:text-i9 transition-colors"
              >
                Ver Regras Fiscais
              </Link>
            </div>
          )}
        </div>
      </div>


      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        {erro && (
          <div className="bg-warn-tint text-warn p-3 rounded-lg text-sm font-semibold border border-[#f0c9c4]">
            {erro}
          </div>
        )}

        {acbrStatusMsg && (
          <div className="bg-blue-500/10 text-blue-400 border border-blue-500/30 p-3 rounded-lg text-sm font-semibold flex items-center gap-2">
            <Zap size={16} />
            {acbrStatusMsg}
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
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold text-muted uppercase">Série NF-e (55)</label>
                  <input
                    name="serie_nfe"
                    type="number"
                    min={1}
                    max={999}
                    value={formData.serie_nfe}
                    onChange={handleChange}
                    className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold text-muted uppercase">Série NFC-e (65)</label>
                  <input
                    name="serie_nfce"
                    type="number"
                    min={1}
                    max={999}
                    value={formData.serie_nfce}
                    onChange={handleChange}
                    className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                  />
                </div>
              </div>
              <div className="text-[11px] text-muted -mt-2">
                Trocar a série reinicia a numeração (nNF) do zero nessa série. Útil para
                abandonar séries com gaps na sequência sem precisar inutilizar cada número.
              </div>
            </div>

            <div className="bg-line-soft p-4 rounded-lg flex flex-col gap-4 relative">
              <div className="text-sm font-bold text-ink flex items-center gap-2">
                <UploadCloud size={18} className="text-i9" /> Certificado A1 (.pfx)
              </div>
              
              {isEditing && (formData as any).has_certificado && (
                <div className="mb-2 p-3 bg-white border border-line rounded-lg text-xs flex flex-col gap-1">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-success">Certificado Ativo</span>
                    { (formData as any).certificado_vencimento && 
                      <span className="text-muted">Vence em: {new Date((formData as any).certificado_vencimento).toLocaleDateString('pt-BR')}</span>
                    }
                  </div>
                  { (formData as any).certificado_emissor && (
                    <span className="text-muted truncate" title={(formData as any).certificado_emissor}>
                      Emissor: {(formData as any).certificado_emissor}
                    </span>
                  )}
                  { (formData as any).certificado_sujeito && (
                    <span className="text-muted truncate" title={(formData as any).certificado_sujeito}>
                      Titular: {(formData as any).certificado_sujeito}
                    </span>
                  )}
                </div>
              )}

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">
                  {(formData as any).has_certificado ? "Substituir Arquivo (.pfx)" : "Arquivo (.pfx ou .p12)"}
                </label>
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

        {/* Bloco: Inutilização de Faixa (Etapa G — só em modo edição) */}
        {isEditing && (
          <div className="bg-card border border-line rounded-DEFAULT shadow p-6">
            <h2 className="text-sm font-bold text-i9 uppercase tracking-wider mb-4 border-b border-line pb-2">
              Inutilizar Faixa de Numeração
            </h2>
            <div className="text-xs text-muted mb-4 leading-relaxed">
              Declara à SEFAZ que uma faixa de números <strong>não foi usada</strong> e
              não será usada. Útil pra fechar buracos na sequência sem trocar de série.
              A SEFAZ limita 999 números por lote — faixas maiores são quebradas
              automaticamente em vários envios.
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">Modelo</label>
                <select
                  value={inutModelo}
                  onChange={(e) => setInutModelo(e.target.value as '55' | '65')}
                  className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                >
                  <option value="55">NF-e (55)</option>
                  <option value="65">NFC-e (65)</option>
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">Número Inicial</label>
                <input
                  type="number"
                  min={1}
                  value={inutIni}
                  onChange={(e) => setInutIni(e.target.value)}
                  className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                  placeholder="Ex: 60"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted uppercase">Número Final</label>
                <input
                  type="number"
                  min={1}
                  value={inutFin}
                  onChange={(e) => setInutFin(e.target.value)}
                  className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                  placeholder="Ex: 70000"
                />
              </div>
              <div className="flex flex-col gap-1.5 justify-end">
                <button
                  type="button"
                  onClick={handleInutilizar}
                  disabled={inutLoading}
                  className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-bold text-white bg-gradient-to-b from-i9 to-i9-dark shadow-sm hover:opacity-90 disabled:opacity-50 transition-opacity"
                >
                  {inutLoading ? <Loader2 size={14} className="animate-spin" /> : null}
                  {inutLoading ? 'Enviando...' : 'Inutilizar Faixa'}
                </button>
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-muted uppercase">Justificativa (mín. 15 caracteres)</label>
              <input
                value={inutJust}
                onChange={(e) => setInutJust(e.target.value)}
                className="bg-field border border-line rounded-lg px-3 py-2 text-sm focus:border-i9 outline-none"
                placeholder="Ex: Correção de sequência por gap na numeração do sistema emissor"
              />
            </div>
            {inutStatus && (
              <div className="mt-3 text-xs px-3 py-2 rounded bg-line-soft text-ink-soft">
                {inutStatus}
              </div>
            )}
          </div>
        )}

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
