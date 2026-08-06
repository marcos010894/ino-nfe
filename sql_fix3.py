import sqlite3
conn = sqlite3.connect('backend/innonfe.db')
c = conn.cursor()
c.execute('PRAGMA foreign_keys=off;')
c.executescript('''
BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS notas_new (
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
-- If notas exists, copy it.
INSERT OR IGNORE INTO notas_new SELECT * FROM notas;
DROP TABLE IF EXISTS notas;
ALTER TABLE notas_new RENAME TO notas;
CREATE INDEX IF NOT EXISTS ix_notas_empresa_id ON notas (empresa_id);
COMMIT;
''')
c.execute('PRAGMA foreign_keys=on;')
conn.close()
