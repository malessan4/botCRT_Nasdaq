import time
import MetaTrader5 as mt5
import config
import mt5_client
import strategy
import telegram_utils

TF_MAPPING = {
    mt5.TIMEFRAME_M15: "M15",
    mt5.TIMEFRAME_H1:  "H1",
    mt5.TIMEFRAME_H2:  "H2",
    mt5.TIMEFRAME_H4:  "H4"
}

# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE POSICIONES ABIERTAS (Breakeven)
# ─────────────────────────────────────────────────────────────────────────────

def manage_open_positions():
    """
    Revisa las posiciones abiertas del bot y mueve el SL a Breakeven +1 USD
    cuando el precio alcanza la relación 1:1 riesgo/recompensa.
    """
    positions = mt5_client.get_open_positions()
    for pos in positions:
        ticket      = pos.ticket
        symbol      = pos.symbol
        order_type  = pos.type
        price_open  = pos.price_open
        sl          = pos.sl
        current_px  = pos.price_current

        contract_size = mt5_client.get_contract_size(symbol)
        # Offset en precio equivalente a BREAKEVEN_PLUS_USD (1 USD)
        be_offset = getattr(config, 'BREAKEVEN_PLUS_USD', 1.0) / (config.LOT_SIZE * contract_size)

        if order_type == mt5.ORDER_TYPE_BUY:
            risk = price_open - sl
            if risk <= 0:
                continue
            target_1_1 = price_open + risk
            be_price   = price_open + be_offset

            if current_px >= target_1_1 and sl < be_price:
                print(f"[{symbol}] BreakEven activado en BUY {ticket} → SL → {be_price:.3f}")
                mt5_client.modify_position_sl(ticket, symbol, be_price)
                telegram_utils.enviar_telegram(
                    f"🛡 *BreakEven Activado*\nSímbolo: {symbol}\nOrden: BUY {ticket}\n"
                    f"Ganancia asegurada: +{config.BREAKEVEN_PLUS_USD} USD"
                )

        elif order_type == mt5.ORDER_TYPE_SELL:
            risk = sl - price_open
            if risk <= 0:
                continue
            target_1_1 = price_open - risk
            be_price   = price_open - be_offset

            if current_px <= target_1_1 and sl > be_price:
                print(f"[{symbol}] BreakEven activado en SELL {ticket} → SL → {be_price:.3f}")
                mt5_client.modify_position_sl(ticket, symbol, be_price)
                telegram_utils.enviar_telegram(
                    f"🛡 *BreakEven Activado*\nSímbolo: {symbol}\nOrden: SELL {ticket}\n"
                    f"Ganancia asegurada: +{config.BREAKEVEN_PLUS_USD} USD"
                )


# ─────────────────────────────────────────────────────────────────────────────
# LIMPIEZA DE ÓRDENES PENDIENTES CADUCADAS
# ─────────────────────────────────────────────────────────────────────────────

def clean_expired_pending_orders():
    """
    Revisa las órdenes pendientes y elimina aquellas que lleven más de
    PENDING_ORDER_EXPIRY_HOURS (ej. 8 horas) sin haberse ejecutado.
    """
    pending = mt5_client.get_pending_orders()
    if not pending:
        return
        
    current_time = time.time()
    expiry_seconds = getattr(config, 'PENDING_ORDER_EXPIRY_HOURS', 8.0) * 3600
    
    for order in pending:
        if order.symbol == config.SYMBOL:
            if (current_time - order.time_setup) > expiry_seconds:
                print(f"[{config.SYMBOL}] Orden pendiente {order.ticket} expirada tras {getattr(config, 'PENDING_ORDER_EXPIRY_HOURS', 8.0)} horas. Eliminando...")
                res = mt5_client.cancel_pending_order(order.ticket)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    safe_sym = config.SYMBOL.replace('_', '\\_')
                    telegram_utils.enviar_telegram(f"🗑 *Orden Expirada*\nSímbolo: {safe_sym}\nSe eliminó la orden {order.ticket} por superar el límite de tiempo en espera.")

# ─────────────────────────────────────────────────────────────────────────────
# CONTROL DE MÁXIMO 3 OPERACIONES POR NIVEL DE PRECIO
# ─────────────────────────────────────────────────────────────────────────────

def count_orders_near_entry(entry_price, tolerance_pct=0.001):
    """
    Cuenta cuántas órdenes (abiertas + pendientes) del bot están cerca del
    nivel de precio 'entry_price' (dentro de tolerance_pct %).
    Esto evita acumular más de MAX_PENDING_ORDERS operaciones en el mismo punto.
    """
    positions = mt5_client.get_open_positions()
    pending   = mt5_client.get_pending_orders()

    count = 0
    tol   = entry_price * tolerance_pct

    for p in positions:
        if abs(p.price_open - entry_price) <= tol:
            count += 1

    for o in pending:
        if abs(o.price_open - entry_price) <= tol:
            count += 1

    return count


