-- auditor-ibs-cbs: conferência dentro do banco (dialeto sqlserver).
-- 1) Carregue os itens das suas notas em ibscbs_auditoria_item (um registro por item com grupo IBS/CBS).
-- 2) SELECT * FROM ibscbs_auditoria_resultado ORDER BY chave, item, codigo;
-- Datas no formato AAAA-MM-DD. Os códigos AIC e de rejeição são os mesmos do auditor (NT 2025.002-RTC v1.53).

CREATE TABLE ibscbs_auditoria_item (chave NVARCHAR(60) NOT NULL, item NVARCHAR(10) NOT NULL, modelo SMALLINT NOT NULL, data_emissao CHAR(10) NOT NULL, cst CHAR(3), cclasstrib CHAR(6), ncm VARCHAR(8));
GO

CREATE VIEW ibscbs_auditoria_resultado AS
SELECT i.chave, i.item, 'AIC-011' AS codigo, N'1020' AS rejeicao, N'CST do IBS/CBS inexistente' AS problema
  FROM ibscbs_auditoria_item i
  WHERE NOT EXISTS (SELECT 1 FROM ibscbs_cst s WHERE s.cst = i.cst)
UNION ALL
SELECT i.chave, i.item, 'AIC-012' AS codigo, NULL AS rejeicao, N'CST fora da vigência' AS problema
  FROM ibscbs_auditoria_item i
  WHERE EXISTS (SELECT 1 FROM ibscbs_cst s WHERE s.cst = i.cst AND NOT ((s.inicio IS NULL OR s.inicio <= i.data_emissao) AND (s.fim IS NULL OR s.fim >= i.data_emissao)))
UNION ALL
SELECT i.chave, i.item, 'AIC-013' AS codigo, N'1023' AS rejeicao, N'cClassTrib inexistente' AS problema
  FROM ibscbs_auditoria_item i
  WHERE NOT EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib)
UNION ALL
SELECT i.chave, i.item, 'AIC-014' AS codigo, NULL AS rejeicao, N'cClassTrib fora da vigência' AS problema
  FROM ibscbs_auditoria_item i
  WHERE EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib AND NOT ((c.inicio IS NULL OR c.inicio <= i.data_emissao) AND (c.fim IS NULL OR c.fim >= i.data_emissao)))
UNION ALL
SELECT i.chave, i.item, 'AIC-015' AS codigo, N'1024' AS rejeicao, N'cClassTrib não pertence ao CST' AS problema
  FROM ibscbs_auditoria_item i
  WHERE i.cst IS NOT NULL AND EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib AND c.cst <> i.cst)
UNION ALL
SELECT i.chave, i.item, 'AIC-016' AS codigo, N'1025' AS rejeicao, N'cClassTrib não permitido neste documento' AS problema
  FROM ibscbs_auditoria_item i
  WHERE EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib) AND NOT EXISTS (SELECT 1 FROM ibscbs_cclasstrib_documento x WHERE x.cclasstrib = i.cclasstrib AND x.modelo = i.modelo AND (x.inicio IS NULL OR x.inicio <= i.data_emissao) AND (x.fim IS NULL OR x.fim >= i.data_emissao))
UNION ALL
SELECT i.chave, i.item, 'AIC-017' AS codigo, NULL AS rejeicao, N'NCM obrigatório para este cClassTrib' AS problema
  FROM ibscbs_auditoria_item i
  WHERE i.modelo IN (55, 65) AND EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib) AND (EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm n WHERE n.cclasstrib = i.cclasstrib AND (n.inicio IS NULL OR n.inicio <= i.data_emissao) AND (n.fim IS NULL OR n.fim >= i.data_emissao)) OR i.cclasstrib IN (N'200038', N'515001')) AND (i.ncm IS NULL OR LEN(i.ncm) <> 8 OR i.ncm IN ('00', '00000000'))
UNION ALL
SELECT i.chave, i.item, 'AIC-018' AS codigo, NULL AS rejeicao, N'NCM não pode usar este cClassTrib' AS problema
  FROM ibscbs_auditoria_item i
  WHERE i.modelo IN (55, 65) AND EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib) AND EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm n WHERE n.cclasstrib = i.cclasstrib AND (n.inicio IS NULL OR n.inicio <= i.data_emissao) AND (n.fim IS NULL OR n.fim >= i.data_emissao)) AND NOT (i.ncm IS NULL OR LEN(i.ncm) <> 8 OR i.ncm IN ('00', '00000000')) AND NOT (EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm n WHERE n.cclasstrib = i.cclasstrib AND i.ncm LIKE n.prefixo + '%' AND (n.inicio IS NULL OR n.inicio <= i.data_emissao) AND (n.fim IS NULL OR n.fim >= i.data_emissao)) AND (NOT EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm n JOIN ibscbs_cclasstrib_ncm_excecao e ON e.ncm_id = n.id WHERE n.cclasstrib = i.cclasstrib AND i.ncm LIKE n.prefixo + '%' AND (n.inicio IS NULL OR n.inicio <= i.data_emissao) AND (n.fim IS NULL OR n.fim >= i.data_emissao) AND i.ncm LIKE e.prefixo + '%' AND (e.inicio IS NULL OR e.inicio <= i.data_emissao) AND (e.fim IS NULL OR e.fim >= i.data_emissao)) OR EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm n WHERE n.cclasstrib = i.cclasstrib AND i.ncm LIKE n.prefixo + '%' AND (n.inicio IS NULL OR n.inicio <= i.data_emissao) AND (n.fim IS NULL OR n.fim >= i.data_emissao) AND (NOT EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm_excecao e WHERE e.ncm_id = n.id) OR EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm_excecao e WHERE e.ncm_id = n.id AND NOT ((e.inicio IS NULL OR e.inicio <= i.data_emissao) AND (e.fim IS NULL OR e.fim >= i.data_emissao)))))));
GO
