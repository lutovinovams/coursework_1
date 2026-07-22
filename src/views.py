import os
import json
import logging
from datetime import datetime
import pandas as pd
import requests

is_debug = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
log_level = logging.DEBUG if is_debug else logging.INFO

logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SETTINGS_FILE = "user_settings.json"


def load_user_settings() -> tuple[list, list]:
    """Загружает список отслеживаемых валют и акций из конфигурационного файла."""
    if not os.path.exists(SETTINGS_FILE):
        logger.warning(f"Файл настроек {SETTINGS_FILE} не найден. Используются значения по умолчанию.")
        return ["USD", "EUR"], ["AAPL", "AMZN", "GOOGL", "MSFT", "TSLA"]

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
            return settings.get("user_currencies", []), settings.get("user_stocks", [])
    except Exception as e:
        logger.error(f"Ошибка при чтении {SETTINGS_FILE}: {e}")
        return [], []


def fetch_currency_rates(currencies: list) -> list[dict]:
    """Получает курс валют по отношению к рублю через API cbr-xml-daily."""
    if not currencies:
        return []

    url = "https://www.cbr-xml-daily.ru/daily_json.js"
    logger.info(f"Запрос курсов валют ЦБ РФ по URL: {url}")
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
                    result.append({"currency": currency, "rate": round(value / nominal, 2)})
                else:
                    result.append({"currency": currency, "rate": None})
            else:
                result.append({"currency": currency, "rate": None})
        return result
    except Exception as e:
        logger.error(f"Ошибка при получении курсов валют через ЦБ РФ API: {e}")
        return [{"currency": c, "rate": None} for c in currencies]


def fetch_stock_prices(stocks: list) -> list[dict]:
    """Получает текущую стоимость закрытия акций через MOEX ISS API."""
    if not stocks:
        return []

    result = []
    for stock in stocks:
        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{stock}.json"
        logger.info(f"Запрос цены акции {stock} на бирже MOEX по URL: {url}")

        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()

            securities = data.get("securities", {})
            sec_columns = securities.get("columns", [])
            sec_data = securities.get("data", [])

            price = None
            if sec_data and "PREVPRICE" in sec_columns:
                idx = sec_columns.index("PREVPRICE")
                # Извлекаем цену последней доступной сделки из первой строки ответа
                if len(sec_data) > 0 and len(sec_data[0]) > idx:
                    price = sec_data[0][idx]

            if price is not None:
                result.append({"stock": stock, "price": float(price)})
            else:
                result.append({"stock": stock, "price": None})

        except Exception as e:
            logger.error(f"Ошибка при получении цены акции {stock} через MOEX API: {e}")
            result.append({"stock": stock, "price": None})

    return result


