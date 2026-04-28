# ═══════════════════════════════════════════════════════════════
#  ACTUALIZACION v8.1 MOMENTUM ICT
#  ═══ EJECUTA ESTE SCRIPT: python actualizar_v81.py ═══
#
#  Que cambia:
#  - strategy.py → Momentum ICT (score 2/4, sigue direccion)
#  - main.py → v8.1 (timeframe por par, intervalo 30s)
#  - data_feed.py → Soporte timeframe por par (M1/M15)
#  - telegram_bot.py → v8.1 (bloque de codigo copiable)
#  - risk_manager.py → XAUUSD incluido
#  - chart_generator.py → M1 + M15
#  - config.py → Parchea para agregar XAUUSD + params relajados
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
    """Crea backup del archivo."""
    if os.path.exists(filepath):
        backup = filepath + ".bak_v81"
        shutil.copy2(filepath, backup)
        print("  Backup: {}".format(backup))


def download_file(filename):
    """Descarga archivo desde GitHub."""
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
    """Parchea config.py para agregar XAUUSD y params v8.1."""
    config_path = "config.py"
    if not os.path.exists(config_path):
        print("  ERROR: config.py no encontrado!")
        return False

    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    modified = False

    # 1. Agregar XAUUSD a FOREX_PAIRS si no esta
    if '"XAUUSD"' not in content and "'XAUUSD'" not in content:
        # Buscar el cierre de FOREX_PAIRS
        if 'FOREX_PAIRS' in content:
            content = content.replace(
                'FOREX_PAIRS = [',
                'FOREX_PAIRS = [\n    "XAUUSD",'
            )
            modified = True
            print("  + XAUUSD agregado a FOREX_PAIRS")
        else:
            content += '\nFOREX_PAIRS = ["XAUUSD"]\n'
            modified = True
            print("  + FOREX_PAIRS creado con XAUUSD")

    # 2. Agregar XAUUSD a pip_values
    if '"XAUUSD": 0.10' not in content and "'XAUUSD': 0.10" not in content:
        if '"pip_values"' in content:
            content = content.replace(
                '"pip_values": {',
                '"pip_values": {\n        "XAUUSD": 0.10,'
            )
            modified = True
            print("  + XAUUSD pip_value=0.10")
        elif "'pip_values'" in content:
            content = content.replace(
                "'pip_values': {",
                "'pip_values': {\n        'XAUUSD': 0.10,"
            )
            modified = True
            print("  + XAUUSD pip_value=0.10")

    # 3. Agregar XAUUSD a digits
    if '"XAUUSD": 2' not in content and "'XAUUSD': 2" not in content:
        if '"digits"' in content:
            content = content.replace(
                '"digits": {',
                '"digits": {\n        "XAUUSD": 2,'
            )
            modified = True
            print("  + XAUUSD digits=2")
        elif "'digits'" in content:
            content = content.replace(
                "'digits': {",
                "'digits': {\n        'XAUUSD': 2,"
            )
            modified = True
            print("  + XAUUSD digits=2")

    # 4. Relajar max_daily_trades
    if '"max_daily_trades": 3' in content:
        content = content.replace('"max_daily_trades": 3', '"max_daily_trades": 15')
        modified = True
        print("  + max_daily_trades: 3 -> 15")
    elif "'max_daily_trades': 3" in content:
        content = content.replace("'max_daily_trades': 3", "'max_daily_trades': 15")
        modified = True
        print("  + max_daily_trades: 3 -> 15")

    # 5. Relajar min_score
    if '"min_score": 4' in content:
        content = content.replace('"min_score": 4', '"min_score": 2')
        modified = True
        print("  + min_score: 4 -> 2")
    elif "'min_score': 4" in content:
        content = content.replace("'min_score': 4", "'min_score': 2")
        modified = True
        print("  + min_score: 4 -> 2")

    # 6. Agregar XAUUSD a PAIR_SESSIONS
    if '"XAUUSD"' in content and "'XAUUSD'" in content:
        if 'PAIR_SESSIONS' in content and '"XAUUSD"' not in content.split('PAIR_SESSIONS')[1][:200]:
            content = content.replace(
                '}',
                '    "XAUUSD": ["london", "new_york"],\n}',
                1
            )
            modified = True
            print("  + XAUUSD PAIR_SESSIONS")

    # 7. Reducir check_interval a 30s
    if '"check_interval": 60' in content:
        content = content.replace('"check_interval": 60', '"check_interval": 30')
        modified = True
        print("  + check_interval: 60 -> 30")

    # 8. Reducir cooldown a 120s
    if '"min_timeframe_between_signals": 300' in content:
        content = content.replace('"min_timeframe_between_signals": 300', '"min_timeframe_between_signals": 120')
        modified = True
        print("  + cooldown: 300 -> 120")

    # 9. Agregar RISK_PER_PAIR para XAUUSD si no existe
    if '"XAUUSD": {"sl_pips":' not in content:
        if 'RISK_PER_PAIR' in content:
            content = content.replace(
                '}',
                '    "XAUUSD": {"sl_pips": 25, "tp_pips": 25},\n}',
                1
            )
            modified = True
            print("  + XAUUSD RISK_PER_PAIR")

    # 10. Asegurar que existan MT5_TIMEFRAME y DATA_DIR
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
        print("  config.py parcheado correctamente")
    else:
        print("  config.py ya esta actualizado")

    return True


def main():
    print("=" * 55)
    print("  ACTUALIZACION v8.1 — MOMENTUM ICT")
    print("  TradingPro24-7 Bot")
    print("=" * 55)
    print()

    # Paso 1: Descargar archivos nuevos
    print("[1/3] Descargando archivos actualizados...")
    all_ok = True
    for filename in FILES_TO_DOWNLOAD:
        backup_file(filename)
        if not download_file(filename):
            all_ok = False

    print()

    # Paso 2: Parchear config.py
    print("[2/3] Parcheando config.py (preservando tus keys)...")
    patch_config()
    print()

    # Paso 3: Resumen
    print("[3/3] Resumen de cambios:")
    print("  - strategy.py: Momentum ICT (score 2/4)")
    print("  - main.py: XAUUSD M1 + Forex M15, intervalo 30s")
    print("  - data_feed.py: Timeframe por par")
    print("  - telegram_bot.py: Bloque de codigo copiable")
    print("  - risk_manager.py: XAUUSD incluido")
    print("  - chart_generator.py: M1 + M15")
    print("  - config.py: XAUUSD + params relajados")
    print()

    if all_ok:
        print("ACTUALIZACION COMPLETADA!")
        print("Ejecuta: python main.py")
    else:
        print("ACTUALIZACION CON ERRORES — Revisa los mensajes arriba")


if __name__ == "__main__":
    main()
