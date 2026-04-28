"""
════════════════════════════════════════════════════════════════
  ACTUALIZACION v8.3 ICT PRO — TradingPro24-7
  ═══ S/R Automatico + Flip + Mercado Adaptativo ═══

  NOVEDADES v8.3:
  - Deteccion de mercado: ALCISTA / BAJISTA / LATERAL
  - ALCISTA: solo compras a favor de tendencia
  - BAJISTA: solo ventas a favor de tendencia
  - LATERAL: compras en soporte + ventas en resistencia
  - S/R Flip: resistencia rota se convierte en soporte
  - Graficos con lineas S/R dibujadas (verde/rojo/amarillo)
  - Auto-ejecucion mejorada en MT5
  - Corregido: NO permite ventas en tendencia alcista

  ARCHIVOS ACTUALIZADOS:
  - strategy.py   → v8.3 (S/R + Mercado Adaptativo)
  - main.py       → v8.3 (S/R levels al grafico + auto-trade fix)
  - chart_generator.py → v8.3 (lineas S/R + flip)
  - telegram_bot.py → v8.3 (condicion mercado + S/R info)

  USO: python actualizar_v83.py
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
        backup = filename + ".bak_v82"
        shutil.copy2(filename, backup)
        print("  Backup: {} -> {}".format(filename, backup))

def main():
    print("=" * 55)
    print("  ACTUALIZACION v8.3 ICT PRO — TradingPro24-7")
    print("  S/R + Mercado Adaptativo + S/R Flip")
    print("=" * 55)
    print()

    print("[1/3] Creando backups...")
    for f in FILES:
        backup_file(f)
    print()

    print("[2/3] Descargando archivos v8.3...")
    ok = 0
    for f in FILES:
        if download_file(f):
            ok += 1
    print()

    print("[3/3] Resultado: {}/{} archivos actualizados".format(ok, len(FILES)))
    print()
    print("ARCHIVOS ACTUALIZADOS:")
    print("  strategy.py       → S/R + Flip + Mercado Adaptativo")
    print("  main.py           → Chart con S/R lines + Auto-trade fix")
    print("  chart_generator.py→ Lineas S/R (verde/rojo/amarillo)")
    print("  telegram_bot.py   → Info mercado + S/R en signal")
    print()
    print("NO TOCA: config.py (tus API keys estan a salvo)")
    print()
    print("EJECUTA AHORA: python main.py")
    print("=" * 55)

if __name__ == "__main__":
    main()
