import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import config
import mt5_client

# ─────────────────────────────────────────────
# UTILIDADES TÉCNICAS
# ─────────────────────────────────────────────

def calculate_atr(df, period=14):
    """Calcula el Average True Range."""
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()


def mark_fvg(df):
    """
    Detecta Fair Value Gaps (FVG) alcistas y bajistas.
    FVG alcista: Low[i] > High[i-2]  → hueco al alza
    FVG bajista: Low[i-2] > High[i]  → hueco a la baja
    Devuelve el mismo DataFrame con columnas FVG_Bull / FVG_Bear añadidas.
    """
    atr = calculate_atr(df, config.ATR_PERIOD)
    fvg_minimo = atr * config.ATR_MULTIPLIER_FVG

    df = df.copy()
    df['ATR'] = atr

    df['Gap_Bull_Size'] = df['Low'] - df['High'].shift(2)
    df['FVG_Bull'] = (df['Low'] > df['High'].shift(2)) & (df['Gap_Bull_Size'] > fvg_minimo)

    df['Gap_Bear_Size'] = df['Low'].shift(2) - df['High']
    df['FVG_Bear'] = (df['Low'].shift(2) > df['High']) & (df['Gap_Bear_Size'] > fvg_minimo)

    return df


# ─────────────────────────────────────────────
# SESGO CRT (Candle Range Theory) MULTI-TF
# ─────────────────────────────────────────────

def get_crt_bias(df_h4, df_h2=None, df_h1=None):
    """
    Determina el sesgo CRT usando la jerarquía HTF → LTF:
      H4 vota primero (peso mayor), luego H2 y H1.
    Retorna:  1 = alcista  |  -1 = bajista  |  0 = neutral
    """
    votes = []

    for df in [df_h4, df_h2, df_h1]:
        if df is None or len(df) < 21:
            continue
        last = df.iloc[-2]
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-2]
        if last['Close'] > last['Open'] and last['Close'] > ema20:
            votes.append(1)
        elif last['Close'] < last['Open'] and last['Close'] < ema20:
            votes.append(-1)
        else:
            votes.append(0)

    if not votes:
        return 0

    # Consenso: si la mayoría apunta en una dirección, ese es el sesgo
    total = sum(votes)
    if total > 0:
        return 1
    elif total < 0:
        return -1
    return 0


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL DE ANÁLISIS
# ─────────────────────────────────────────────

def analyze_smc(df_entry, df_h4=None, df_h2=None, df_h1=None):
    """
    Analiza una temporalidad de entrada (15m, 1H, 2H o 4H) buscando:
      1. FVG  – Fair Value Gap fresco
      2. IFVG – Inversión de FVG (FVG roto y re-testeado)

    El sesgo CRT se construye con H4 > H2 > H1 como filtro HTF.
    El TP se fija exactamente en MIN_TP_USD (15 USD).

    Retorna dict: {signal, entry, sl, tp}
    """
    df = mark_fvg(df_entry)
    crt_bias = get_crt_bias(df_h4, df_h2, df_h1)

    last_idx = -2       # última vela cerrada
    row3 = df.iloc[last_idx]
    row1 = df.iloc[last_idx - 2]

    signal = None
    entry  = 0.0
    sl     = 0.0
    tp     = 0.0
    buffer = getattr(config, 'SL_BUFFER_PIPS', 10.0)

    # ── 1. FVG FRESCO ────────────────────────────────────────────────────────
    if row3['FVG_Bull'] and crt_bias >= 0:
        signal = "BUY_LIMIT"
        entry  = row1['High']
        sl     = row1['Low'] - buffer

    elif row3['FVG_Bear'] and crt_bias <= 0:
        signal = "SELL_LIMIT"
        entry  = row1['Low']
        sl     = row1['High'] + buffer

    # ── 2. IFVG – Inversión de FVG ───────────────────────────────────────────
    if not signal:
        cierre_actual = row3['Close']

        for i_back in range(3, 20):
            idx_ana = last_idx - i_back
            if idx_ana - 2 < 0:
                break

            v3 = df.iloc[idx_ana]
            v1 = df.iloc[idx_ana - 2]

            # FVG alcista pasado → IFVG bajista si el precio lo rompe a la baja
            if v3.get('FVG_Bull', False):
                base   = v1['Low']
                techo  = v1['High']
                if cierre_actual < base and crt_bias <= 0:
                    signal = "SELL_LIMIT"
                    entry  = base           # resistencia convertida (antiguo soporte)
                    sl     = techo + buffer
                    break

            # FVG bajista pasado → IFVG alcista si el precio lo rompe al alza
            elif v3.get('FVG_Bear', False):
                base   = v1['Low']
                techo  = v1['High']
                if cierre_actual > techo and crt_bias >= 0:
                    signal = "BUY_LIMIT"
                    entry  = techo          # soporte convertido (antigua resistencia)
                    sl     = base - buffer
                    break

    # ── 3. TP FIJO = +15 USD ─────────────────────────────────────────────────
    if signal:
        contract_size = mt5_client.get_contract_size(config.SYMBOL)
        lot_size      = config.LOT_SIZE
        tp_usd        = getattr(config, 'MIN_TP_USD', 15.0)   # siempre 15 USD

        # Distancia en precio que produce exactamente tp_usd de ganancia
        price_dist = tp_usd / (lot_size * contract_size)

        if signal == "BUY_LIMIT":
            tp = entry + price_dist
        elif signal == "SELL_LIMIT":
            tp = entry - price_dist

    return {
        "signal": signal,
        "entry":  entry,
        "sl":     sl,
        "tp":     tp
    }
