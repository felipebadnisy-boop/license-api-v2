import subprocess
import time
import webbrowser
import os
import sys
import threading
import psutil

# Configurações
API_DIR = r"C:\Users\Lipee Lipinhuuu\Desktop\Meu macro\license"
MACRO_DIR = r"C:\Users\Lipee Lipinhuuu\Desktop\Meu macro\dist"
API_FILE = "license_server.py"
MACRO_FILE = "RecoilMacro_API.exe"
API_URL = "http://localhost:5000"
DOCS_URL = "http://localhost:5000/docs"

def print_color(text, color="white"):
    """Print colorido no terminal"""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "white": "\033[0m"
    }
    print(f"{colors.get(color, colors['white'])}{text}{colors['white']}")

def start_api():
    """Inicia a API em segundo plano"""
    print_color("[1/4] Iniciando API de licenciamento...", "blue")
    
    os.chdir(API_DIR)
    
    # Abre o terminal da API
    subprocess.Popen(
        f'start cmd /k "cd /d {API_DIR} && python {API_FILE}"',
        shell=True
    )
    
    time.sleep(3)
    print_color("✓ API iniciada!", "green")

def start_macro():
    """Inicia o macro"""
    print_color("[2/4] Iniciando Recoil Macro...", "blue")
    
    macro_path = os.path.join(MACRO_DIR, MACRO_FILE)
    
    if os.path.exists(macro_path):
        subprocess.Popen(macro_path, shell=True)
        print_color("✓ Macro iniciado!", "green")
    else:
        print_color(f"⚠️ Macro não encontrado em: {macro_path}", "yellow")

def open_browser():
    """Abre o navegador na documentação da API"""
    print_color("[3/4] Abrindo documentação da API...", "blue")
    
    time.sleep(2)
    webbrowser.open(DOCS_URL)
    print_color("✓ Navegador aberto!", "green")

def check_api():
    """Verifica se API está rodando"""
    import requests
    try:
        response = requests.get(f"{API_URL}/", timeout=5)
        return response.status_code == 200
    except:
        return False

def wait_api():
    """Aguarda API ficar pronta"""
    print_color("[0/4] Aguardando API iniciar...", "yellow")
    
    for i in range(15):
        if check_api():
            print_color("✓ API está respondendo!", "green")
            return True
        time.sleep(1)
        print(f"   Aguardando... {i+1}/15")
    
    print_color("⚠️ API não respondeu. Verifique se está rodando.", "yellow")
    return False

def show_menu():
    """Mostra menu interativo"""
    print("=" * 60)
    print("🎯 RECOIL MACRO - LAUNCHER PROFISSIONAL")
    print("=" * 60)
    print("")
    print("  1. 🚀 Iniciar TUDO (API + Macro + Site)")
    print("  2. 🔧 Iniciar apenas API")
    print("  3. 🎮 Iniciar apenas Macro")
    print("  4. 🌐 Abrir apenas Site da API")
    print("  5. ❌ Fechar TUDO")
    print("  6. 📊 Verificar Status")
    print("  7. 💀 Matar todos os processos (emergência)")
    print("")
    print("=" * 60)

def kill_all():
    """Mata todos os processos relacionados"""
    print_color("💀 Matando processos...", "red")
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Mata processos Python rodando a API
            if proc.info['name'] == 'python.exe' and 'license_server' in str(proc.info['cmdline']):
                proc.kill()
                print(f"   ✓ API finalizada (PID: {proc.info['pid']})")
            
            # Mata o macro
            if proc.info['name'] == 'RecoilMacro_API.exe':
                proc.kill()
                print(f"   ✓ Macro finalizado (PID: {proc.info['pid']})")
                
        except:
            pass
    
    print_color("✓ Todos os processos foram finalizados!", "green")
    time.sleep(2)

def check_status():
    """Verifica status dos serviços"""
    print("\n" + "=" * 40)
    print("📊 STATUS DOS SERVIÇOS")
    print("=" * 40)
    
    # Verifica API
    if check_api():
        print("   ✅ API: ONLINE")
    else:
        print("   ❌ API: OFFLINE")
    
    # Verifica Macro
    macro_running = False
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] == 'RecoilMacro_API.exe':
            macro_running = True
            break
    
    if macro_running:
        print("   ✅ Macro: RODANDO")
    else:
        print("   ❌ Macro: PARADO")
    
    print("=" * 40 + "\n")

def start_all():
    """Inicia tudo"""
    print("\n" + "=" * 60)
    print_color("🚀 INICIANDO RECOIL MACRO - MODO COMPLETO", "green")
    print("=" * 60 + "\n")
    
    # Inicia API
    start_api()
    
    # Aguarda API
    if not wait_api():
        print_color("⚠️ Continuando mesmo assim...", "yellow")
    
    # Abre navegador
    open_browser()
    
    # Inicia macro
    start_macro()
    
    print("\n" + "=" * 60)
    print_color("✅ TUDO INICIADO COM SUCESSO!", "green")
    print_color("📌 Dica: Use a chave no macro para ativar", "yellow")
    print("=" * 60)
    print("")
    input("Pressione ENTER para sair...")

def start_api_only():
    """Inicia apenas a API"""
    print_color("\n🔧 Iniciando apenas API...", "blue")
    start_api()
    wait_api()
    print_color("✓ API está rodando!", "green")
    print("")
    input("Pressione ENTER para sair...")

def start_macro_only():
    """Inicia apenas o macro"""
    print_color("\n🎮 Iniciando apenas Macro...", "blue")
    start_macro()
    print("")
    input("Pressione ENTER para sair...")

def open_site_only():
    """Abre apenas o site"""
    print_color("\n🌐 Abrindo site da API...", "blue")
    webbrowser.open(DOCS_URL)
    print_color("✓ Navegador aberto!", "green")
    print("")
    input("Pressione ENTER para sair...")

def main():
    """Menu principal"""
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        show_menu()
        
        opcao = input("👉 Escolha uma opção (1-7): ").strip()
        
        if opcao == "1":
            start_all()
            break
        elif opcao == "2":
            start_api_only()
        elif opcao == "3":
            start_macro_only()
        elif opcao == "4":
            open_site_only()
        elif opcao == "5":
            kill_all()
            print_color("\n👋 Saindo...", "green")
            time.sleep(1)
            break
        elif opcao == "6":
            check_status()
            input("Pressione ENTER para continuar...")
        elif opcao == "7":
            kill_all()
        else:
            print_color("\n❌ Opção inválida!", "red")
            time.sleep(1)

if __name__ == "__main__":
    # Verifica se psutil está instalado
    try:
        import psutil
    except ImportError:
        print_color("⚠️ Instalando psutil...", "yellow")
        subprocess.run([sys.executable, "-m", "pip", "install", "psutil"], capture_output=True)
        print_color("✓ Psutil instalado!", "green")
    
    main()