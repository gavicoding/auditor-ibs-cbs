"""Catálogo das regras de validação da NT 2025.002-RTC (NF-e e NFC-e) usadas pelo auditor.

Cada código de rejeição (cStat) aponta para a regra, a página da nota técnica e se a regra já
está em produção ("Implementação futura" na NT = ainda não rejeita em produção).
Fonte: Nota Técnica 2025.002-RTC, versão 1.53, outubro de 2026 (Portal Nacional da NF-e).
"""

from __future__ import annotations

VERSAO_NT = "NT 2025.002-RTC v1.53"

# cStat -> (regra, página, em produção)
REGRAS: dict[str, tuple[str, int, bool]] = {
    "1006": ("BB01-10", 32, True),
    "1115": ("UB12-10", 40, False),
    "1020": ("UB13-10", 40, True),
    "1021": ("UB13-20", 40, True),
    "1022": ("UB13-30", 41, True),
    "1151": ("UB13-39", 41, True),
    "1116": ("UB13-40", 41, False),
    "1131": ("UB13-44", 41, True),
    "1132": ("UB13-45", 41, True),
    "1023": ("UB14-10", 41, True),
    "1024": ("UB14-20", 41, True),
    "1025": ("UB14-25", 41, True),
    "1202": ("UB14-60", 42, True),
    "1200": ("UB14-70", 42, True),
    "1201": ("UB14-80", 43, True),
    "1104": ("UB16-10", 43, False),
    "1026": ("UB18-10", 43, True),
    "1029": ("UB22-10", 44, True),
    "1030": ("UB22-20", 44, True),
    "1031": ("UB23-10", 44, True),
    "1111": ("UB24-10", 44, True),
    "1032": ("UB26-10", 44, True),
    "1033": ("UB26-20", 44, True),
    "1034": ("UB27-10", 44, True),
    "1035": ("UB28-10", 45, True),
    "1041": ("UB35-10", 45, True),
    "1036": ("UB37-10", 45, True),
    "1044": ("UB40-10", 45, True),
    "1083": ("UB40-20", 45, True),
    "1045": ("UB42-10", 46, True),
    "1112": ("UB43-10", 46, True),
    "1007": ("UB45-10", 46, True),
    "1074": ("UB45-20", 46, True),
    "1046": ("UB46-10", 46, True),
    "1047": ("UB47-10", 46, True),
    "1052": ("UB54-10", 47, True),
    "1150": ("UB54a-10", 47, True),
    "1037": ("UB56-10", 47, True),
    "1061": ("UB59-10", 48, True),
    "1090": ("UB59-20", 49, True),
    "1062": ("UB61-10", 49, True),
    "1187": ("UB62-10", 49, True),
    "1188": ("UB62a-10", 49, True),
    "1189": ("UB63-10", 49, True),
    "1028": ("UB64-10", 49, True),
    "1079": ("UB64-20", 49, True),
    "1063": ("UB65-10", 50, True),
    "1064": ("UB66-10", 50, True),
    "1069": ("UB67-10", 52, True),
    "1066": ("UB69-10", 52, True),
    "1067": ("UB70-10", 52, True),
    "1040": ("UB72-10", 52, True),
    "1051": ("UB72b-10", 52, True),
    "1068": ("UB72d-10", 52, True),
    "1141": ("UB82a-10", 52, True),
    "1142": ("UB82a-20", 53, True),
    "1144": ("UB82a-30", 53, True),
    "1133": ("UB106-30", 65, True),
    "1129": ("UB106-40", 65, True),
    "1170": ("UB112-20", 65, True),
    "1172": ("UB116-10", 65, True),
    "1173": ("UB116-20", 66, True),
    "1049": ("UB120-10", 66, True),
    "1138": ("UB131-10", 67, True),
    "1135": ("UB131-30", 67, True),
    "1158": ("UB131-40", 67, True),
    "1159": ("UB131-50", 67, True),
    "1118": ("W34-10", 70, True),
    "1119": ("W34-20", 70, True),
    "1076": ("W35-10", 71, True),
    "1077": ("W38-10", 71, True),
    "1078": ("W39-10", 71, True),
    "1080": ("W41-10", 71, True),
    "1081": ("W43-10", 71, True),
    "1082": ("W44-10", 71, True),
    "1084": ("W46-10", 71, True),
    "1085": ("W47-10", 71, True),
    "1086": ("W48-10", 71, True),
    "1088": ("W53-10", 71, True),
    "1089": ("W54-10", 71, True),
    "1091": ("W56-10", 71, True),
    "1087": ("W56a-10", 71, True),
    "1092": ("W58-10", 71, True),
    "1093": ("W59-10", 71, True),
    "1120": ("W59a-10", 71, True),
    "1121": ("W59b-10", 71, True),
    "1122": ("W59c-10", 71, True),
    "1123": ("W59d-10", 71, True),
    "1176": ("W59f-10", 71, True),
    "1177": ("W59g-10", 71, True),
}

