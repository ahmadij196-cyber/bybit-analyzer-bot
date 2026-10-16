import os
import time
import requests

BYBIT_URL = "https://api.bybit.com"
TELEGRAM_URL = "https://api.telegram.org/bot"

TIMEFRAMES = {
    "15 دقیقه": "15",
    "30 دقیقه": "30",
    "1 ساعت": "60",
    "4 ساعت": "240"
}

session = requests.Session()


def get_candles(symbol, interval):
    response = session.get(
        f"{BYBIT_URL}/v5/market/kline",
        params={
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": 150
        },
        timeout=20
    )
    response.raise_for_status()
    data = response.json()

    if data["retCode"] != 0:
        raise ValueError(data["retMsg"])

    now = int(time.time() * 1000)
    duration = int(interval) * 60 * 1000

    candles = data["result"]["list"][::-1]
    result = []

    for c in candles:
        # فقط کندل‌های بسته‌شده
        if int(c[0]) + duration <= now:
            result.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4])
            })

    return result


def ema(values, period):
    if len(values) < period:
        return None

    value = sum(values[:period]) / period
    multiplier = 2 / (period + 1)

    for price in values[period:]:
        value = price * multiplier + value * (1 - multiplier)

    return value


def rsi(values, period=14):
    if len(values) <= period:
        return None

    changes = [
        values[i] - values[i - 1]
        for i in range(1, len(values))
    ]

    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = (
            avg_gain * (period - 1) + gains[i]
        ) / period

        avg_loss = (
            avg_loss * (period - 1) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd(values):
    if len(values) < 35:
        return None, None

    line = []

    for i in range(25, len(values)):
        fast = ema(values[:i + 1], 12)
        slow = ema(values[:i + 1], 26)
        line.append(fast - slow)

    return line[-1], ema(line, 9)


def analyze(symbol, name, interval):
    candles = get_candles(symbol, interval)

    if len(candles) < 50:
        return f"{name}: اطلاعات کافی دریافت نشد."

    closes = [c["close"] for c in candles]
    recent = candles[-30:]

    price = closes[-1]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    r = rsi(closes)
    m, sig = macd(closes)

    score = 0
    reasons = []

    if e20 > e50:
        score += 1
        reasons.append("EMA صعودی")
    else:
        score -= 1
        reasons.append("EMA نزولی")

    if r > 50:
        score += 1
        reasons.append("RSI بالای 50")
    else:
        score -= 1
        reasons.append("RSI زیر 50")

    if m > sig:
        score += 1
        reasons.append("MACD صعودی")
    else:
        score -= 1
        reasons.append("MACD نزولی")

    if score >= 2:
        decision = "LONG — تمایل صعودی"
    elif score <= -2:
        decision = "SHORT — تمایل نزولی"
    else:
        decision = "WAIT — انتظار برای تأیید"

    support = min(c["low"] for c in recent)
    resistance = max(c["high"] for c in recent)

    return (
        f"📊 {symbol} | {name}\n"
        f"قیمت: {price}\n"
        f"EMA20: {e20:.6f}\n"
        f"EMA50: {e50:.6f}\n"
        f"RSI: {r:.2f}\n"
        f"MACD: {m:.6f}\n"
        f"سیگنال MACD: {sig:.6f}\n"
        f"حمایت تقریبی: {support}\n"
        f"مقاومت تقریبی: {resistance}\n"
        f"امتیاز: {score}/3\n"
        f"نتیجه: {decision}\n"
        f"دلایل: {'، '.join(reasons)}"
    )


def analyze_all(symbol):
    reports = []

    for name, interval in TIMEFRAMES.items():
        try:
            reports.append(analyze(symbol, name, interval))
        except Exception as error:
            reports.append(f"{name}: خطا در تحلیل: {error}")

    return "\n\n--------------------\n\n".join(reports)


def telegram_request(token, method, payload=None):
    response = session.post(
        f"{TELEGRAM_URL}{token}/{method}",
        json=payload or {},
        timeout=40
    )
    response.raise_for_status()
    return response.json()


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError("توکن تلگرام تنظیم نشده است.")

    offset = None
    print("ربات تحلیل‌گر شروع شد.")

    while True:
        try:
            data = telegram_request(
                token,
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": 25
                }
            )

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message", {})
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                command = message.get("text", "").strip()

                if not chat_id:
                    continue

                if command.startswith("/start"):
                    reply = (
                        "سلام! 🤖\n"
                        "ربات تحلیل‌گر Bybit آماده است.\n\n"
                        "/analyze — تحلیل BTCUSDT\n"
                        "/analyze ETHUSDT — تحلیل اتریوم\n"
                        "/help — راهنما\n\n"
                        "ربات فقط تحلیل می‌کند و معامله باز نمی‌کند."
                    )

                elif command.startswith("/help"):
                    reply = (
                        "برای تحلیل بنویس:\n"
                        "/analyze\n"
                        "یا:\n"
                        "/analyze ETHUSDT"
                    )

                elif command.startswith("/analyze"):
                    parts = command.split()
                    symbol = (
                        parts[1].upper()
                        if len(parts) > 1
                        else "BTCUSDT"
                    )

                    if not symbol.endswith("USDT"):
                        symbol += "USDT"

                    if not symbol.replace("USDT", "").isalnum():
                        reply = "نام ارز درست نیست."
                    else:
                        telegram_request(
                            token,
                            "sendMessage",
                            {
                                "chat_id": chat_id,
                                "text": (
                                    f"در حال تحلیل {symbol} "
                                    "در چهار تایم‌فریم..."
                                )
                            }
                        )
                        reply = analyze_all(symbol)

                else:
                    reply = "برای شروع /start یا برای تحلیل /analyze را بفرست."

                telegram_request(
                    token,
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": reply
                    }
                )

        except Exception as error:
            print("خطا:", error)
            time.sleep(5)


if __name__ == "__main__":
    main()
