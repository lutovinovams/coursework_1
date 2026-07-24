import json
import logging
import os
from math import ceil
import requests

logger = logging.getLogger(__name__)
SETTINGS_FILE = "user_settings.json"


def load_user_settings() -> tuple[list[str], list[str]]:
    """Загружает списки отслеживаемых валют и акций из конфигурационного файла."""
    if not os.path.exists(SETTINGS_FILE):
        return ["USD", "EUR"], ["SBER", "GAZP", "LKOH", "YNDX", "ROSN"]
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
            return (
                settings.get("user_currencies", ["USD", "EUR"]),
                settings.get("user_stocks", ["SBER", "GAZP", "LKOH", "YNDX", "ROSN"]),
            )
    except Exception as e:
        logger.error(f"Ошибка при чтении {SETTINGS_FILE}: {e}")
        return ["USD", "EUR"], ["SBER", "GAZP", "LKOH", "YNDX", "ROSN"]


def fetch_currency_rates(currencies: list[str]) -> list[dict]:
    """Получает актуальные курсы валют через официальную JSON-обертку ЦБ РФ."""
    if not currencies:
        return []
    url = "https://www.cbr-xml-daily.ru/daily_json.js"
    result = []
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        valute_data = data.get("Valute", {})
        for currency in currencies:
            info = valute_data.get(currency)
            if info:
                value = info.get("Value")
                nominal = info.get("Nominal", 1)
                if value and nominal:
                    result.append(
                        {"currency": currency, "rate": round(value / nominal, 2)}
                    )
                else:
                    result.append({"currency": currency, "rate": None})
            else:
                result.append({"currency": currency, "rate": None})
        return result
    except Exception as e:
        logger.error(f"Ошибка курсов валют через API ЦБ РФ: {e}")
        return [{"currency": c, "rate": None} for c in currencies]


def fetch_stock_prices(stocks: list[str]) -> list[dict]:
    """Получает текущие стоимости акций из официального API Московской биржи (MOEX ISS)."""
    if not stocks:
        return []
    result = []
    for stock in stocks:
        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{stock}.json"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()

            securities_data = data.get("securities", {})
            columns = securities_data.get("columns", [])
            data_rows = securities_data.get("data", [])

            price = None
            if "PREVPRICE" in columns and data_rows:
                idx = columns.index("PREVPRICE")
                if len(data_rows[0]) > idx:
                    price = data_rows[0][idx]

            if price is not None:
                result.append({"stock": stock, "price": float(price)})
            else:
                result.append({"stock": stock, "price": None})
        except Exception as e:
            logger.error(f"Ошибка цены акции {stock} через API MOEX: {e}")
            result.append({"stock": stock, "price": None})
    return result


def get_investment_rounded_amount(amount: float, limit: int) -> float:
    """Вычисляет сумму округления для одной транзакции на основе лимита."""
    if limit <= 0:
        return 0.0
    abs_amount = abs(amount)
    rounded_amount = ceil(abs_amount / limit) * limit
    return round(rounded_amount - abs_amount, 2)


def investment_bank(month: str, transactions: list[dict], limit: int) -> float:
    """Рассчитывает сумму округления трат за определенный месяц для инвесткопилки."""
    logger.info(
        f"Запуск расчета инвесткопилки за месяц {month} с шагом округления {limit}"
    )
    if not transactions or limit <= 0:
        return 0.0
    valid_transactions = filter(
        lambda t: (
                isinstance(t.get("Дата операции"), str)
                and t["Дата операции"].startswith(month)
                and isinstance(t.get("Сумма операции"), (int, float))
                and t["Сумма операции"] < 0
        ),
        transactions,
    )
    savings = map(
        lambda t: get_investment_rounded_amount(t["Сумма операции"], limit),
        valid_transactions,
    )
    total_savings = sum(savings)
    logger.info(f"Расчет завершен. В инвесткопилку отложено: {total_savings} руб.")
    return round(total_savings, 2)