# ─────────────────────────────────────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if not mt5_client.initialize():
        return

    print("Iniciando Bot CRT/SMC (FVG + IFVG) — Nasdaq v2.0")
    print(f"Símbolo : {config.SYMBOL}")
    print(f"Lote    : {config.LOT_SIZE}  |  TP fijo: {config.MIN_TP_USD} USD  |  BE: +{config.BREAKEVEN_PLUS_USD} USD")
    print(f"TFs     : {[TF_MAPPING.get(t, str(t)) for t in config.TIMEFRAMES]}")
    print(f"Máx operaciones por nivel: {config.MAX_PENDING_ORDERS}")
    print("─" * 60)

    try:
        while True:
            # 1. Gestionar posiciones abiertas (BreakEven)
            manage_open_positions()
            
            # Limpiar órdenes caducadas
            clean_expired_pending_orders()

            # 2. Obtener datos HTF para el sesgo CRT (siempre H4 > H2 > H1)
            df_h4 = mt5_client.get_data(config.SYMBOL, mt5.TIMEFRAME_H4, n_candles=50)
            df_h2 = mt5_client.get_data(config.SYMBOL, mt5.TIMEFRAME_H2, n_candles=50)
            df_h1 = mt5_client.get_data(config.SYMBOL, mt5.TIMEFRAME_H1, n_candles=50)

            # 3. Analizar cada temporalidad de entrada
            for timeframe in config.TIMEFRAMES:
                tf_name = TF_MAPPING.get(timeframe, str(timeframe))

                df_entry = mt5_client.get_data(config.SYMBOL, timeframe, n_candles=150)
                if df_entry is None or df_entry.empty:
                    continue

                result = strategy.analyze_smc(df_entry, df_h4=df_h4, df_h2=df_h2, df_h1=df_h1)

                if not result['signal']:
                    continue

                entry_price = result['entry']
                signal      = result['signal']
                sl          = result['sl']
                tp          = result['tp']

                # ── Verificar límite de 3 operaciones por nivel de precio ──
                orders_at_level = count_orders_near_entry(entry_price)
                if orders_at_level >= config.MAX_PENDING_ORDERS:
                    print(f"[{tf_name}] Nivel {entry_price:.3f} ya tiene {orders_at_level} órdenes → omitiendo.")
                    continue

                # ── Verificar cooldown de orden reciente ──
                pending_all  = mt5_client.get_pending_orders()
                current_time = time.time()
                timeout_secs = getattr(config, 'PENDING_ORDER_TIMEOUT_MINUTES', 30) * 60
                recent = any(
                    (current_time - o.time_setup) < timeout_secs
                    for o in pending_all
                    if o.symbol == config.SYMBOL
                )
                if recent and orders_at_level > 0:
                    continue

                print(f"\n[!] SEÑAL {signal} en {config.SYMBOL} ({tf_name})")
                print(f"    Entry : {entry_price:.3f}")
                print(f"    SL    : {sl:.3f}")
                print(f"    TP    : {tp:.3f}  (+{config.MIN_TP_USD} USD)")

                safe_sym = config.SYMBOL.replace('_', '\\_')
                msg = (
                    f"🚀 *NUEVA ORDEN {signal}*\n"
                    f"Símbolo: {safe_sym} ({tf_name})\n"
                    f"Entrada Limit: `{entry_price:.3f}`\n"
                    f"SL: `{sl:.3f}`\n"
                    f"TP CRT: `{tp:.3f}` (+{config.MIN_TP_USD} USD)\n"
                    f"BreakEven: +{config.BREAKEVEN_PLUS_USD} USD\n"
                    f"Lote: {config.LOT_SIZE}"
                )
                telegram_utils.enviar_telegram(msg)

                order_res = mt5_client.send_market_order(
                    config.SYMBOL, signal, config.LOT_SIZE, entry_price, sl, tp
                )
                if order_res and order_res.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f">> Orden ejecutada. Ticket: {order_res.order}")
                else:
                    print(f">> Error al ejecutar orden: {order_res}")

                time.sleep(10)

            # Pausa de ciclo
            time.sleep(15)

    except KeyboardInterrupt:
        print("\nBot detenido manualmente.")
    finally:
        mt5_client.shutdown()


if __name__ == "__main__":
    main()