# Códigos por tributo (IBS estadual, IBS municipal, CBS) para as regras que se repetem
POR_TRIBUTO = {
    "dif_indevido": {"IBSUF": "1029", "IBSMun": "1083", "CBS": "1090"},
    "dif_ausente": {"IBSUF": "1030", "IBSMun": "1044", "CBS": "1061"},
    "v_dif": {"IBSUF": "1031", "IBSMun": "1045", "CBS": "1062"},
    "red_indevido": {"IBSUF": "1032", "IBSMun": "1007", "CBS": "1028"},
    "red_ausente": {"IBSUF": "1033", "IBSMun": "1074", "CBS": "1079"},
    "p_red": {"IBSUF": "1034", "IBSMun": "1046", "CBS": "1063"},
    "aliq_efet": {"IBSUF": "1035", "IBSMun": "1047", "CBS": "1064"},
    "valor": {"IBSUF": "1041", "IBSMun": "1052", "CBS": "1069"},
    "aliquota": {"IBSUF": "1026", "IBSMun": "1036", "CBS": "1037"},
    "trib_regular": {"IBSUF": "1040", "IBSMun": "1051", "CBS": "1068"},
}

# Totais (caminho no grupo IBSCBSTot -> cStat)
TOTAIS = {
    "vBCIBSCBS": "1076",
    "gIBS/gIBSUF/vDif": "1077",
    "gIBS/gIBSUF/vDevTrib": "1078",
    "gIBS/gIBSUF/vIBSUF": "1080",
    "gIBS/gIBSMun/vDif": "1081",
    "gIBS/gIBSMun/vDevTrib": "1082",
    "gIBS/gIBSMun/vIBSMun": "1084",
    "gIBS/vIBS": "1085",
    "gIBS/vCredPres": "1086",
    "gCBS/vDif": "1088",
    "gCBS/vDevTrib": "1089",
    "gCBS/vCBS": "1091",
    "gCBS/vCredPres": "1087",
    "gMono/vIBSMono": "1092",
    "gMono/vCBSMono": "1093",
    "gMono/vIBSMonoReten": "1120",
    "gMono/vCBSMonoReten": "1121",
    "gMono/vIBSMonoRet": "1122",
    "gMono/vCBSMonoRet": "1123",
    "gEstornoCred/vIBSEstCred": "1176",
    "gEstornoCred/vCBSEstCred": "1177",
}

# UB14-60/70/80: cClassTrib que só cabem em certas notas de débito/crédito
CCLASS_DEBITO_CREDITO = {
    "410030": ({"07"}, set()),
    "800001": ({"05"}, {"05"}),
    "800002": ({"01"}, set()),
    "810001": (set(), {"02"}),
    "811001": ({"02"}, set()),
    "811002": ({"03"}, set()),
    "811003": ({"08"}, set()),
}
DEBITO_EXIGE = {"01": "800002", "02": "811001", "03": "811002", "05": "800001", "07": "410030", "08": "811003"}
CREDITO_EXIGE = {"02": "810001", "05": "800001"}

# UB18-10, UB37-10 e UB56-10: alíquotas fixadas em lei para o período de teste
ALIQUOTAS_LEI = {
    2025: {"IBSUF": "0.10", "IBSMun": "0", "CBS": "0.90"},
    2026: {"IBSUF": "0.10", "IBSMun": "0", "CBS": "0.90"},
    2027: {"IBSUF": "0.05", "IBSMun": "0.05"},
    2028: {"IBSUF": "0.05", "IBSMun": "0.05"},
}


def referencia(cstat: str) -> dict | None:
    """Dados da regra oficial para anexar a um achado."""
    regra = REGRAS.get(cstat)
    if not regra:
        return None
    nome, pagina, producao = regra
    return {"rejeicao": cstat, "regra_nt": nome, "pagina_nt": pagina, "em_producao": producao}
