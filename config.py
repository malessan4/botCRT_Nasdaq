import os
from dotenv import load_dotenv

load_dotenv() # Carga las variables del archivo .env

import MetaTrader5 as mt5

# Configuración General
SYMBOL = "USTEC_x100m" # Ajustar al nombre exacto de tu broker para Nasdaq (ej. "NAS100", "USTEC", "USTEC_x100m")
LOT_SIZE = 0.09 # Apalancamiento 0.09 lotes
MAGIC_NUMBER = int(os.getenv("MAGIC_NUMBER", 123457)) # Identificador único para el bot de Nasdaq
DEVIATION = 50 # Desviación permitida (slippage) ampliada por la volatilidad de Nasdaq

# Temporalidades a monitorear
TIMEFRAMES = [mt5.TIMEFRAME_M15, mt5.TIMEFRAME_H1, mt5.TIMEFRAME_H2, mt5.TIMEFRAME_H4]

# Gestión de Riesgo (Risk Management)
RISK_REWARD_RATIO = 2.0 # TP por defecto si no hay liquidez cercana
HTF_BIAS_TF = mt5.TIMEFRAME_H4  # Temporalidad base para el sesgo CRT (HTF bias)
MOVE_TO_BREAKEVEN_RATIO = 1.0 # Mover SL a precio de entrada cuando el precio alcance 1:1 R/R
SL_BUFFER_PIPS = 10.0 # Distancia extra de respiro para el Stop Loss (ajustado a Nasdaq)
BREAKEVEN_PLUS_USD = 1.0 # Dólares extra a asegurar en el BreakEven
MIN_TP_USD = 15.0 # Take Profit fijo: exactamente +15 USD por operación
MAX_TP_USD = 15.0 # Take Profit fijo: exactamente +15 USD por operación
MAX_PENDING_ORDERS = 3 # Máximo 3 órdenes (pendientes + abiertas) en el mismo nivel de precio
PENDING_ORDER_TIMEOUT_MINUTES = 30 # Tiempo de espera mínimo antes de colocar otra orden pendiente
PENDING_ORDER_EXPIRY_HOURS = 8.0 # Tiempo en horas para cancelar automáticamente órdenes pendientes no ejecutadas
ORDER_COOLDOWN_MINUTES = 30.0 # Minutos de espera antes de permitir otra orden Limit duplicada

# Configuración de Estrategia SMC
ATR_PERIOD = 14
ATR_MULTIPLIER_FVG = 0.2 # Extremadamente relajado para permitir muchas entradas
KILLZONE_START_HOUR = 0 # Operar todo el día
KILLZONE_END_HOUR = 24 # Sin límite de horario
SMA_BODY_PERIOD = 20
OB_BODY_MULTIPLIER = 2.0

TELEGRAM_ENABLED = False  # ← Cambiar a True para reactivar las notificaciones
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MAGIC_NUMBER = int(os.getenv("MAGIC_NUMBER", 123457))
