"""
Fix config.py para estrategia v8.0 Momentum Following
Solo cambia los valores de riesgo y SL/TP, NO toca tokens
Ejecutar: venv312\Scripts\python fix_config_v8.py
"""

import os
import shutil
import re

print("=" * 50)
print("  Fix config.py - Estrategia v8.0")
print("  Momentum: SI SUBE compra, SI BAJA vende")
print("  R:R 1:1 | 15 pips TP | 15 pips SL")
print("=" * 50)
print("")

config_file = "config.py"

# Backup
shutil.copy2(config_file, "config_backup_v7.py")
print("Backup: config_backup_v7.py")

with open(config_file, "r", encoding="utf-8") as f:
    contenido = f.read()

# 1. RISK sl_pips = 15
contenido = re.sub(
    r'"sl_pips":\s*\d+,',
    '"sl_pips": 15,',
    contenido
)
# 2. RISK tp_pips = 15
contenido = re.sub(
    r'"tp_pips":\s*\d+,',
    '"tp_pips": 15,',
    contenido
)
# 3. RISK rr_ratio = 1.0
contenido = re.sub(
    r'"rr_ratio":\s*[\d.]+,',
    '"rr_ratio": 1.0,',
    contenido
)
# 4. RISK max_daily_trades = 8
contenido = re.sub(
    r'"max_daily_trades":\s*\d+,',
    '"max_daily_trades": 8,',
    contenido
)
# 5. RISK daily_loss_limit = 4.0
contenido = re.sub(
    r'"daily_loss_limit":\s*[\d.]+,',
    '"daily_loss_limit": 4.0,',
    contenido
)

# 6. RISK_PER_PAIR: todos a 15 pips
contenido = re.sub(
    r'"(EURUSD|AUDUSD|USDCAD|USDCHF)":\s*\{"sl_pips":\s*\d+,\s*"tp_pips":\s*\d+\}',
    r'"\1": {"sl_pips": 15, "tp_pips": 15}',
    contenido
)
contenido = re.sub(
    r'"USDJPY":\s*\{"sl_pips":\s*\d+,\s*"tp_pips":\s*\d+\}',
    r'"USDJPY": {"sl_pips": 15, "tp_pips": 15}',
    contenido
)
contenido = re.sub(
    r'"GBPUSD":\s*\{"sl_pips":\s*\d+,\s*"tp_pips":\s*\d+\}',
    r'"GBPUSD": {"sl_pips": 18, "tp_pips": 18}',
    contenido
)

# 7. range_mode sl_pips = 15, tp_pips = 15
contenido = re.sub(
    r'("range_mode".*?"tp_pips":\s*)\d+(\s*.*?"sl_pips":\s*)\d+',
    r'\g<1>15\g<2>15',
    contenido,
    flags=re.DOTALL
)

# 8. AI_VISION max_daily_calls = 50
contenido = re.sub(
    r'"max_daily_calls":\s*\d+,',
    '"max_daily_calls": 50,',
    contenido
)
# 9. AI_VISION min_confidence = 0.65
contenido = re.sub(
    r'"min_confidence":\s*[\d.]+,',
    '"min_confidence": 0.65,',
    contenido
)

# 10. BOT min_timeframe_between_signals = 180
contenido = re.sub(
    r'"min_timeframe_between_signals":\s*\d+,',
    '"min_timeframe_between_signals": 180,',
    contenido
)

with open(config_file, "w", encoding="utf-8") as f:
    f.write(contenido)

print("config.py actualizado!")
print("")
print("Cambios aplicados:")
print("  SL: 15 pips (era 18)")
print("  TP: 15 pips (era 45)")
print("  R:R: 1:1 (era 1:2.5)")
print("  Max trades/dia: 8 (era 3)")
print("  Perdida max diaria: 4% (era 3%)")
print("  AI confidence: 65% (era 70%)")
print("  AI max calls: 50 (era 30)")
print("")
print("Tokens: NO MODIFICADOS")
print("")
print("Reinicia el bot:")
print("  venv312\Scripts\python main.py")

input("")
