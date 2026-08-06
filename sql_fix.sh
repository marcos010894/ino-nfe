#!/bin/bash
sqlite3 innonfe.db << 'SQL'
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;
CREATE TABLE notas_new (
	id INTEGER NOT NULL, 
	empresa_id INTEGER, 
	modelo VARCHAR(2) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	chave_acesso VARCHAR(44), 
	numero INTEGER, 
	serie INTEGER, 
	valor_total FLOAT NOT NULL, 
	json_venda VARCHAR NOT NULL, 
	payload_enviado VARCHAR, 
	resposta_integradora VARCHAR, 
	xml_url VARCHAR, 
	pdf_url VARCHAR, 
	criado_em DATETIME NOT NULL, 
	atualizado_em DATETIME NOT NULL, 
    usuario_id INTEGER DEFAULT 1, 
	PRIMARY KEY (id), 
	FOREIGN KEY(empresa_id) REFERENCES empresas (id)
);
INSERT INTO notas_new SELECT * FROM notas;
DROP TABLE notas;
ALTER TABLE notas_new RENAME TO notas;
CREATE INDEX ix_notas_empresa_id ON notas (empresa_id);
COMMIT;
PRAGMA foreign_keys=on;
SQL
