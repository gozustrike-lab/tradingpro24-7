# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — SETUP & DIAGNÓSTICO
#  Verifica que todo esté configurado correctamente
# ═══════════════════════════════════════════════════════════════

import sys
import os
import importlib

def print_header():
    print("\n" + "=" * 55)
    print("  TRADINGPRO24-7 — DIAGNÓSTICO DEL SISTEMA")
    print("=" * 55 + "\n")


def check_python():
    """Verifica versión de Python."""
    version = sys.version_info
    print(f"  Python: {version.major}.{version.minor}.{version.micro}", end=" ")

    if version.major == 3 and version.minor == 12:
        print("OK")
        return True
    elif version.major == 3 and version.minor <= 11:
        print("OK")
        return True
    else:
        print("ADVERTENCIA - Se recomienda Python 3.12 o 3.11")
        return False


def check_dependencies():
    """Verifica que todas las dependencias estén instaladas."""
    print("\n  [2/5] Dependencias:")

    dependencies = [
        ("MetaTrader5", "mt5"),
        ("requests", "requests"),
        ("pandas", "pd"),
        ("numpy", "np"),
        ("matplotlib", "mpl"),
        ("pytz", "pytz"),
    ]

    all_ok = True
    for name, alias in dependencies:
        try:
            importlib.import_module(name.replace("-", "_"))
            print(f"    {name} OK")
        except ImportError:
            print(f"    {name} FALTA - pip install {name}")
            all_ok = False

    return all_ok


def check_openrouter():
    """Verifica API key de OpenRouter."""
    print("\n  [3/5] OpenRouter API Key:")

    try:
        with open("config.py", "r", encoding="utf-8") as f:
            content = f.read()

        if "TU_API_KEY_AQUI" in content and "openrouter_api_key" in content:
            print("    NO configurada")
            print("    -> Obtén tu key en: https://openrouter.ai/keys")
            return False
        else:
            key = content.split("OPENROUTER_API_KEY")[1].split("=")[1].strip().strip('"').strip("'")
            masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
            print(f"    Configurada: {masked}")
            return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def check_telegram():
    """Verifica credenciales de Telegram."""
    print("\n  [4/5] Telegram Bot:")

    try:
        with open("config.py", "r", encoding="utf-8") as f:
            content = f.read()

        has_token = "TU_BOT_TOKEN_AQUI" not in content
        has_chat = "TU_CHAT_ID_AQUI" not in content

        if has_token and has_chat:
            print("    Bot Token: OK")
            print("    Chat ID: OK")
            return True
        elif not has_token and not has_chat:
            print("    Bot Token: NO configurado")
            print("    Chat ID: NO configurado")
            print("    -> Token: @BotFather -> /newbot")
            print("    -> Chat ID: @userinfobot -> /start")
            return False
        elif not has_token:
            print("    Bot Token: NO configurado")
            print("    -> @BotFather -> /newbot")
            return False
        else:
            print("    Bot Token: OK")
            print("    Chat ID: NO configurado")
            print("    -> @userinfobot -> /start")
            return False
    except Exception as e:
        print(f"    Error: {e}")
        return False


def check_mt5():
    """Verifica conexión con MetaTrader 5."""
    print("\n  [5/5] MetaTrader 5:")

    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            error_code, error_msg = mt5.last_error()

            if error_code == -10005:
                print(f"    ERROR: IPC Timeout ({error_code})")
                print("    Soluciones:")
                print("    1. Ejecutar CMD como Administrador")
                print("    2. Verificar que MT5 sea de 64-bit (Ayuda > Acerca de)")
                print("    3. Mover esta carpeta fuera de OneDrive")
                print("       A: C:\\Users\\fabio\\trading-bot-hibrido")
                print("    4. Cerrar MT5 completamente y reabrir")
            else:
                print(f"    ERROR: {error_code} - {error_msg}")
                print("    Asegúrate de que MT5 esté abierto y logueado")

            mt5.shutdown()
            return False

        account = mt5.account_info()

        if account:
            print(f"    Conectado: SI")
            print(f"    Cuenta: {account.login}")
            print(f"    Balance: ${account.balance:.2f}")
            print(f"    Servidor: {account.server}")
            print(f"    Moneda: {account.currency}")
            result = True
        else:
            print("    Conectado: SI (pero sin cuenta logueada)")
            print("    Abre MT5 y logueate con tu cuenta")
            result = False

        mt5.shutdown()
        return result

    except ImportError:
        print("    MetaTrader5 NO instalado")
        print("    -> pip install MetaTrader5")
        return False
    except Exception as e:
        print(f"    Error inesperado: {e}")
        return False


def main():
    """Ejecuta todas las verificaciones."""
    print_header()

    results = []

    print("  [1/5] Python:")
    results.append(check_python())

    results.append(check_dependencies())
    results.append(check_openrouter())
    results.append(check_telegram())
    results.append(check_mt5())

    # Resumen
    print("\n" + "=" * 55)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"  RESULTADO: {passed}/{total} - TODO OK!")
        print("  Ejecuta: python main.py")
    elif passed >= 4:
        print(f"  RESULTADO: {passed}/{total} - Casi listo")
        print("  Revisa los puntos marcados arriba")
    elif passed >= 3:
        print(f"  RESULTADO: {passed}/{total} - Faltan configuraciones")
        print("  Revisa las dependencias y credenciales")
    else:
        print(f"  RESULTADO: {passed}/{total} - Se requiere setup")
        print("  Sigue las instrucciones de cada sección")

    print("=" * 55 + "\n")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
