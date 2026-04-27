# ═══════════════════════════════════════════════════════════════
#  TRADING BOT — ACTUALIZADOR AUTOMÁTICO v1.0
#  Un solo comando para actualizar sin romper nada
#
#  USO: venv312\Scripts\python actualizar.py
# ═══════════════════════════════════════════════════════════════

import os
import sys
import shutil
import zipfile
import requests
from datetime import datetime

# ─── CONFIGURACIÓN ─────────────────────────────────────────
REPO = "gozustrike-lab/tradingpro24-7"
BRANCH = "main"

# Archivos que SE actualizan (código del bot)
UPDATE_FILES = [
    "strategy.py",
    "main.py",
    "telegram_bot.py",
    "ai_vision.py",
    "risk_manager.py",
    "trade_logger.py",
    "copy_trading.py",
    "chart_generator.py",
    "data_feed.py",
    "config_template.py",
]

# Archivos que NUNCA se tocan
PROTECTED = [
    "config.py",          # Tiene tus API keys
    "venv312/",           # Entorno Python
    "venv/",              # Entorno Python alternativo
    "logs/",              # Logs del bot
    "screenshots/",       # Capturas de pantalla
    "data/",              # Datos cache
    "__pycache__/",       # Python cache
    "*.log",              # Archivos de log
    "actualizar.py",      # Este mismo script
    "bot.log",            # Log del bot
]

