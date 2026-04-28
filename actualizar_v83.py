# ═══════════════════════════════════════════════════════════════
#  ACTUALIZACION v8.3 — ICT PRO (S/R + AUTO-TRADE)
#  ═══ EJECUTA: python actualizar_v83.py ═══
#
#  QUE CAMBIA:
#  - strategy.py → S/R automatico + S/R flip + pullback entry
#  - main.py → Auto-ejecucion en MT5 (abre trades solito)
#  - data_feed.py / telegram_bot.py (mismos)
#
#  IMPORTANTE: Preserva tus API keys de config.py
# ═══════════════════════════════════════════════════════════════

import os
import shutil
import sys

REPO_URL = "https://raw.githubusercontent.com/gozustrike-lab/tradingpro24-7/main/"

FILES_TO_DOWNLOAD = [
    "strategy.py",
    "main.py",
    "data_feed.py",
    "telegram_bot.py",
    "risk_manager.py",
    "chart_generator.py",
]


def backup_file(filepath):
    if os.path.exists(filepath):
        backup = filepath + ".bak_v83"
        shutil.copy2(filepath, backup)
        print("  Backup: {}".format(backup))


def download_file(filename):
    url = REPO_URL + filename
    try:
        import urllib.request
        urllib.request.urlretrieve(url, filename)
        print("  OK: {}".format(filename))
        return True
    except Exception as e:
        print("  ERROR descargando {}: {}".format(filename, e))
        return False


def patch_config():
    config_path = "config.py"
    if not os.path.exists(config_path):
        print("  ERROR: config.py no encontrado!")
        return False

    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    modified = False

    # 1. Agregar XAUUSD a FOREX_PAIRS
    if '"XAUUSD"' not in content and "'XAUUSD'" not in content:
        if 'FOREX_PAIRS' in content:
            content = content.replace('FOREX_PAIRS = [', 'FOREX_PAIRS = [\n    "XAUUSD",')
            modified = True
            print("  + XAUUSD a FOREX_PAIRS")

    # 2. XAUUSD pip_value
    if '"XAUUSD": 0.10' not in content and "'XAUUSD': 0.10" not in content:
        if '"pip_values"' in content:
            content = content.replace('"pip_values": {', '"pip_values": {\n        "XAUUSD": 0.10,')
            modified = True
            print("  + XAUUSD pip_value=0.10")
        elif "'pip_values'" in content:
            content = content.replace("'pip_values': {", "'pip_values': {\n        'XAUUSD': 0.10,")
            modified = True
            print("  + XAUUSD pip_value=0.10")

    # 3. XAUUSD digits
    if '"XAUUSD": 2' not in content and "'XAUUSD': 2" not in content:
        if '"digits"' in content:
            content = content.replace('"digits": {', '"digits": {\n        "XAUUSD": 2,')
            modified = True
            print("  + XAUUSD digits=2")
        elif "'digits'" in content:
            content = content.replace("'digits': {", "'digits': {\n        'XAUUSD': 2,")
            modified = True
            print("  + XAUUSD digits=2")

    # 4. SIN LIMITE DE PERDIDAS
    for old_val in ['"daily_loss_limit": 5.0', '"daily_loss_limit": 3.0',
                    "'daily_loss_limit': 5.0", "'daily_loss_limit': 3.0"]:
        if old_val in content:
            new_val = old_val.replace('5.0', '999.0').replace('3.0', '999.0')
            content = content.replace(old_val, new_val)
            modified = True
            print("  + daily_loss_limit = 999 (sin limite)")

    # 5. max_daily_trades
    if '"max_daily_trades": 3' in content:
        content = content.replace('"max_daily_trades": 3', '"max_daily_trades": 30')
        modified = True
        print("  + max_daily_trades: 30")
    elif "'max_daily_trades': 3" in content:
        content = content.replace("'max_daily_trades': 3", "'max_daily_trades': 30")
        modified = True
        print("  + max_daily_trades: 30")

    # 6. check_interval rapido
    if '"check_interval": 60' in content:
        content = content.replace('"check_interval": 60', '"check_interval": 20')
        modified = True
        print("  + check_interval: 20s")

    # 7. Agregar AUTO_TRADE config
    if 'AUTO_TRADE' not in content:
        content += '\n\n# ─── AUTO-TRADE (abre operaciones en MT5) ─────────────\nAUTO_TRADE = True\nAUTO_TRADE_VOLUME = 0.01\n'
        modified = True
        print("  + AUTO_TRADE = True (0.01 lotes)")

    # 8. XAUUSD PAIR_SESSIONS
    if 'PAIR_SESSIONS' in content and 'XAUUSD' not in content.split('PAIR_SESSIONS')[1][:300]:
        last_brace = content.find('}', content.index('PAIR_SESSIONS'))
        if last_brace > 0:
            content = content[:last_brace] + '    "XAUUSD": ["london", "new_york"],\n' + content[last_brace:]
            modified = True
            print("  + XAUUSD PAIR_SESSIONS")

    # 9. RISK_PER_PAIR XAUUSD
    if '"XAUUSD": {"sl_pips":' not in content:
        if 'RISK_PER_PAIR' in content:
            last_brace = content.rfind('}')
            if last_brace > 0:
                content = content[:last_brace] + '    "XAUUSD": {"sl_pips": 25, "tp_pips": 25},\n' + content[last_brace:]
                modified = True
                print("  + XAUUSD RISK_PER_PAIR")

    # 10. MT5_TIMEFRAME y DATA_DIR
    if 'MT5_TIMEFRAME' not in content:
        content += '\nMT5_TIMEFRAME = 15\n'
        modified = True
        print("  + MT5_TIMEFRAME")

    if 'DATA_DIR' not in content:
        content += '\nDATA_DIR = os.path.join(BASE_DIR, "data")\nos.makedirs(DATA_DIR, exist_ok=True)\n'
        modified = True
        print("  + DATA_DIR")

    if modified:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("  config.py parcheado OK")
    else:
        print("  config.py ya actualizado")

    return True


def main():
    print("=" * 55)
    print("  ACTUALIZACION v8.3 — ICT PRO")
    print("  S/R Automatico + Auto-Trade MT5")
    print("=" * 55)
    print()

    print("[1/3] Descargando archivos...")
    all_ok = True
    for filename in FILES_TO_DOWNLOAD:
        backup_file(filename)
        if not download_file(filename):
            all_ok = False

    print()
    print("[2/3] Parcheando config.py...")
    patch_config()
    print()

    print("[3/3] Cambios:")
    print("  strategy.py: S/R auto + S/R flip + pullback")
    print("  main.py: Auto-ejecucion MT5")
    print("  config.py: AUTO_TRADE = True + sin limites")
    print()

    if all_ok:
        print("ACTUALIZACION v8.3 COMPLETADA!")
        print("Ejecuta: python main.py")
        print()
        print("El bot ahora:")
        print("  1. Detecta S/R automaticamente (tus lineas rojas)")
        print("  2. Detecta S/R flip (resistencia→soporte)")
        print("  3. Busca pullback a S/R como entrada")
        print("  4. Abre la operacion SOLO en MT5")
        print("  5. Envia senal a Telegram")
    else:
        print("ACTUALIZACION CON ERRORES — Revisa arriba")


if __name__ == "__main__":
    main()
