import json
from datetime import datetime, timedelta
from typing import Any, Dict
import pandas as pd

from services import fetch_currency_rates, fetch_stock_prices, load_user_settings


def process_financial_data(
    df: pd.DataFrame, start_date: datetime, end_date: datetime
) -> Dict[str, Any]:
    """Выполняет фильтрацию транзакций по дате, их группировку по категориям

    и округление до целых чисел.
    """
    if df.empty:
        return {
            "expenses": {"total_amount": 0, "main": [], "transfers_and_cash": []},
            "income": {"total_amount": 0, "main": []},
        }

    working_df = df.copy()
    if working_df["Сумма операции"].dtype == object:
        working_df["Сумма операции"] = (
            working_df["Сумма операции"]
            .astype(str)
            .str.replace(",", ".")
            .str.replace(" ", "")
        )
    working_df["Сумма операции"] = (
        pd.to_numeric(working_df["Сумма операции"], errors="coerce")
        .fillna(0)
    )
    working_df["Дата операции"] = pd.to_datetime(
        working_df["Дата операции"], dayfirst=True
    )

    mask = (working_df["Дата операции"] >= start_date) & (
        working_df["Дата операции"] <= end_date
    )
    filtered_df = working_df[mask].copy()

    expenses_df = filtered_df[filtered_df["Сумма операции"] < 0].copy()
    expenses_df["Сумма операции"] = expenses_df["Сумма операции"].abs()
    income_df = filtered_df[filtered_df["Сумма операции"] > 0]

    total_expenses = int(round(expenses_df["Сумма операции"].sum()))
    cash_transfer_cats = ["Наличные", "Переводы"]

    cash_df = expenses_df[expenses_df["Категория"].isin(cash_transfer_cats)]
    cash_grouped = (
        cash_df.groupby("Категория")["Сумма операции"].sum().reset_index()
    )
    cash_grouped = cash_grouped.sort_values(by="Сумма операции", ascending=False)
    cash_grouped["amount"] = cash_grouped["Сумма операции"].round().astype(int)
    cash_grouped = cash_grouped.rename(columns={"Категория": "category"})
    cash_summary = cash_grouped[["category", "amount"]].to_dict(orient="records")

    main_exp_df = expenses_df[~expenses_df["Категория"].isin(cash_transfer_cats)]
    main_grouped = (
        main_exp_df.groupby("Категория")["Сумма операции"]
        .sum()
        .sort_values(ascending=False)
    )

    main_summary = []
    if not main_grouped.empty:
        if len(main_grouped) > 7:
            top_7 = main_grouped.iloc[:7].reset_index()
            others_sum = main_grouped.iloc[7:].sum()
            for _, row in top_7.iterrows():
                main_summary.append(
                    {
                        "category": str(row["Категория"]),
                        "amount": int(round(row["Сумма операции"])),
                    }
                )
            main_summary.append({"category": "Остальное", "amount": int(round(others_sum))})
        else:
            for cat, val in main_grouped.items():
                main_summary.append({"category": str(cat), "amount": int(round(val))})

    total_income = int(round(income_df["Сумма операции"].sum()))
    income_grouped = (
        income_df.groupby("Категория")["Сумма операции"].sum().reset_index()
    )
    income_grouped = income_grouped.sort_values(
        by="Сумма операции", ascending=False
    )
    income_grouped["amount"] = income_grouped["Сумма операции"].round().astype(int)
    income_grouped = income_grouped.rename(columns={"Категория": "category"})
    income_summary = income_grouped[["category", "amount"]].to_dict(
        orient="records"
    )

    return {
        "expenses": {
            "total_amount": total_expenses,
            "main": main_summary,
            "transfers_and_cash": cash_summary,
        },
        "income": {"total_amount": total_income, "main": income_summary},
    }


def get_events_page_data(
    df: pd.DataFrame, date_str: str, range_type: str = "M"
) -> str:
    """Главная функция страницы 'События'.

    Расчитывает временные диапазоны и формирует итоговый JSON-ответ.
    """
    formats = ["%d.%m.%Y", "%Y-%m-%d"]
    target_date = None
    for fmt in formats:
        try:
            target_date = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue

    if not target_date:
        raise ValueError(f"Неподдерживаемый формат даты: {date_str}")

    end_date = target_date.replace(hour=23, minute=59, second=59)

    if range_type == "W":
        start_date = target_date - timedelta(days=target_date.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0)
    elif range_type == "M":
        start_date = target_date.replace(day=1, hour=0, minute=0, second=0)
    elif range_type == "Y":
        start_date = target_date.replace(
            month=1, day=1, hour=0, minute=0, second=0
        )
    elif range_type == "ALL":
        start_date = datetime.min
    else:
        start_date = target_date.replace(day=1, hour=0, minute=0, second=0)

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
