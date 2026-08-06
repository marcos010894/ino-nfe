#!/bin/bash
python -c "
import sqlite3
conn = sqlite3.connect('innonfe.db')
c = conn.cursor()
c.execute(\"UPDATE usuarios SET token_integracao='a_xmjcydnNkdIk-PbyudWAHJP3q-iwGrcJHAz6uz5dk' WHERE email='christian.silva@netminas.com.br'\")
conn.commit()
conn.close()
"
