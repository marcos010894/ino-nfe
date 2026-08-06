import asyncio
import httpx
import logging
from datetime import datetime, timedelta, timezone
import uuid
import random
from typing import Dict, Any, Tuple, Optional, Union
from app.core.config import settings
from app.models.empresa import Empresa
from app.models.regra_fiscal import RegraFiscal

logger = logging.getLogger(__name__)

# Cache do access_token ACBr por (client_id, env). Compartilhado entre
# instâncias porque ACBrAPIService é instanciado por request. Sem cache,
# o Keycloak devolve 429 Too Many Requests durante emissão + polling.
_TOKEN_CACHE: Dict[Tuple[str, str], Tuple[str, datetime]] = {}
_TOKEN_LOCK = asyncio.Lock()


def _r(valor: float) -> float:
    """Arredondamento fiscal padrão."""
    return round(float(valor or 0.0), 2)


class ACBrAPIService:
    def __init__(self):
        self.client_id = settings.acbr_api_client_id
        self.client_secret = settings.acbr_api_client_secret
        self.env = settings.acbr_api_env

        # URL do provedor de autenticação (Keycloak do ACBr)
        self.auth_url = "https://auth.acbr.api.br/realms/ACBrAPI/protocol/openid-connect/token"

        # URL base dependendo do ambiente
        if self.env == "producao":
            self.base_url = "https://prod.acbr.api.br"
        else:
            self.base_url = "https://hom.acbr.api.br"

    # Escopos padrão exigidos pelo Keycloak da ACBr. Sem isso o JWT vem com
    # scope vazio e todo endpoint retorna InsufficientPermissions, mesmo que
    # as permissões estejam atribuídas no painel.
    OAUTH_SCOPES = "empresa nfce nfe cnpj cep conta"

    async def _get_access_token(self) -> str:
        """Obtém o Token de Acesso via OAuth2 (client_credentials) com cache em memória.

        O Keycloak da ACBr aplica rate-limit no /token e devolve 429 se o
        backend chamar login a cada request. Reusamos o token até 30s antes
        do vencimento; o cache é global (chave = client_id+env)."""
        cache_key = (self.client_id, self.env)
        cached = _TOKEN_CACHE.get(cache_key)
        now = datetime.utcnow()
        if cached and cached[1] > now:
            return cached[0]

        async with _TOKEN_LOCK:
            # revalida sob lock (outra corrotina pode ter renovado enquanto esperávamos)
            cached = _TOKEN_CACHE.get(cache_key)
            if cached and cached[1] > now:
                return cached[0]

            async with httpx.AsyncClient() as client:
                data = {
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": self.OAUTH_SCOPES,
                }
                response = await client.post(self.auth_url, data=data, timeout=10.0)
                if response.status_code != 200:
                    logger.error(f"Erro na autenticação ACBr API ({response.status_code}): {response.text}")
                    raise Exception(
                        f"Falha na autenticação ACBr API ({response.status_code}): {response.text}"
                    )
                res_data = response.json()
                token = res_data["access_token"]
                expires_in = int(res_data.get("expires_in") or 300)
                # renova 30s antes de expirar de fato
                expires_at = now + timedelta(seconds=max(expires_in - 30, 30))
                _TOKEN_CACHE[cache_key] = (token, expires_at)
                return token

    # ------------------------------------------------------------------
    # Health-check
    # ------------------------------------------------------------------
    async def testar_conexao(self) -> Tuple[bool, Dict[str, Any]]:
        """Handshake real com a ACBr API. Não usa fallback."""
        info: Dict[str, Any] = {
            "env": self.env,
            "base_url": self.base_url,
            "auth_url": self.auth_url,
        }
        try:
            token = await self._get_access_token()
        except Exception as e:
            return False, {**info, "etapa": "auth", "erro": str(e)}

        info["token_ok"] = True

        # Ping em endpoint autenticado. Usamos /empresas (lista) — se retorna 200
        # ou 401/403 sabemos que o servidor está no ar; 5xx/timeout = falha real.
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{self.base_url}/empresas", headers=headers, timeout=10.0)
                info["endpoint_status_code"] = r.status_code
                if r.status_code >= 500:
                    return False, {**info, "etapa": "endpoint", "erro": r.text}
                return True, info
        except Exception as e:
            return False, {**info, "etapa": "endpoint", "erro": str(e)}

    # ------------------------------------------------------------------
    # Sincronização e certificado
    # ------------------------------------------------------------------
    async def sincronizar_empresa_acbr(self, empresa: Empresa) -> Tuple[bool, Dict[str, Any]]:
        """Sincroniza dados cadastrais da empresa com a ACBr API.

        Formato do payload conforme DTO `Empresa.DTO.TEmpresa` da ACBr:
          - cpf_cnpj, nome_razao_social, nome_fantasia, email
          - endereco: logradouro, numero, bairro, cep, codigo_municipio (IBGE), uf
        Faz POST para criar; se retornar 409/duplicado, cai em PUT para atualizar.
        """
        try:
            token = await self._get_access_token()
        except Exception as e:
            return False, {"erro": f"Falha de autenticação ACBr: {e}"}

        cnpj_limpo = "".join(filter(str.isdigit, empresa.cnpj))

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Campos obrigatórios pela ACBr — precisam existir sempre
        email = empresa.contato_email or f"sem-email-{cnpj_limpo}@innofiscal.local"
        codigo_municipio = empresa.codigo_municipio or "3550308"  # fallback São Paulo

        payload = {
            "cpf_cnpj": cnpj_limpo,
            "nome_razao_social": empresa.razao_social,
            "nome_fantasia": empresa.nome_fantasia or empresa.razao_social,
            "email": email,
            "endereco": {
                "logradouro": empresa.logradouro or "NAO INFORMADO",
                "numero": empresa.numero or "SN",
                "bairro": empresa.bairro or "CENTRO",
                "cep": "".join(filter(str.isdigit, empresa.cep or "01001000")),
                "codigo_municipio": codigo_municipio,
                "uf": (empresa.uf or "SP").upper(),
            },
        }

        create_url = f"{self.base_url}/empresas"
        update_url = f"{self.base_url}/empresas/{cnpj_limpo}"

        # 1) tenta POST /empresas (criar)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(create_url, json=payload, headers=headers, timeout=15.0)
        except Exception as e:
            logger.error(f"Erro de comunicação ao criar empresa ACBr: {e}")
            return False, {"erro": str(e)}

        if response.status_code in (200, 201):
            return True, response.json()

        # 2) se já existe (409 ou mensagem específica), faz PUT (atualizar)
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}
        code = (body.get("error") or {}).get("code", "")
        if response.status_code == 409 or code in ("EmpresaAlreadyExists", "DuplicateResource"):
            try:
                async with httpx.AsyncClient() as client:
                    r2 = await client.put(update_url, json=payload, headers=headers, timeout=15.0)
                if r2.status_code in (200, 201):
                    return True, r2.json()
                try:
                    body2 = r2.json()
                except Exception:
                    body2 = {"raw": r2.text}
                logger.warning(f"PUT /empresas ACBr falhou ({r2.status_code}): {r2.text}")
                return False, {"status_code": r2.status_code, **body2}
            except Exception as e:
                logger.error(f"Erro de comunicação no PUT empresa ACBr: {e}")
                return False, {"erro": str(e)}

        logger.warning(f"Sincronização cadastral ACBr falhou ({response.status_code}): {response.text}")
        return False, {"status_code": response.status_code, **body}

    async def enviar_certificado_acbr(
        self, empresa: Empresa, certificado_base64: str, senha: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """Envia e vincula o Certificado Digital A1 da empresa na ACBr API.

        Método: PUT /empresas/{cnpj}/certificado
        Payload esperado: {"certificado": <base64>, "password": <senha>}
        """
        try:
            token = await self._get_access_token()
        except Exception as e:
            return False, {"erro": f"Falha de autenticação ACBr: {e}"}

        cnpj_limpo = "".join(filter(str.isdigit, empresa.cnpj))
        url = f"{self.base_url}/empresas/{cnpj_limpo}/certificado"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        payload = {
            "certificado": certificado_base64,
            "password": senha,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(url, json=payload, headers=headers, timeout=20.0)
        except Exception as e:
            logger.error(f"Erro de comunicação ao enviar certificado ACBr: {e}")
            return False, {"erro": str(e)}

        if response.status_code in (200, 201):
            return True, response.json()

        logger.warning(f"Upload de certificado ACBr falhou ({response.status_code}): {response.text}")
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}
        return False, {"status_code": response.status_code, **body}

    # ------------------------------------------------------------------
    # Resolvers de tributos por CST / CSOSN
    # ------------------------------------------------------------------
    def _resolver_icms(self, regra: RegraFiscal, valor_item: float) -> Dict[str, Any]:
        """Resolve a estrutura do ICMS conforme o CST ou CSOSN da regra."""
        cst_csosn = (regra.cst_csosn or "").strip()
        origem = int(regra.origem_icms or "0")
        aliquota = float(regra.icms_aliquota or 0.0)
        mod_bc = int(regra.mod_bc) if regra.mod_bc not in (None, "") else 3
        p_red_bc = float(regra.p_red_bc or 0.0)
        p_fcp = float(regra.p_fcp or 0.0)
        p_mva = float(regra.p_mva_st or 0.0)
        p_red_bc_st = float(regra.p_red_bc_st or 0.0)
        p_icms_st = float(regra.p_icms_st or 0.0)
        p_fcp_st = float(regra.p_fcp_st or 0.0)
        mod_bc_st = int(regra.mod_bc_st) if regra.mod_bc_st not in (None, "") else 4
        v_icms_deson = float(regra.v_icms_deson or 0.0)
        mot_des = regra.mot_des_icms

        base_icms = _r(valor_item * (1 - p_red_bc / 100.0)) if p_red_bc else _r(valor_item)
        v_icms = _r(base_icms * (aliquota / 100.0))

        base_st = _r(valor_item * (1 + p_mva / 100.0) * (1 - p_red_bc_st / 100.0))
        v_icms_st_bruto = _r(base_st * (p_icms_st / 100.0))
        v_icms_st = _r(max(0.0, v_icms_st_bruto - v_icms))

        v_fcp = _r(base_icms * (p_fcp / 100.0)) if p_fcp else 0.0
        v_fcp_st = _r(base_st * (p_fcp_st / 100.0)) if p_fcp_st else 0.0

        # Simples Nacional (CSOSN 3 dígitos)
        if len(cst_csosn) == 3:
            if cst_csosn == "101":
                return {"ICMSSN101": {
                    "orig": origem, "CSOSN": cst_csosn,
                    "pCredSN": aliquota, "vCredICMSSN": v_icms,
                }}
            if cst_csosn in ("102", "103", "300", "400"):
                return {"ICMSSN102": {"orig": origem, "CSOSN": cst_csosn}}
            if cst_csosn in ("201", "202", "203"):
                grp = "ICMSSN201" if cst_csosn == "201" else "ICMSSN202"
                inner = {
                    "orig": origem, "CSOSN": cst_csosn,
                    "modBCST": mod_bc_st, "pMVAST": p_mva,
                    "pRedBCST": p_red_bc_st, "vBCST": base_st,
                    "pICMSST": p_icms_st, "vICMSST": v_icms_st_bruto,
                }
                if cst_csosn == "201":
                    inner["pCredSN"] = aliquota
                    inner["vCredICMSSN"] = v_icms
                return {grp: inner}
            if cst_csosn == "500":
                return {"ICMSSN500": {"orig": origem, "CSOSN": cst_csosn}}
            if cst_csosn == "900":
                return {"ICMSSN900": {
                    "orig": origem, "CSOSN": cst_csosn,
                    "modBC": mod_bc, "vBC": base_icms, "pICMS": aliquota, "vICMS": v_icms,
                    "modBCST": mod_bc_st, "pMVAST": p_mva, "pRedBCST": p_red_bc_st,
                    "vBCST": base_st, "pICMSST": p_icms_st, "vICMSST": v_icms_st_bruto,
                    "pCredSN": aliquota, "vCredICMSSN": v_icms,
                }}
            # fallback Simples
            return {"ICMSSN102": {"orig": origem, "CSOSN": cst_csosn}}

        # Regime normal (CST 2 dígitos)
        if cst_csosn == "00":
            return {"ICMS00": {
                "orig": origem, "CST": cst_csosn,
                "modBC": mod_bc, "vBC": base_icms, "pICMS": aliquota, "vICMS": v_icms,
                "pFCP": p_fcp, "vFCP": v_fcp,
            }}
        if cst_csosn == "10":
            return {"ICMS10": {
                "orig": origem, "CST": cst_csosn,
                "modBC": mod_bc, "vBC": base_icms, "pICMS": aliquota, "vICMS": v_icms,
                "modBCST": mod_bc_st, "pMVAST": p_mva, "pRedBCST": p_red_bc_st,
                "vBCST": base_st, "pICMSST": p_icms_st, "vICMSST": v_icms_st,
                "pFCP": p_fcp, "vFCP": v_fcp, "pFCPST": p_fcp_st, "vFCPST": v_fcp_st,
            }}
        if cst_csosn == "20":
            return {"ICMS20": {
                "orig": origem, "CST": cst_csosn,
                "modBC": mod_bc, "pRedBC": p_red_bc,
                "vBC": base_icms, "pICMS": aliquota, "vICMS": v_icms,
                "vICMSDeson": v_icms_deson, "motDesICMS": mot_des,
                "pFCP": p_fcp, "vFCP": v_fcp,
            }}
        if cst_csosn == "30":
            return {"ICMS30": {
                "orig": origem, "CST": cst_csosn,
                "modBCST": mod_bc_st, "pMVAST": p_mva, "pRedBCST": p_red_bc_st,
                "vBCST": base_st, "pICMSST": p_icms_st, "vICMSST": v_icms_st_bruto,
                "vICMSDeson": v_icms_deson, "motDesICMS": mot_des,
            }}
        if cst_csosn in ("40", "41", "50"):
            inner = {"orig": origem, "CST": cst_csosn}
            if v_icms_deson:
                inner["vICMSDeson"] = v_icms_deson
                inner["motDesICMS"] = mot_des
            return {"ICMS40": inner}
        if cst_csosn == "51":
            return {"ICMS51": {
                "orig": origem, "CST": cst_csosn,
                "modBC": mod_bc, "vBC": base_icms, "pICMS": aliquota, "vICMS": v_icms,
            }}
        if cst_csosn == "60":
            return {"ICMS60": {
                "orig": origem, "CST": cst_csosn,
                "vBCSTRet": base_st, "vICMSSTRet": v_icms_st_bruto,
                "pFCPSTRet": p_fcp_st, "vFCPSTRet": v_fcp_st,
            }}
        if cst_csosn == "70":
            return {"ICMS70": {
                "orig": origem, "CST": cst_csosn,
                "modBC": mod_bc, "pRedBC": p_red_bc,
                "vBC": base_icms, "pICMS": aliquota, "vICMS": v_icms,
                "modBCST": mod_bc_st, "pMVAST": p_mva, "pRedBCST": p_red_bc_st,
                "vBCST": base_st, "pICMSST": p_icms_st, "vICMSST": v_icms_st,
                "vICMSDeson": v_icms_deson, "motDesICMS": mot_des,
            }}
        if cst_csosn == "90":
            return {"ICMS90": {
                "orig": origem, "CST": cst_csosn,
                "modBC": mod_bc, "vBC": base_icms, "pRedBC": p_red_bc,
                "pICMS": aliquota, "vICMS": v_icms,
                "modBCST": mod_bc_st, "pMVAST": p_mva, "pRedBCST": p_red_bc_st,
                "vBCST": base_st, "pICMSST": p_icms_st, "vICMSST": v_icms_st,
                "vICMSDeson": v_icms_deson, "motDesICMS": mot_des,
            }}
        # fallback conservador
        return {"ICMS40": {"orig": origem, "CST": cst_csosn or "40"}}

    def _resolver_pis(self, cst: str, aliquota: float, valor_item: float) -> Dict[str, Any]:
        """Resolve a estrutura do PIS conforme o CST."""
        cst = (cst or "").strip()
        if cst in ("01", "02"):
            v_pis = _r(valor_item * (aliquota / 100.0))
            return {"PISAliq": {"CST": cst, "vBC": _r(valor_item), "pPIS": aliquota, "vPIS": v_pis}}
        if cst == "03":
            return {"PISQtde": {"CST": cst, "qBCProd": 0.0, "vAliqProd": aliquota, "vPIS": 0.0}}
        if cst in ("04", "05", "06", "07", "08", "09"):
            return {"PISNT": {"CST": cst}}
        if cst in ("49", "50", "51", "52", "53", "54", "55", "56",
                   "60", "61", "62", "63", "64", "65", "66", "67",
                   "70", "71", "72", "73", "74", "75", "98", "99"):
            v_pis = _r(valor_item * (aliquota / 100.0))
            return {"PISOutr": {"CST": cst, "vBC": _r(valor_item), "pPIS": aliquota, "vPIS": v_pis}}
        return {"PISNT": {"CST": cst or "07"}}

    def _resolver_cofins(self, cst: str, aliquota: float, valor_item: float) -> Dict[str, Any]:
        """Resolve a estrutura do COFINS conforme o CST."""
        cst = (cst or "").strip()
        if cst in ("01", "02"):
            v_cof = _r(valor_item * (aliquota / 100.0))
            return {"COFINSAliq": {"CST": cst, "vBC": _r(valor_item), "pCOFINS": aliquota, "vCOFINS": v_cof}}
        if cst == "03":
            return {"COFINSQtde": {"CST": cst, "qBCProd": 0.0, "vAliqProd": aliquota, "vCOFINS": 0.0}}
        if cst in ("04", "05", "06", "07", "08", "09"):
            return {"COFINSNT": {"CST": cst}}
        if cst in ("49", "50", "51", "52", "53", "54", "55", "56",
                   "60", "61", "62", "63", "64", "65", "66", "67",
                   "70", "71", "72", "73", "74", "75", "98", "99"):
            v_cof = _r(valor_item * (aliquota / 100.0))
            return {"COFINSOutr": {"CST": cst, "vBC": _r(valor_item), "pCOFINS": aliquota, "vCOFINS": v_cof}}
        return {"COFINSNT": {"CST": cst or "07"}}

    def _resolver_ipi(self, regra: RegraFiscal, valor_item: float) -> Optional[Dict[str, Any]]:
        """Resolve a estrutura do IPI. Retorna None se a regra não configurou IPI."""
        cst = (regra.ipi_cst or "").strip()
        if not cst:
            return None
        aliquota = float(regra.ipi_aliquota or 0.0)
        cenq = regra.ipi_cenq or "999"
        # CSTs tributados: 00, 49, 50, 99
        if cst in ("00", "49", "50", "99"):
            v_ipi = _r(valor_item * (aliquota / 100.0))
            return {"cEnq": cenq, "IPITrib": {"CST": cst, "vBC": _r(valor_item), "pIPI": aliquota, "vIPI": v_ipi}}
        # Demais CSTs = não tributado
        return {"cEnq": cenq, "IPINT": {"CST": cst}}

    def _resolver_ii(self, regra: RegraFiscal, valor_item: float) -> Optional[Dict[str, Any]]:
        """Resolve o II — retorna None se não houver alíquota configurada."""
        if not regra.ii_aliquota:
            return None
        v_ii = _r(valor_item * (float(regra.ii_aliquota) / 100.0))
        return {"vBC": _r(valor_item), "vDespAdu": 0.0, "vII": v_ii, "vIOF": 0.0}

    def _resolver_ibs_cbs(self, regra: RegraFiscal, valor_item: float) -> Optional[Dict[str, Any]]:
        """Grupo gIBSCBS da Reforma Tributária (vigente desde 2026-08-01)."""
        cst = (regra.cbs_cst or "").strip()
        cclass = regra.cbs_cclass_trib
        p_cbs = float(regra.cbs_aliquota or 0.0)
        p_ibs_uf = float(regra.ibs_uf_aliquota or 0.0)
        p_ibs_mun = float(regra.ibs_mun_aliquota or 0.0)

        # Se nenhum campo da Reforma foi configurado, omite o grupo
        if not cst and p_cbs == 0.0 and p_ibs_uf == 0.0 and p_ibs_mun == 0.0:
            return None

        base = _r(valor_item)
        v_cbs = _r(base * (p_cbs / 100.0))
        v_ibs_uf = _r(base * (p_ibs_uf / 100.0))
        v_ibs_mun = _r(base * (p_ibs_mun / 100.0))

        grp: Dict[str, Any] = {
            "CST": cst or "000",
            "cClassTrib": cclass or "000000",
            "vBC": base,
            "gIBSUF": {"pIBSUF": p_ibs_uf, "vIBSUF": v_ibs_uf},
            "gIBSMun": {"pIBSMun": p_ibs_mun, "vIBSMun": v_ibs_mun},
            "gCBS": {"pCBS": p_cbs, "vCBS": v_cbs},
        }
        if regra.regime_monofasico:
            grp["gIBSCBSMono"] = {"pRFBCBS": p_cbs, "vRFBCBS": v_cbs}
        if regra.credito_presumido:
            grp["gIBSCredPres"] = {"cCredPres": "01", "pCredPres": 0.0, "vCredPres": 0.0}
        if regra.diferimento:
            grp["gIBSCBSDif"] = {"cBenefDif": "0", "pDif": 100.0, "vDif": v_cbs + v_ibs_uf + v_ibs_mun}
        return grp

    def _resolver_is(self, regra: RegraFiscal, valor_item: float) -> Optional[Dict[str, Any]]:
        """Imposto Seletivo (IS). Omitido se não configurado."""
        cst = (regra.is_cst or "").strip()
        aliquota = float(regra.is_aliquota or 0.0)
        if not cst and aliquota == 0.0:
            return None
        base = _r(valor_item)
        v_is = _r(base * (aliquota / 100.0))
        return {"CST": cst or "000", "vBC": base, "pIS": aliquota, "vIS": v_is}

    # ------------------------------------------------------------------
    # Montagem do payload NF-e / NFC-e
    # ------------------------------------------------------------------
    def montar_payload_nfce(
        self,
        empresa: Empresa,
        regra: RegraFiscal,
        venda: Dict[str, Any],
        modelo: int = 65,
        numero: Optional[int] = None,
        serie: int = 1,
    ) -> Dict[str, Any]:
        """Gera o payload compatível com NfePedidoEmissao da ACBr API."""
        itens_venda = venda.get("itens", [])
        pagamentos = venda.get("pagamentos", [])

        v_prod = sum(
            float(item.get("quantidade", 0)) * float(item.get("valor_unitario", 0))
            for item in itens_venda
        )
        v_desc = float(venda.get("desconto", 0.0))
        v_nf_base = _r(v_prod - v_desc)

        # Rateio do desconto total entre os itens (proporcional ao vProd).
        # A SEFAZ rejeita (cStat 537) se sum(item.vDesc) != total.vDesc.
        # Último item recebe o resíduo para fechar centavos exatos.
        descontos_item: Dict[int, float] = {}
        if v_desc > 0 and v_prod > 0 and itens_venda:
            alocado = 0.0
            n = len(itens_venda)
            for idx, item in enumerate(itens_venda, start=1):
                v_item = float(item.get("quantidade", 0)) * float(item.get("valor_unitario", 0))
                if idx == n:
                    descontos_item[idx] = _r(v_desc - alocado)
                else:
                    d = _r((v_item / v_prod) * v_desc)
                    descontos_item[idx] = d
                    alocado += d

        c_nf = str(random.randint(10000000, 99999999))

        # Acumuladores de totais
        tot_v_bc = 0.0
        tot_v_icms = 0.0
        tot_v_icms_deson = 0.0
        tot_v_fcp = 0.0
        tot_v_bc_st = 0.0
        tot_v_st = 0.0
        tot_v_fcp_st = 0.0
        tot_v_pis = 0.0
        tot_v_cofins = 0.0
        tot_v_ipi = 0.0
        tot_v_ii = 0.0
        tot_v_cbs = 0.0
        tot_v_ibs_uf = 0.0
        tot_v_ibs_mun = 0.0
        tot_v_is = 0.0

        det = []
        for i, item in enumerate(itens_venda, start=1):
            qtd = float(item.get("quantidade", 1.0))
            v_un = float(item.get("valor_unitario", 0.0))
            v_item_prod = _r(qtd * v_un)

            ncm = item.get("ncm", regra.ncm_padrao)
            ncm = "".join(filter(str.isdigit, ncm))[:8]
            cfop = "".join(filter(str.isdigit, regra.cfop))[:4]

            prod: Dict[str, Any] = {
                "cProd": item.get("codigo", f"PROD{i}"),
                "cEAN": "SEM GTIN",
                "cEANTrib": "SEM GTIN",
                "xProd": item.get("nome", "Item sem Nome").upper(),
                "NCM": ncm,
                "CFOP": cfop,
                "uCom": item.get("unidade", "UN").upper(),
                "qCom": qtd,
                "vUnCom": v_un,
                "vProd": v_item_prod,
                "uTrib": item.get("unidade", "UN").upper(),
                "qTrib": qtd,
                "vUnTrib": v_un,
                "indTot": 1,
            }
            if regra.cest:
                prod["CEST"] = "".join(filter(str.isdigit, regra.cest))[:7]

            if i in descontos_item and descontos_item[i] > 0:
                prod["vDesc"] = descontos_item[i]

            icms_group = self._resolver_icms(regra, v_item_prod)
            pis_group = self._resolver_pis(regra.pis_cst, float(regra.pis_aliquota or 0.0), v_item_prod)
            cofins_group = self._resolver_cofins(regra.cofins_cst, float(regra.cofins_aliquota or 0.0), v_item_prod)

            imposto: Dict[str, Any] = {
                "vTotTrib": _r(v_item_prod * 0.15),
                "ICMS": icms_group,
                "PIS": pis_group,
                "COFINS": cofins_group,
            }
            ipi = self._resolver_ipi(regra, v_item_prod)
            if ipi:
                imposto["IPI"] = ipi
            ii = self._resolver_ii(regra, v_item_prod)
            if ii:
                imposto["II"] = ii
            ibscbs = self._resolver_ibs_cbs(regra, v_item_prod)
            if ibscbs:
                imposto["IBSCBS"] = ibscbs
            is_grp = self._resolver_is(regra, v_item_prod)
            if is_grp:
                imposto["IS"] = is_grp

            det_item: Dict[str, Any] = {"nItem": i, "prod": prod, "imposto": imposto}
            if regra.cbenef:
                det_item["prod"]["cBenef"] = regra.cbenef
            det.append(det_item)

            # Somas para totais
            inner = next(iter(icms_group.values()))
            tot_v_bc += float(inner.get("vBC", 0.0) or 0.0)
            tot_v_icms += float(inner.get("vICMS", 0.0) or 0.0)
            tot_v_icms_deson += float(inner.get("vICMSDeson", 0.0) or 0.0)
            tot_v_fcp += float(inner.get("vFCP", 0.0) or 0.0)
            tot_v_bc_st += float(inner.get("vBCST", 0.0) or 0.0)
            tot_v_st += float(inner.get("vICMSST", 0.0) or 0.0)
            tot_v_fcp_st += float(inner.get("vFCPST", 0.0) or 0.0)

            for key in ("PISAliq", "PISOutr", "PISQtde"):
                if key in pis_group:
                    tot_v_pis += float(pis_group[key].get("vPIS", 0.0) or 0.0)
            for key in ("COFINSAliq", "COFINSOutr", "COFINSQtde"):
                if key in cofins_group:
                    tot_v_cofins += float(cofins_group[key].get("vCOFINS", 0.0) or 0.0)

            if ipi:
                if "IPITrib" in ipi:
                    tot_v_ipi += float(ipi["IPITrib"].get("vIPI", 0.0) or 0.0)
            if ii:
                tot_v_ii += float(ii.get("vII", 0.0) or 0.0)
            if ibscbs:
                tot_v_cbs += float(ibscbs.get("gCBS", {}).get("vCBS", 0.0) or 0.0)
                tot_v_ibs_uf += float(ibscbs.get("gIBSUF", {}).get("vIBSUF", 0.0) or 0.0)
                tot_v_ibs_mun += float(ibscbs.get("gIBSMun", {}).get("vIBSMun", 0.0) or 0.0)
            if is_grp:
                tot_v_is += float(is_grp.get("vIS", 0.0) or 0.0)

        # Pagamentos
        # SEFAZ exige subgrupo `card` (com tpIntegra) para tPag 03 (cartao credito),
        # 04 (cartao debito) e 17 (PIX). Sem ele: rejeicao cStat 391.
        # tpIntegra=2 = "Pagamento nao integrado com o sistema de automacao da empresa".
        _TPAG_EXIGE_CARD = {"03", "04", "17"}
        det_pag = []
        for pag in pagamentos:
            tpag = pag.get("meio_pagamento", "01")
            item = {
                "indPag": 0,
                "tPag": tpag,
                "vPag": float(pag.get("valor", v_nf_base)),
            }
            if tpag in _TPAG_EXIGE_CARD:
                item["card"] = {"tpIntegra": 2}
            det_pag.append(item)
        if not det_pag:
            det_pag.append({"indPag": 0, "tPag": "01", "vPag": v_nf_base})

        crt = 1
        if hasattr(empresa, "regime_tributario") and empresa.regime_tributario:
            if "Normal" in empresa.regime_tributario:
                crt = 3

        # Código IBGE do município do emitente. DEVE ser da mesma UF, senão a SEFAZ
        # rejeita com "Código Município do Fato Gerador: difere da UF do emitente".
        cod_mun_uf = (
            getattr(empresa, "codigo_municipio", None)
            or "3550308"  # fallback SP capital (só quando empresa não configurou)
        )
        uf_emit = (empresa.uf or "SP").upper()
        uf_codes = {
            "AC": 12, "AL": 27, "AM": 13, "AP": 16, "BA": 29, "CE": 23, "DF": 53, "ES": 32, "GO": 52,
            "MA": 21, "MG": 31, "MS": 50, "MT": 51, "PA": 15, "PB": 25, "PE": 26, "PI": 22, "PR": 41,
            "RJ": 33, "RN": 24, "RO": 11, "RR": 14, "RS": 43, "SC": 42, "SE": 28, "SP": 35, "TO": 17,
        }
        c_uf = uf_codes.get(uf_emit, 35)

        # dest: só incluir se houver CPF/CNPJ. Consumidor anônimo em NFC-e omite o bloco.
        # A ordem dos elementos importa: CPF/CNPJ/idEstrangeiro DEVE vir antes de xNome.
        dest = None
        cliente = venda.get("cliente")
        if cliente:
            cpf = "".join(filter(str.isdigit, cliente.get("cpf") or ""))
            cnpj_cli = "".join(filter(str.isdigit, cliente.get("cnpj") or ""))
            if cpf and len(cpf) == 11:
                dest = {"CPF": cpf, "xNome": cliente.get("nome", "CONSUMIDOR").upper(), "indIEDest": 9}
            elif cnpj_cli and len(cnpj_cli) == 14:
                dest = {"CNPJ": cnpj_cli, "xNome": cliente.get("nome", "CONSUMIDOR").upper(), "indIEDest": 9}
            # sem doc → deixa dest = None (consumidor anônimo)

            # NF-e (mod 55) exige `enderDest`. SEFAZ rejeita com cStat 726
            # ("NF-e sem a informacao de endereco do destinatario") se omitido.
            # NFC-e (mod 65) NÃO exige — só incluir quando cliente enviou endereço.
            if dest is not None:
                end_cli = cliente.get("endereco") or {}
                tem_end = bool(end_cli.get("logradouro") or end_cli.get("cep"))
                if modelo == 55 or tem_end:
                    # Fallback: quando o usuário não informou, usar a UF/município do emitente
                    # (mínimo aceito pelo schema em homologação). Em produção o endereço
                    # real do destinatário deve vir do cadastro.
                    ender_dest = {
                        "xLgr": (end_cli.get("logradouro") or "NAO INFORMADO").upper()[:60],
                        "nro": str(end_cli.get("numero") or "SN")[:60],
                        "xBairro": (end_cli.get("bairro") or "NAO INFORMADO").upper()[:60],
                        "cMun": end_cli.get("codigo_municipio") or cod_mun_uf,
                        "xMun": (end_cli.get("cidade") or empresa.cidade or "NAO INFORMADO").upper()[:60],
                        "UF": (end_cli.get("uf") or uf_emit).upper(),
                        "CEP": "".join(filter(str.isdigit, end_cli.get("cep") or empresa.cep or "")),
                        "cPais": 1058,
                        "xPais": "BRASIL",
                    }
                    complemento = end_cli.get("complemento")
                    if complemento:
                        ender_dest["xCpl"] = str(complemento).upper()[:60]
                    dest["enderDest"] = ender_dest

        v_nf = _r(v_prod - v_desc + tot_v_st + tot_v_ipi + tot_v_ii - tot_v_icms_deson)

        payload: Dict[str, Any] = {
            "ambiente": "homologacao" if self.env != "producao" else "producao",
            "referencia": str(uuid.uuid4()),
            "infNFe": {
                "versao": "4.00",
                "ide": {
                    "cUF": c_uf,
                    "cNF": c_nf,
                    "natOp": "VENDA DE MERCADORIA",
                    "mod": modelo,
                    "serie": serie,
                    # SEFAZ exige nNF sequencial ascendente por (CNPJ, mod, serie).
                    # Fallback random só existe para scripts legados de teste em hom —
                    # em produção o caller SEMPRE passa `numero` calculado por MAX+1.
                    "nNF": numero if numero is not None else random.randint(1, 999999),
                    "dhEmi": datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds"),
                    "tpNF": 1,
                    "idDest": 1,
                    "cMunFG": cod_mun_uf,
                    "tpImp": 1 if modelo == 55 else 4,
                    "tpEmis": 1,
                    "tpAmb": 2 if self.env != "producao" else 1,
                    "finNFe": 1,
                    "indFinal": 1,
                    "indPres": 1,
                    "procEmi": 0,
                    "verProc": "1.0.0",
                },
                "emit": {
                    "CNPJ": "".join(filter(str.isdigit, empresa.cnpj)),
                    "xNome": empresa.razao_social.upper(),
                    "xFant": (empresa.nome_fantasia or empresa.razao_social).upper(),
                    "enderEmit": {
                        "xLgr": (empresa.logradouro or "RUA DO EMISSOR").upper(),
                        "nro": empresa.numero or "SN",
                        "xBairro": (empresa.bairro or "CENTRO").upper(),
                        "cMun": cod_mun_uf,
                        "xMun": (empresa.cidade or "SAO PAULO").upper(),
                        "UF": uf_emit,
                        "CEP": "".join(filter(str.isdigit, empresa.cep or "01001000")),
                        "cPais": "1058",
                        "xPais": "BRASIL",
                    },
                    "IE": (empresa.inscricao_estadual.strip().upper()
                           if (empresa.inscricao_estadual or "").strip().upper() == "ISENTO"
                           else "".join(filter(str.isdigit, empresa.inscricao_estadual or "")) or "ISENTO"),
                    "CRT": crt,
                },
                "det": det,
                "total": {
                    "ICMSTot": {
                        "vBC": _r(tot_v_bc),
                        "vICMS": _r(tot_v_icms),
                        "vICMSDeson": _r(tot_v_icms_deson),
                        "vFCPUFDest": 0.0,
                        "vICMSUFDest": 0.0,
                        "vICMSUFRemet": 0.0,
                        "vFCP": _r(tot_v_fcp),
                        "vBCST": _r(tot_v_bc_st),
                        "vST": _r(tot_v_st),
                        "vFCPST": _r(tot_v_fcp_st),
                        "vFCPSTRet": 0.0,
                        "vProd": _r(v_prod),
                        "vFrete": 0.0,
                        "vSeg": 0.0,
                        "vDesc": _r(v_desc),
                        "vII": _r(tot_v_ii),
                        "vIPI": _r(tot_v_ipi),
                        "vIPIDevol": 0.0,
                        "vPIS": _r(tot_v_pis),
                        "vCOFINS": _r(tot_v_cofins),
                        "vOutro": 0.0,
                        "vNF": v_nf,
                        "vTotTrib": _r(v_prod * 0.15),
                    },
                },
                "transp": {"modFrete": 9},
                "pag": {"detPag": det_pag},
            },
        }

        if dest:
            payload["infNFe"]["dest"] = dest

        return payload

    # ------------------------------------------------------------------
    # Transmissão / cancelamento / consulta
    # ------------------------------------------------------------------
    async def transmitir_nfce(self, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Envia o payload NFC-e (modelo 65) para a ACBr API de forma síncrona."""
        try:
            token = await self._get_access_token()
        except Exception as e:
            return "processando", {"erro": f"Falha de autenticação ACBr: {e}"}

        url = f"{self.base_url}/nfce"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=30.0)
        except Exception as e:
            logger.error(f"Erro de comunicação NFC-e ACBr: {e}")
            return "processando", {"erro": f"Erro de comunicação: {e}"}

        try:
            res_json = response.json()
        except Exception:
            res_json = {"raw": response.text}

        if response.status_code in (200, 201):
            # HTTP 200 apenas indica que a ACBr aceitou o payload — a SEFAZ pode ter rejeitado.
            # O status real está em res_json["status"] ("autorizado" | "rejeitado" | ...).
            acbr_status = (res_json.get("status") or "").lower()
            if acbr_status.startswith("autoriz"):
                return "autorizada", res_json
            aut = res_json.get("autorizacao") or {}
            motivo = aut.get("motivo_status") or res_json.get("motivo_status")
            codigo = aut.get("codigo_status") or res_json.get("codigo_status")
            logger.warning(f"NFC-e rejeitada pela SEFAZ (cStat {codigo}): {motivo}")
            return "rejeitada", res_json

        logger.warning(f"NFC-e rejeitada pela ACBr API ({response.status_code}): {response.text}")
        return "rejeitada", {"status_code": response.status_code, **res_json}

    async def cancelar_nfce(self, documento_id: str, justificativa: str, modelo: int = 65) -> Tuple[bool, Dict[str, Any]]:
        """Cancela um documento fiscal (NFC-e mod 65 ou NF-e mod 55) na ACBr API.

        Nome mantido por compat, mas roteia entre `/nfce` e `/nfe` conforme o modelo.
        Preferência: inferir o modelo pelo prefixo do `documento_id` (`nfc_` / `nfe_`)
        e só cair no argumento se o id não tiver prefixo reconhecível.
        """
        try:
            token = await self._get_access_token()
        except Exception as e:
            return False, {"erro": f"Falha de autenticação ACBr: {e}"}

        # Fonte de verdade do modelo é o prefixo do id retornado pela ACBr na emissão.
        if documento_id.startswith("nfc_"):
            recurso = "nfce"
        elif documento_id.startswith("nfe_"):
            recurso = "nfe"
        else:
            recurso = "nfce" if modelo == 65 else "nfe"

        url = f"{self.base_url}/{recurso}/{documento_id}/cancelamento"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"justificativa": justificativa}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=30.0)
        except Exception as e:
            logger.error(f"Erro de comunicação no cancelamento ACBr: {e}")
            return False, {"erro": f"Erro de comunicação: {e}"}

        try:
            res_json = response.json()
        except Exception:
            res_json = {"raw": response.text}

        if response.status_code in (200, 201):
            return True, res_json

        logger.warning(f"Cancelamento {recurso} rejeitado ({response.status_code}): {response.text}")
        return False, {"status_code": response.status_code, **res_json}

    async def inutilizar_faixa(
        self,
        cnpj: str,
        ano: int,
        serie: int,
        numero_inicial: int,
        numero_final: int,
        justificativa: str,
        modelo: int = 55,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Inutiliza uma faixa de numeração NF-e (mod 55) ou NFC-e (mod 65) via ACBr.

        Endpoint: POST /{nfe|nfce}/inutilizacoes
        Body: {cnpj, ano, serie, numero_inicial, numero_final, justificativa (≥15 chars)}

        Uso típico: quando o sistema gerou um `nNF` (mandou pra assinatura ou pra SEFAZ)
        e a nota nunca virou documento fiscal — o número fica "queimado" na sequência
        e precisa ser declarado como inutilizado pra fechar o livro fiscal.
        """
        try:
            token = await self._get_access_token()
        except Exception as e:
            return False, {"erro": f"Falha de autenticação ACBr: {e}"}

        recurso = "nfe" if modelo == 55 else "nfce"
        url = f"{self.base_url}/{recurso}/inutilizacoes"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "cnpj": "".join(filter(str.isdigit, cnpj)),
            "ano": ano,
            "serie": serie,
            "numero_inicial": numero_inicial,
            "numero_final": numero_final,
            "justificativa": justificativa,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=30.0)
        except Exception as e:
            logger.error(f"Erro de comunicação na inutilização ACBr: {e}")
            return False, {"erro": f"Erro de comunicação: {e}"}

        try:
            res_json = response.json()
        except Exception:
            res_json = {"raw": response.text}

        if response.status_code in (200, 201):
            return True, res_json

        logger.warning(f"Inutilização {recurso} rejeitada ({response.status_code}): {response.text}")
        return False, {"status_code": response.status_code, **res_json}

    async def transmitir_nfe(self, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Envia o payload NF-e (modelo 55) para a ACBr API de forma assíncrona."""
        try:
            token = await self._get_access_token()
        except Exception as e:
            return "processando", {"erro": f"Falha de autenticação ACBr: {e}", "referencia": payload.get("referencia")}

        url = f"{self.base_url}/nfe"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=30.0)
        except Exception as e:
            logger.error(f"Erro de comunicação NF-e ACBr: {e}")
            return "processando", {"erro": f"Erro de comunicação: {e}", "referencia": payload.get("referencia")}

        try:
            res_json = response.json()
        except Exception:
            res_json = {"raw": response.text}

        if response.status_code in (200, 201, 202):
            # HTTP 200 apenas indica que a ACBr aceitou o payload — a SEFAZ pode ter rejeitado.
            # O status real está em res_json["status"] ("autorizado" | "rejeitado" | "processando").
            acbr_status = (res_json.get("status") or "").lower()
            if acbr_status.startswith("autoriz"):
                return "autorizada", res_json
            if acbr_status.startswith("rejeit"):
                aut = res_json.get("autorizacao") or {}
                motivo = aut.get("motivo_status") or res_json.get("motivo_status")
                codigo = aut.get("codigo_status") or res_json.get("codigo_status")
                logger.warning(f"NF-e rejeitada pela SEFAZ (cStat {codigo}): {motivo}")
                return "rejeitada", res_json
            # Só cai em "processando" se a ACBr realmente devolveu esse estado (fila assíncrona).
            return "processando", res_json

        logger.warning(f"NF-e rejeitada pela ACBr API ({response.status_code}): {response.text}")
        return "rejeitada", {"status_code": response.status_code, **res_json}

    async def baixar_xml(self, documento_id: str, modelo: int = 65) -> Tuple[bool, Union[bytes, Dict[str, Any]]]:
        """Baixa o XML autorizado da NFC-e (modelo 65) ou NF-e (modelo 55). Recebe o id interno ACBr (nfc_xxx/nfe_xxx)."""
        try:
            token = await self._get_access_token()
        except Exception as e:
            return False, {"erro": f"Falha de autenticação ACBr: {e}"}
        recurso = "nfce" if modelo == 65 else "nfe"
        url = f"{self.base_url}/{recurso}/{documento_id}/xml"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, headers=headers, timeout=15.0)
        except Exception as e:
            return False, {"erro": str(e)}
        if r.status_code == 200:
            return True, r.content
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text}
        return False, {"status_code": r.status_code, **body}

    async def baixar_pdf(self, documento_id: str, modelo: int = 65) -> Tuple[bool, Union[bytes, Dict[str, Any]]]:
        """Baixa o PDF (DANFE) da NFC-e (modelo 65) ou NF-e (modelo 55). Recebe o id interno ACBr (nfc_xxx/nfe_xxx)."""
        try:
            token = await self._get_access_token()
        except Exception as e:
            return False, {"erro": f"Falha de autenticação ACBr: {e}"}
        recurso = "nfce" if modelo == 65 else "nfe"
        url = f"{self.base_url}/{recurso}/{documento_id}/pdf"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, headers=headers, timeout=20.0)
        except Exception as e:
            return False, {"erro": str(e)}
        if r.status_code == 200:
            return True, r.content
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text}
        return False, {"status_code": r.status_code, **body}

    async def consultar_documento(self, documento_id: str, modelo: int = 65) -> Tuple[bool, Dict[str, Any]]:
        """Consulta os dados de um DFe na ACBr (GET /nfce/{id} ou /nfe/{id}). Recebe o id interno ACBr (nfc_xxx/nfe_xxx)."""
        try:
            token = await self._get_access_token()
        except Exception as e:
            return False, {"erro": f"Falha de autenticação ACBr: {e}"}
        recurso = "nfce" if modelo == 65 else "nfe"
        url = f"{self.base_url}/{recurso}/{documento_id}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, headers=headers, timeout=10.0)
        except Exception as e:
            return False, {"erro": str(e)}
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text}
        if r.status_code == 200:
            return True, body
        return False, {"status_code": r.status_code, **body}

    async def consultar_status_nfe(self, referencia_ou_chave: str) -> Tuple[str, Dict[str, Any]]:
        """Consulta o status de processamento da NF-e na ACBr API."""
        try:
            token = await self._get_access_token()
        except Exception as e:
            return "processando", {"erro": f"Falha de autenticação ACBr: {e}"}

        url = f"{self.base_url}/nfe/{referencia_ou_chave}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10.0)
        except Exception as e:
            logger.error(f"Erro ao consultar NF-e ACBr: {e}")
            return "processando", {"erro": str(e)}

        try:
            res_json = response.json()
        except Exception:
            res_json = {"raw": response.text}

        if response.status_code == 200:
            status_api = res_json.get("status", "processando")
            if status_api in ("autorizado", "autorizada", "sucesso"):
                return "autorizada", res_json
            if status_api in ("rejeitado", "rejeitada", "erro"):
                return "rejeitada", res_json
            return "processando", res_json

        return "processando", {"status_code": response.status_code, **res_json}