def process_financial_data(df: pd.DataFrame, start_date: datetime, end_date: datetime) -> dict:
    """Фильтрует транзакции в заданном диапазоне дат и формирует финансовую агрегацию."""
    if df.empty:
        return {
            "expenses": {"total_amount": 0, "main": [], "transfers_and_cash": []},
            "income": {"total_amount": 0, "main": []}
        }

    working_df = df.copy()
    if working_df["Сумма операции"].dtype == object:
        working_df["Сумма операции"] = (
            working_df["Сумма операции"].astype(str).str.replace(",", ".").str.replace(" ", "")
        )
    working_df["Сумма операции"] = pd.to_numeric(working_df["Сумма операции"], errors="coerce").fillna(0)
    working_df["Дата операции"] = pd.to_datetime(working_df["Дата операции"], dayfirst=True)

    mask = (working_df["Дата операции"] >= start_date) & (
            working_df["Дата операции"] <= end_date.replace(hour=23, minute=59, second=59)
    )
    filtered_df = working_df[mask].copy()

    expenses_df = filtered_df[filtered_df["Сумма операции"] < 0].copy()
    expenses_df["Сумма операции"] = expenses_df["Сумма операции"].abs()
    income_df = filtered_df[filtered_df["Сумма операции"] > 0]

    total_expenses = int(round(expenses_df["Сумма операции"].sum()))
    cash_transfer_cats = ["Наличные", "Переводы"]

    cash_df = expenses_df[expenses_df["Категория"].isin(cash_transfer_cats)]
    cash_grouped = cash_df.groupby("Категория")["Сумма операции"].sum().reset_index()
    cash_grouped = cash_grouped.sort_values(by="Сумма операции", ascending=False)
    cash_grouped["amount"] = cash_grouped["Сумма операции"].round().astype(int)
    cash_grouped = cash_grouped.rename(columns={"Категория": "category"})
    cash_summary = cash_grouped[["category", "amount"]].to_dict(orient="records")

    main_exp_df = expenses_df[~expenses_df["Категория"].isin(cash_transfer_cats)]
    main_grouped = main_exp_df.groupby("Категория")["Сумма операции"].sum().sort_values(ascending=False)

    main_summary = []
    if not main_grouped.empty:
        if len(main_grouped) > 7:
            top_7 = main_grouped.iloc[:7].reset_index()
            others_sum = main_grouped.iloc[7:].sum()

            for _, row in top_7.iterrows():
                main_summary.append({"category": row["Категория"], "amount": int(round(row["Сумма операции"]))})
            main_summary.append({"category": "Остальное", "amount": int(round(others_sum))})
        else:
            for cat, val in main_grouped.items():
                main_summary.append({"category": cat, "amount": int(round(val))})

    total_income = int(round(income_df["Сумма операции"].sum()))
    income_grouped = income_df.groupby("Категория")["Сумма операции"].sum().reset_index()
    income_grouped = income_grouped.sort_values(by="Сумма операции", ascending=False)
    income_grouped["amount"] = income_grouped["Сумма операции"].round().astype(int)
    income_grouped = income_grouped.rename(columns={"Категория": "category"})
    income_summary = income_grouped[["category", "amount"]].to_dict(orient="records")

    return {
        "expenses": {
            "total_amount": total_expenses,
            "main": main_summary,
            "transfers_and_cash": cash_summary
        },
        "income": {
            "total_amount": total_income,
            "main": income_summary
        }
    }


def get_events_page_data(df: pd.DataFrame, date_str: str) -> str:
    """Главная функция страницы 'События'. Формирует итоговый JSON-ответ."""
    logger.info(f"Запрос страницы 'События' для даты: {date_str}")
    formats = ["%d.%m.%Y", "%Y-%m-%d"]
    target_date = None

    for fmt in formats:
        try:
            target_date = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue

    if not target_date:
        raise ValueError(f"Неподдерживаемый формат даты: {date_str}. Используйте ДД.ММ.ГГГГ")

    start_date = target_date.replace(day=1, hour=0, minute=0, second=0)
    end_date = target_date

    user_currencies, user_stocks = load_user_settings()
    financial_data = process_financial_data(df, start_date, end_date)

    currency_rates = fetch_currency_rates(user_currencies)
    stock_prices = fetch_stock_prices(user_stocks)

    result = {
        "expenses": financial_data["expenses"],
        "income": financial_data["income"],
        "currency_rates": currency_rates,
        "stock_prices": stock_prices,
    }
    return json.dumps(result, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    raw_bank_data = [
        {"Дата операции": "31.12.2021 16:44:00", "Сумма операции": "-160.89", "Категория": "Супермаркеты"},
        {"Дата операции": "31.12.2021 16:42:04", "Сумма операции": "-64.00", "Категория": "Супермаркеты"},
        {"Дата операции": "31.12.2021 00:12:53", "Сумма операции": "-800.00", "Категория": "Переводы"},
        {"Дата операции": "30.12.2021 22:22:03", "Сумма операции": "-20000.00", "Категория": "Переводы"},
        {"Дата операции": "30.12.2021 17:50:17", "Сумма операции": "174000.00", "Категория": "Пополнения"},
        {"Дата операции": "29.12.2021 22:32:24", "Сумма операции": "-1411.40", "Категория": "Ж/д билеты"},
        {"Дата операции": "28.12.2021 18:42:21", "Сумма операции": "-257.89", "Категория": "Каршеринг"},
        {"Дата операции": "16.12.2021 16:40:47", "Сумма операции": "-14216.42", "Категория": "ЖКХ"},
    ]
    df_test = pd.DataFrame(raw_bank_data)
    print("--- Результирующий JSON-ответ для страницы 'События' ---")
    try:
        json_result = get_events_page_data(df_test, "30.12.2021")
        print(json_result)
    except Exception as error:
        print(f"Критическая ошибка при выполнении скрипта: {error}")
