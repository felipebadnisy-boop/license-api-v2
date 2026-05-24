import requests
import time
import json
import os

# Configurações
API_URL = "https://api.tatidecora.com"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiZDk5MjkyNTktZjhiZi00NzdlLTkyMDgtYjNjZjQ4M2VhNWE2IiwidXNlcm5hbWUiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc3OTU4MDk5Nn0.eGCDZ8jfAtnoRqP3PmO1Ke7LRDQWU56qsmbidYqZBy4"
PRODUTO_SLUG = "meu-software"

def limpar_tela():
    os.system('cls' if os.name == 'nt' else 'clear')

def criar_chave(plano):
    """Cria uma chave via API"""
    url = f"{API_URL}/admin/create-license"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "produto_slug": PRODUTO_SLUG,
        "plano": plano
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            return result["dados"]["key"]
        else:
            return None
    except Exception as e:
        print(f"Erro: {e}")
        return None

def verificar_api():
    """Verifica se API está rodando"""
    try:
        response = requests.get(f"{API_URL}/", timeout=3)
        return response.status_code == 200
    except:
        return False

def mostrar_menu():
    print("=" * 60)
    print("         GERADOR DE CHAVES - RECOIL MACRO")
    print("=" * 60)
    print("\nESCOLHA O TIPO DE CHAVE:")
    print("-" * 50)
    print("   1. Teste Rapido (2 MINUTOS)")
    print("   2. Teste Gratis (3 HORAS)")
    print("   3. 1 DIA")
    print("   4. 30 DIAS")
    print("   5. 1 ANO (365 DIAS)")
    print("   6. VITALICIA (Nunca expira)")
    print("   7. GERAR TODOS (100 de cada)")
    print("   8. SAIR")
    print("=" * 60)

def gerar_chaves(plano_codigo, plano_nome, quantidade):
    """Gera N chaves para um plano especifico"""
    print(f"\nGerando {quantidade} chave(s) para: {plano_nome}")
    print("-" * 50)
    
    chaves = []
    sucesso = 0
    
    for i in range(quantidade):
        print(f"   [{i+1}/{quantidade}] Gerando...", end=" ")
        chave = criar_chave(plano_codigo)
        
        if chave:
            chaves.append(chave)
            sucesso += 1
            print(f"OK {chave}")
        else:
            print("FALHOU")
        
        time.sleep(0.1)
    
    # Salvar em arquivo
    nome_arquivo = f"chaves_{plano_codigo}_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    with open(nome_arquivo, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write(f"CHAVES - {plano_nome.upper()}\n")
        f.write("=" * 60 + "\n")
        f.write(f"Produto: {PRODUTO_SLUG}\n")
        f.write(f"Plano: {plano_codigo}\n")
        f.write(f"Quantidade solicitada: {quantidade}\n")
        f.write(f"Quantidade gerada: {sucesso}\n")
        f.write(f"Data geracao: {time.strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        
        for i, chave in enumerate(chaves, 1):
            f.write(f"{i:3d}. {chave}\n")
        
        f.write("\n" + "=" * 60 + "\n")
        f.write("INSTRUCOES:\n")
        f.write("-" * 60 + "\n")
        f.write("1. Distribua essas chaves para seus clientes\n")
        f.write("2. O cliente deve ativar no software\n")
        f.write("3. O tempo comeca a contar APOS a ativacao!\n")
        f.write("=" * 60 + "\n")
    
    return chaves, sucesso, nome_arquivo

def gerar_todos(quantidade):
    """Gera todos os tipos de chave"""
    print(f"\nGerando TODOS os tipos ({quantidade} chaves cada)")
    print("=" * 50)
    
    planos = {
        "trial_2min": "Teste Rapido (2 MINUTOS)",
        "trial_3h": "Teste Gratis (3 HORAS)",
        "1day": "1 DIA",
        "30days": "30 DIAS",
        "365days": "1 ANO",
        "lifetime": "VITALICIA"
    }
    
    total_geral = 0
    for codigo, nome in planos.items():
        print(f"\nProcessando: {nome}")
        chaves, sucesso, arquivo = gerar_chaves(codigo, nome, quantidade)
        total_geral += sucesso
        print(f"   Arquivo: {arquivo}")
    
    return total_geral

def main():
    while True:
        limpar_tela()
        
        # Verificar API
        if not verificar_api():
            print("=" * 30)
            print("   ERRO: API NAO ESTA RODANDO!")
            print("   Execute primeiro: python license_server.py")
            print("=" * 30)
            input("\nPressione ENTER para sair...")
            break
        
        mostrar_menu()
        
        try:
            opcao = input("\nDigite a opcao desejada (1-8): ").strip()
            
            if opcao == "8":
                print("\nSaindo... Volte sempre!")
                time.sleep(1)
                break
            
            if opcao == "7":
                print("\nATENCAO: Isso vai gerar 100 chaves de CADA tipo (total 600 chaves)")
                confirmar = input("Confirmar? (digite SIM para continuar): ").strip().upper()
                
                if confirmar == "SIM":
                    total = gerar_todos(100)
                    print(f"\nTOTAL GERAL: {total} chaves criadas!")
                else:
                    print("\nOperacao cancelada!")
                input("\nPressione ENTER para continuar...")
                continue
            
            # Mapeamento das opcoes
            planos_map = {
                "1": {"codigo": "trial_2min", "nome": "Teste Rapido (2 MINUTOS)"},
                "2": {"codigo": "trial_3h", "nome": "Teste Gratis (3 HORAS)"},
                "3": {"codigo": "1day", "nome": "1 DIA"},
                "4": {"codigo": "30days", "nome": "30 DIAS"},
                "5": {"codigo": "365days", "nome": "1 ANO"},
                "6": {"codigo": "lifetime", "nome": "VITALICIA"}
            }
            
            if opcao in planos_map:
                plano = planos_map[opcao]
                
                # Perguntar quantidade
                while True:
                    try:
                        qtd_input = input(f"\nQuantas chaves de {plano['nome']} voce quer gerar? (1-1000): ").strip()
                        if not qtd_input:
                            quantidade = 100
                        else:
                            quantidade = int(qtd_input)
                        
                        if quantidade < 1:
                            print("Quantidade deve ser maior que 0!")
                            continue
                        if quantidade > 1000:
                            print("Quantidade muito alta! Maximo recomendado: 1000")
                            confirmar = input("Continuar mesmo assim? (S/N): ").strip().upper()
                            if confirmar != "S":
                                continue
                        break
                    except ValueError:
                        print("Digite um numero valido!")
                
                print(f"\nVoce vai gerar {quantidade} chave(s) de {plano['nome']}")
                confirmar = input("Confirmar? (S/N): ").strip().upper()
                
                if confirmar == "S":
                    chaves, sucesso, arquivo = gerar_chaves(plano["codigo"], plano["nome"], quantidade)
                    print(f"\n{sucesso}/{quantidade} chaves geradas com sucesso!")
                    print(f"Arquivo salvo: {arquivo}")
                else:
                    print("\nOperacao cancelada!")
                
                input("\nPressione ENTER para continuar...")
            
            else:
                print("\nOpcao invalida! Digite um numero de 1 a 8.")
                time.sleep(1.5)
                
        except KeyboardInterrupt:
            print("\n\nSaindo...")
            break
        except Exception as e:
            print(f"\nErro inesperado: {e}")
            input("\nPressione ENTER para continuar...")

if __name__ == "__main__":
    main()