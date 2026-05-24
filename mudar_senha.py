import sqlite3
import hashlib

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Conectar ao banco
conn = sqlite3.connect('licenses.db')
cursor = conn.cursor()

# Nova senha
nova_senha = "36791788"
senha_hash = hash_password(nova_senha)

# Atualizar senha do admin
cursor.execute("UPDATE admin_users SET password_hash = ? WHERE username = 'admin'", (senha_hash,))
conn.commit()

print(f"Senha do admin alterada para: {nova_senha}")

conn.close()