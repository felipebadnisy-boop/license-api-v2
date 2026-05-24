import sqlite3

def limpar_chaves():
    conn = sqlite3.connect('licenses.db')
    cursor = conn.cursor()
    
    # Contar antes
    cursor.execute("SELECT COUNT(*) FROM licencas")
    total_antes = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE plano = 'lifetime'")
    vitalicias_antes = cursor.fetchone()[0]
    
    # Deletar todas as chaves que NÃO são vitalícias
    cursor.execute("DELETE FROM licencas WHERE plano != 'lifetime'")
    deletadas = cursor.rowcount
    
    # Deletar sessões ativas
    cursor.execute("DELETE FROM sessoes_ativas")
    
    conn.commit()
    
    # Contar depois
    cursor.execute("SELECT COUNT(*) FROM licencas")
    total_depois = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE plano = 'lifetime'")
    vitalicias_depois = cursor.fetchone()[0]
    
    conn.close()
    
    print("=" * 50)
    print("LIMPEZA DO BANCO DE DADOS")
    print("=" * 50)
    print(f"Chaves antes: {total_antes}")
    print(f"Chaves vitalícias mantidas: {vitalicias_antes}")
    print(f"Chaves deletadas: {deletadas}")
    print(f"Chaves depois: {total_depois}")
    print("=" * 50)
    print("✅ Limpeza concluída!")
    print("💎 Apenas chaves vitalícias foram mantidas")

if __name__ == "__main__":
    limpar_chaves()