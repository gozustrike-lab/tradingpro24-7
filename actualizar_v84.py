"""
════════════════════════════════════════════════════════════════
  ACTUALIZACION v8.4 ICT PRO + ONDAS — TradingPro24-7
  ═══ Pattern Recognition + Agotamiento + Impulsivo ═══

  NOVEDADES v8.4:
  - Detecta "montañitas" (ondas) del precio automáticamente
  - Cuenta cuántas veces se repite el patrón (2, 3, 4+)
  - AGOTAMIENTO: la 4ta onda falla = reversión
  - IMPULSIVO: subida/caída fuerte > corrección débil
  - REPETICION: mismo patrón 2-3x = probable continuación
  - Graficos con ondas numeradas y conectadas
  - Telegram muestra info de patrón

  ARCHIVOS ACTUALIZADOS:
  - strategy.py        → v8.4 (Wave Pattern Recognition)
  - main.py            → v8.4 (wave_data al chart)
  - chart_generator.py → v8.4 (ondas numeradas)
  - telegram_bot.py    → v8.4 (info patron + agotamiento)

  USO: python actualizar_v84.py
════════════════════════════════════════════════════════════════
"""

import os
import urllib.request
import shutil

REPO = "gozustrike-lab/tradingpro24-7"
BRANCH = "main"
BASE_URL = "https://raw.githubusercontent.com/{}/{}/".format(REPO, BRANCH)

FILES = [
    "strategy.py",
    "main.py",
    "chart_generator.py",
    "telegram_bot.py",
]

def download_file(filename):
    url = BASE_URL + filename
    print("  Descargando {} ...".format(filename))
    try:
        urllib.request.urlretrieve(url, filename)
        print("  OK: {}".format(filename))
        return True
    except Exception as e:
        print("  ERROR descargando {}: {}".format(filename, e))
        return False

def backup_file(filename):
    if os.path.exists(filename):
        backup = filename + ".bak_v83"
        shutil.copy2(filename, backup)
        print("  Backup: {} -> {}".format(filename, backup))

def main():
    print("=" * 55)
    print("  ACTUALIZACION v8.4 ICT PRO + ONDAS")
    print("  Pattern Recognition + Agotamiento + Impulsivo")
    print("=" * 55)
    print()

    print("[1/3] Creando backups...")
    for f in FILES:
        backup_file(f)
    print()

    print("[2/3] Descargando archivos v8.4...")
    ok = 0
    for f in FILES:
        if download_file(f):
            ok += 1
    print()

    print("[3/3] Resultado: {}/{} archivos actualizados".format(ok, len(FILES)))
    print()
    print("ARCHIVOS ACTUALIZADOS:")
    print("  strategy.py       → Wave Pattern Recognition")
    print("  main.py           → wave_data al grafico + signal")
    print("  chart_generator.py→ Ondas numeradas + conectadas")
    print("  telegram_bot.py   → Info patron + agotamiento")
    print()
    print("NO TOCA: config.py (tus API keys estan a salvo)")
    print()
    print("EJECUTA AHORA: python main.py")
    print("=" * 55)

if __name__ == "__main__":
    main()