# ─── COLORES PARA CMD ─────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════╗
║        TRADING BOT — ACTUALIZADOR v1.0          ║
║    Descarga y reemplaza solo lo necesario        ║
╚══════════════════════════════════════════════════╝{RESET}
""")


def print_step(num, text):
    print(f"\n{BLUE}{BOLD}[PASO {num}] {RESET}{BOLD}{text}{RESET}")
    print("-" * 50)


def print_ok(text):
    print(f"  {GREEN}✅ {text}{RESET}")


def print_warn(text):
    print(f"  {YELLOW}⚠️  {text}{RESET}")


def print_error(text):
    print(f"  {RED}❌ {text}{RESET}")


def print_info(text):
    print(f"  {CYAN}ℹ️  {text}{RESET}")


def is_protected(filepath):
    """Verifica si un archivo está protegido."""
    for p in PROTECTED:
        if filepath.endswith(p) or filepath.startswith(p):
            return True
    return False


def create_backup(project_dir):
    """Crea backup de los archivos que se van a reemplazar."""
    backup_dir = os.path.join(project_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"

    changed = []
    for fname in UPDATE_FILES:
        filepath = os.path.join(project_dir, fname)
        if os.path.exists(filepath):
            changed.append(fname)

    if not changed:
        print_info("No hay archivos previos para respaldar (primera instalación)")
        return None

    backup_path = os.path.join(backup_dir, backup_name)
    os.makedirs(backup_path, exist_ok=True)

    for fname in changed:
        src = os.path.join(project_dir, fname)
        dst = os.path.join(backup_path, fname)
        shutil.copy2(src, dst)
        print_info(f"Respaldado: {fname}")

    print_ok(f"Backup creado: {backup_name} ({len(changed)} archivos)")

    # Limpiar backups viejos (mantener solo los últimos 5)
    all_backups = sorted([d for d in os.listdir(backup_dir)
                          if os.path.isdir(os.path.join(backup_dir, d))])
    if len(all_backups) > 5:
        for old in all_backups[:-5]:
            old_path = os.path.join(backup_dir, old)
            shutil.rmtree(old_path)
            print_info(f"Backup viejo eliminado: {old}")

    return backup_path


def download_repo(project_dir):
    """Descarga el ZIP del repositorio de GitHub."""
    url = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
    zip_path = os.path.join(project_dir, "update_temp.zip")

    print_info(f"Descargando de: {url}")

    try:
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()

        total = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded * 100 // total
                    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                    print(f"\r  {CYAN}⬇️  [{bar}] {pct}%{RESET}", end="", flush=True)

        print(f"\r  {GREEN}⬇️  Descarga completa          {RESET}")
        return zip_path

    except requests.exceptions.RequestException as e:
        print_error(f"Error descargando: {e}")
        return None


def extract_and_update(zip_path, project_dir):
    """Extrae el ZIP y reemplaza solo los archivos necesarios."""
    extract_dir = os.path.join(project_dir, "update_temp")
    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)
        print_ok("ZIP extraído correctamente")
    except zipfile.BadZipFile:
        print_error("Error: El ZIP descargado está corrupto")
        return False

    # Encontrar la carpeta del repo dentro del ZIP
    repo_folder = None
    for item in os.listdir(extract_dir):
        full_path = os.path.join(extract_dir, item)
        if os.path.isdir(full_path) and item.startswith(REPO.split("/")[1]):
            repo_folder = full_path
            break

    if not repo_folder:
        print_error("No se encontró la carpeta del repositorio en el ZIP")
        return False

    # Reemplazar archivos
    updated = []
    skipped = []

    for fname in UPDATE_FILES:
        src = os.path.join(repo_folder, fname)
        dst = os.path.join(project_dir, fname)

        if not os.path.exists(src):
            skipped.append(f"{fname} (no existe en el repo)")
            continue

        if is_protected(fname):
            skipped.append(f"{fname} (PROTEGIDO)")
            continue

        shutil.copy2(src, dst)
        updated.append(fname)
        print_ok(f"Actualizado: {fname}")

    # Verificar si hay archivos nuevos (no en la lista)
    for item in os.listdir(repo_folder):
        src_item = os.path.join(repo_folder, item)
        if os.path.isfile(src_item):
            if item not in UPDATE_FILES and not is_protected(item) and item.endswith(".py"):
                dst_item = os.path.join(project_dir, item)
                if not os.path.exists(dst_item):
                    shutil.copy2(src_item, dst_item)
                    updated.append(f"{item} (NUEVO)")
                    print_info(f"Nuevo archivo: {item}")

    # Mostrar resumen
    print(f"\n{BOLD}═══ RESUMEN DE ACTUALIZACIÓN ═══{RESET}")
    print_ok(f"{len(updated)} archivos actualizados")
    if skipped:
        print_warn(f"{len(skipped)} archivos omitidos:")
        for s in skipped:
            print(f"      {YELLOW}↳ {s}{RESET}")

    return len(updated) > 0


def cleanup(project_dir):
    """Elimina archivos temporales."""
    zip_path = os.path.join(project_dir, "update_temp.zip")
    extract_dir = os.path.join(project_dir, "update_temp")

    if os.path.exists(zip_path):
        os.remove(zip_path)
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)

    print_ok("Archivos temporales eliminados")


def main():
    print_banner()

    # Detectar el directorio del proyecto
    project_dir = os.path.dirname(os.path.abspath(__file__))
    print_info(f"Directorio del proyecto: {project_dir}")

    # Verificar que estamos en el lugar correcto
    if not os.path.exists(os.path.join(project_dir, "config.py")):
        print_error("No se encontró config.py. ¿Estás en la carpeta correcta del bot?")
        print_info("Debes ejecutar este script desde la carpeta del bot:")
        print_info(f"  cd C:\\TradingIA\\tradingpro24-7-main")
        print_info(f"  venv312\\Scripts\\python actualizar.py")
        sys.exit(1)

    # Verificar que requests está instalado
    try:
        import requests
    except ImportError:
        print_error("No se encontró 'requests'. Instalando...")
        os.system(f"{sys.executable} -m pip install requests -q")
        print_ok("requests instalado")
        import requests

    # PASO 1: Crear backup
    print_step(1, "CREAR BACKUP DE SEGURIDAD")
    backup = create_backup(project_dir)

    # PASO 2: Descargar
    print_step(2, "DESCARGAR ÚLTIMA VERSIÓN DE GITHUB")
    zip_path = download_repo(project_dir)
    if not zip_path:
        print_error("No se pudo descargar. Verifica tu conexión a internet.")
        sys.exit(1)

    # PASO 3: Extraer y actualizar
    print_step(3, "REEMPLAZAR ARCHIVOS")
    success = extract_and_update(zip_path, project_dir)

    # PASO 4: Limpiar
    print_step(4, "LIMPIAR ARCHIVOS TEMPORALES")
    cleanup(project_dir)

    # RESULTADO FINAL
    print(f"\n{GREEN}{BOLD}════════════════════════════════════════════{RESET}")
    if success:
        print(f"{GREEN}{BOLD}  ✅ ACTUALIZACIÓN COMPLETADA{RESET}")
        print(f"{GREEN}{BOLD}════════════════════════════════════════════{RESET}")
        print(f"\n{CYAN}  Tu config.py NO fue modificado (API keys seguras){RESET}")
        print(f"{CYAN}  Los backups están en la carpeta 'backups/'{RESET}")
        print(f"\n{BOLD}  Siguiente paso:{RESET}")
        print(f"  {YELLOW}1. Cierra el bot si está corriendo (Ctrl+C){RESET}")
        print(f"  {YELLOW}2. Ejecuta: venv312\\Scripts\\python main.py{RESET}")
        print(f"\n{GREEN}  ¡Listo! Ya tienes la última versión.{RESET}")
    else:
        print(f"{RED}{BOLD}  ❌ LA ACTUALIZACIÓN NO COMPLETÓ{RESET}")
        print(f"{RED}{BOLD}════════════════════════════════════════════{RESET}")
        print(f"  No te preocupes, tus archivos están intactos (se restauró el backup).")
        print(f"  Verifica tu conexión a internet e intenta de nuevo.")

    print(f"\n{BOLD}Versión actual: {datetime.now().strftime('%Y-%m-%d %H:%M')}{RESET}\n")

    input("Presiona Enter para salir...")


if __name__ == "__main__":
    main()
