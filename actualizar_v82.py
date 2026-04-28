# ═══════════════════════════════════════════════════════════════
#  ACTUALIZACION v8.2 MOMENTUM ICT + MULTI-TIMEFRAME
#  ═══ EJECUTA: python actualizar_v82.py ═══
#
#  Que cambia:
#  - strategy.py → v8.2 con MTF (M5 direccion + M1 entrada)
#  - main.py → v8.2 (muestra info MTF en senales)
#  - config.py → daily_loss_limit = 999 (sin limite, pruebas)
#  - data_feed.py / telegram_bot.py / risk_manager.py (ya actualizados)
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
        backup = filepath + ".bak_v82"
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
            content = content.replace(
                'FOREX_PAIRS = [',
                'FOREX_PAIRS = [\n    "XAUUSD",'
            )
            modified = True
            print("  + XAUUSD agregado a FOREX_PAIRS")

    # 2. Agregar XAUUSD a pip_values (0.10 para oro)
    if '"XAUUSD": 0.10' not in content and "'XAUUSD': 0.10" not in content:
        if '"pip_values"' in content:
            content = content.replace('"pip_values": {', '"pip_values": {\n        "XAUUSD": 0.10,')
            modified = True
            print("  + XAUUSD pip_value=0.10")
        elif "'pip_values'" in content:
            content = content.replace("'pip_values': {", "'pip_values': {\n        'XAUUSD': 0.10,")
            modified = True
            print("  + XAUUSD pip_value=0.10")

    # 3. Agregar XAUUSD a digits (2 para oro)
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
    if '"daily_loss_limit": 5.0' in content:
        content = content.replace('"daily_loss_limit": 5.0', '"daily_loss_limit": 999.0')
        modified = True
        print("  + daily_loss_limit: 5.0 -> 999.0 (SIN LIMITE)")
    elif '"daily_loss_limit": 3.0' in content:
        content = content.replace('"daily_loss_limit": 3.0', '"daily_loss_limit": 999.0')
        modified = True
        print("  + daily_loss_limit: 3.0 -> 999.0 (SIN LIMITE)")
    elif "'daily_loss_limit': 5.0" in content:
        content = content.replace("'daily_loss_limit': 5.0", "'daily_loss_limit': 999.0")
        modified = True
        print("  + daily_loss_limit: SIN LIMITE")
    elif "'daily_loss_limit': 3.0" in content:
        content = content.replace("'daily_loss_limit': 3.0", "'daily_loss_limit': 999.0")
        modified = True
        print("  + daily_loss_limit: SIN LIMITE")

    # 5. max_daily_trades relajado
    if '"max_daily_trades": 3' in content:
        content = content.replace('"max_daily_trades": 3', '"max_daily_trades": 15')
        modified = True
        print("  + max_daily_trades: 3 -> 15")
    elif "'max_daily_trades': 3" in content:
        content = content.replace("'max_daily_trades': 3", "'max_daily_trades': 15")
        modified = True
        print("  + max_daily_trades: 3 -> 15")

    # 6. min_score relajado
    if '"min_score": 4' in content:
        content = content.replace('"min_score": 4', '"min_score": 2')
        modified = True
        print("  + min_score: 4 -> 2")
    elif "'min_score': 4" in content:
        content = content.replace("'min_score': 4", "'min_score': 2")
        modified = True
        print("  + min_score: 4 -> 2")

    # 7. check_interval rapido
    if '"check_interval": 60' in content:
        content = content.replace('"check_interval": 60', '"check_interval": 30')
        modified = True
        print("  + check_interval: 60 -> 30")

    # 8. Cooldown reducido
    if '"min_timeframe_between_signals": 300' in content:
        content = content.replace('"min_timeframe_between_signals": 300', '"min_timeframe_between_signals": 60')
        modified = True
        print("  + cooldown: 300 -> 60")

    # 9. Agregar XAUUSD a PAIR_SESSIONS
    if 'PAIR_SESSIONS' in content and 'XAUUSD' not in content:
        # Agregar antes del ultimo }
        last_brace = content.rfind('}')
        if last_brace > 0:
            content = content[:last_brace] + '    "XAUUSD": ["london", "new_york"],\n' + content[last_brace:]
            modified = True
            print("  + XAUUSD PAIR_SESSIONS")

    # 10. RISK_PER_PAIR para XAUUSD
    if '"XAUUSD": {"sl_pips":' not in content:
        if 'RISK_PER_PAIR' in content:
            last_brace = content.rfind('}')
            if last_brace > 0:
                content = content[:last_brace] + '    "XAUUSD": {"sl_pips": 25, "tp_pips": 25},\n' + content[last_brace:]
                modified = True
                print("  + XAUUSD RISK_PER_PAIR")

    # 11. MT5_TIMEFRAME y DATA_DIR
    if 'MT5_TIMEFRAME' not in content:
        content += '\nMT5_TIMEFRAME = 15\n'
        modified = True
        print("  + MT5_TIMEFRAME agregado")

    if 'DATA_DIR' not in content:
        content += '\nDATA_DIR = os.path.join(BASE_DIR, "data")\nos.makedirs(DATA_DIR, exist_ok=True)\n'
        modified = True
        print("  + DATA_DIR agregado")

    if modified:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("  config.py parcheado OK")
    else:
        print("  config.py ya esta actualizado")

    return True


def main():
    print("=" * 55)
    print("  ACTUALIZACION v8.2 — MTF + SIN LIMITE PERDIDAS")
    print("  TradingPro24-7 Bot")
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
    print("  strategy.py: v8.2 MTF (M5 dir + M1 entrada)")
    print("  main.py: v8.2 (info MTF en senales)")
    print("  config.py: SIN limite de perdidas + XAUUSD")
    print("  data_feed.py: Timeframe por par")
    print("  telegram_bot.py: Bloque codigo copiable")
    print()

    if all_ok:
        print("ACTUALIZACION v8.2 COMPLETADA!")
        print("Ejecuta: python main.py")
    else:
        print("ACTUALIZACION CON ERRORES — Revisa arriba")


if __name__ == "__main__":
    main()
