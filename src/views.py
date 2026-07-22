import os
import json
import logging
from datetime import datetime
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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


def get_currency_rates(currencies: list, target_date: datetime) -> dict:
    """Получает курс валют по отношению к рублю (RUB) на выбранную дату через API ЦБ РФ (cbr-xml-daily)."""
    if not currencies:
        return {}

    now = datetime.now()
    if target_date.date() == now.date():
        url = "https://cbr-xml-daily.ru"
    else:
        date_path = target_date.strftime("%Y/%m/%d")
        url = "https://cbr-xml-daily.ru" + date_path + "/daily_json.js"

    try:
        logger.info(f"Запрос курсов валют ЦБ РФ по URL: {url}")
        response = requests.get(url, timeout=5)

        if response.status_code == 404:
            logger.warning(f"Архивный курс на дату {target_date.strftime('%d.%m.%Y')} не найден, берем текущий.")
            url = "https://cbr-xml-daily.ru"
            response = requests.get(url, timeout=5)

        response.raise_for_status()
        data = response.json()
        valute_data = data.get("Valute", {})

        result = {}
        for currency in currencies:
            info = valute_data.get(currency)
            if info:
                value = info.get("Value")
                nominal = info.get("Nominal", 1)
                if value and nominal:
                    result[currency] = round(value / nominal, 2)
                else:
                    result[currency] = None
            else:
                result[currency] = None
        return result
    except Exception as e:
        logger.error(f"Ошибка при получении курсов валют через ЦБ РФ API: {e}")
        return {currency: None for currency in currencies}


def get_stock_prices(stocks: list, target_date: datetime) -> dict:
    """Получает историческую стоимость закрытия акций на выбранную дату через MOEX ISS API."""
    if not stocks:
        return {}

    date_str = target_date.strftime("%Y-%m-%d")
    result = {}

    for stock in stocks:
        url = "https://moex.com" + stock + ".json"
        try:
            logger.info(f"Запрос цены акции {stock} на бирже MOEX за дату: {date_str}")
            response = requests.get(url, params={"date": date_str}, timeout=5)
            response.raise_for_status()
            data = response.json()

            history_data = data.get("history", {})
            columns = history_data.get("columns", [])
            rows = history_data.get("data", [])

            if not rows:
                fallback_url = (
                    "https://moex.com" + stock + ".json"
                )
                fallback_resp = requests.get(fallback_url, timeout=5)
                if fallback_resp.status_code == 200:
                    fb_data = fallback_resp.json()
                    securities = fb_data.get("securities", {})
                    sec_data = securities.get("data", [])
                    sec_columns = securities.get("columns", [])
                    if sec_data and "PREVPRICE" in sec_columns:
                        idx = sec_columns.index("PREVPRICE")
                        result[stock] = sec_data[idx]
                        continue
                result[stock] = None
                continue

            df_moex = pd.DataFrame(rows, columns=columns)

            if (
                "LEGALCLOSEPRICE" in df_moex.columns
                and not df_moex["LEGALCLOSEPRICE"].empty
                and pd.notna(df_moex["LEGALCLOSEPRICE"].iloc)
            ):
                price = df_moex["LEGALCLOSEPRICE"].iloc
            elif "CLOSE" in df_moex.columns and not df_moex["CLOSE"].empty and pd.notna(df_moex["CLOSE"].iloc):
                price = df_moex["CLOSE"].iloc
            else:
                price = None

            result[stock] = float(price) if price is not None else None

        except Exception as e:
            logger.error(f"Ошибка при получении цены акции {stock} через MOEX API: {e}")
            result[stock] = None

    return result


def process_financial_data(df: pd.DataFrame, start_date: datetime, end_date: datetime) -> dict:
    """Фильтрует транзакции в заданном диапазоне дат и формирует финансовую агрегацию."""
    if df.empty:
        return {
            "Расходы": {"Общая сумма": 0, "Основные": {}, "Переводы и наличные": {}},
            "Поступления": {"Общая сумма": 0, "Основные": {}},
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
    cash_summary = (
        cash_df.groupby("Категория")["Сумма операции"]
        .sum()
        .round()
        .astype(int)
        .sort_values(ascending=False)
        .to_dict()
    )

    main_exp_df = expenses_df[~expenses_df["Категория"].isin(cash_transfer_cats)]
    main_grouped = main_exp_df.groupby("Категория")["Сумма операции"].sum().sort_values(ascending=False)

    if len(main_grouped) > 7:
        top_7 = main_grouped.iloc[:7]
        others_sum = main_grouped.iloc[7:].sum()
        main_summary = top_7.round().astype(int).to_dict()
        main_summary["Остальное"] = int(round(others_sum))
    else:
        main_summary = main_grouped.round().astype(int).to_dict()

    total_income = int(round(income_df["Сумма операции"].sum()))
    income_summary = (
        income_df.groupby("Категория")["Сумма операции"]
        .sum()
        .round()
        .astype(int)
        .sort_values(ascending=False)
        .to_dict()
    )

    return {
        "Расходы": {
            "Общая сумма": total_expenses,
            "Основные": main_summary,
            "Переводы и наличные": cash_summary,
        },
        "Поступления": {"Общая сумма": total_income, "Основные": income_summary},
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

    currency_rates = get_currency_rates(user_currencies, target_date)
    stock_prices = get_stock_prices(user_stocks, target_date)

    result = {
        "Расходы": financial_data["Расходы"],
        "Поступления": financial_data["Поступления"],
        "Курс валют": currency_rates,
        "Стоимость акций": stock_prices,
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
    df = pd.DataFrame(raw_bank_data)

    print("--- Результирующий JSON-ответ для страницы 'События' ---")

    try:
        json_result = get_events_page_data(df, "30.12.2021")
        print(json_result)
    except Exception as error:
        print(f"Критическая ошибка при выполнении скрипта: {error}")
