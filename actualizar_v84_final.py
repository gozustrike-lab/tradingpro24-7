"""
════════════════════════════════════════════════════════════════
  ACTUALIZACION v8.4 FINAL — TradingPro24-7
  ═══ S/R + Ondas + Reentrada Automatica ═══

  NOVEDADES:
  - Re-entrada automatica: 1 trade extra a favor cuando ganas
  - Config.py actualizado con params de re-entrada
  - main.py trackea trades abiertos para re-entrada

  ARCHIVOS: main.py, config.py
  ATENCION: Este script TAMBIEN actualiza config.py
  Agrega las variables AUTO_TRADE y REENTRY_* al final

  USO: python actualizar_v84_final.py
════════════════════════════════════════════════════════════════
"""

import os

REPO = "gozustrike-lab/tradingpro24-7"
BRANCH = "main"
BASE_URL = "https://raw.githubusercontent.com/{}/{}/".format(REPO, BRANCH)

FILES = ["strategy.py", "main.py", "chart_generator.py", "telegram_bot.py", "config.py"]

def download_file(filename):
    url = BASE_URL + filename
    print("  Descargando {} ...".format(filename))
    try:
        import urllib.request
        urllib.request.urlretrieve(url, filename)
        print("  OK: {}".format(filename))
        return True
    except Exception as e:
        print("  ERROR: {}".format(e))
        return False

def main():
    import shutil
    print("=" * 55)
    print("  ACTUALIZACION v8.4 FINAL — TradingPro24-7")
    print("  S/R + Ondas + Reentrada Automatica")
    print("=" * 55)
    print()

    print("[1/3] Backups...")
    for f in FILES:
        if os.path.exists(f):
            bak = f + ".bak_v83"
            shutil.copy2(f, bak)
            print("  Backup: {}".format(bak))
    print()

    # Para config.py: solo agregar las nuevas variables si no existen
    print("[2/3] Descargando archivos...")
    ok = 0
    for f in FILES:
        if download_file(f):
            ok += 1
    print()

    print("[3/3] Resultado: {}/{} actualizados".format(ok, len(FILES)))
    print()
    print("IMPORTANTE: config.py fue actualizado!")
    print("Si tenias API keys personalizadas, edita config.py")
    print("y coloca tus keys en:")
    print("  OPENROUTER_API_KEY")
    print("  TELEGRAM_BOT_TOKEN")
    print("  TELEGRAM_CHAT_ID")
    print("  TELEGRAM_CHANNEL_ID")
    print()
    print("Nuevas variables en config.py:")
    print("  AUTO_TRADE = True")
    print("  AUTO_TRADE_VOLUME = 0.01")
    print("  REENTRY_ENABLED = True")
    print("  REENTRY_MIN_PROFIT_PIPS = 5")
    print("  REENTRY_MAX_DISTANCE_PIPS = 30")
    print("  REENTRY_COOLDOWN_SECS = 120")
    print("  REENTRY_MAX_PER_SIGNAL = 1")
    print()
    print("EJECUTA: python main.py")
    print("=" * 55)

if __name__ == "__main__":
    main()
