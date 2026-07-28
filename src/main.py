import os
import warnings
import pandas as pd

from src.reports import spending_by_category
from src.services import (
    fetch_currency_rates,
    fetch_stock_prices,
    investment_bank,
    load_user_settings,
)
from src.views import get_events_page_data

warnings.filterwarnings("ignore", category=UserWarning)

FILE_PATH = r"C:\Users\Admin\Desktop\project\coursework_1\data\operations.xlsx"


def main() -> None:
    """Единая точка входа для загрузки данных из XLSX файла

    и поочередного запуска всех функциональных модулей проекта.
    """
    if not os.path.exists(FILE_PATH):
        print(f"Ошибка: Файл транзакций не найден по пути {FILE_PATH}")
        return

    try:
        excel_file = pd.ExcelFile(FILE_PATH)
        sheet_names = excel_file.sheet_names

        df = None
        chosen_sheet = None

        for sheet in sheet_names:
            preview_df = pd.read_excel(FILE_PATH, sheet_name=sheet, nrows=2)
            preview_df.columns = preview_df.columns.astype(str).str.strip()

            if "Категория" in preview_df.columns:
                chosen_sheet = sheet
                df = pd.read_excel(FILE_PATH, sheet_name=sheet)
                break

        if df is None:
            chosen_sheet = sheet_names[0]
            df = pd.read_excel(FILE_PATH, sheet_name=chosen_sheet)

        df.columns = df.columns.astype(str).str.strip()

        if "Сумма платежа" in df.columns and "Сумма операции" not in df.columns:
            df = df.rename(columns={"Сумма платежа": "Сумма операции"})

        print(f"[+] Данные успешно загружены с листа Excel: '{chosen_sheet}'")
        print(f"[+] Всего транзакций на листе: {len(df)} шт.")

        required_columns = ["Дата операции", "Сумма операции", "Категория"]
        for col in required_columns:
            if col not in df.columns:
                print(f"[-] КРИТИЧЕСКАЯ ОШИБКА: Колонка '{col}' не найдена.")
                print(f"[!] Доступные колонки: {list(df.columns)}")
                return

    except Exception as e:
        print(f"Ошибка чтения файла: {e}")
        return

    test_date = "31.12.2021"
    target_month = "2021-12"

    # ИСПРАВЛЕНО: Сбор данных API и передача четырех аргументов в get_events_page_data
    try:
        user_currencies, user_stocks = load_user_settings()
        currency_rates = fetch_currency_rates(user_currencies)
        stock_prices = fetch_stock_prices(user_stocks)

        json_response = get_events_page_data(
            df,
            date_str=test_date,
            currency_rates=currency_rates,
            stock_prices=stock_prices,
            range_type="M",
        )
        print("\n--- Главная страница (События) ---")
        print(json_response[:1000] + "\n...")
    except Exception as e:
        print(f"\nОшибка главной страницы: {e}")

    try:
        dict_df = df.dropna(subset=["Дата операции"]).copy()
        dict_df["Дата операции"] = pd.to_datetime(
            dict_df["Дата операции"], dayfirst=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")

        transactions_list = dict_df.dropna(subset=["Дата операции"]).to_dict(
            orient="records"
        )

        savings = investment_bank(
            month=target_month, transactions=transactions_list, limit=50
        )
        print(f"\n--- Инвесткопилка за {target_month} ---\nНакоплено: {savings} руб.")
    except Exception as e:
        print(f"\nОшибка инвесткопилки: {e}")

    try:
        report_df = spending_by_category(df, category="Супермаркеты", date=test_date)
        print(f"\n--- Отчеты ---\nСформирован отчет. Записей: {len(report_df)}")
    except Exception as e:
        print(f"\nОшибка отчета: {e}")


if __name__ == "__main__":
    main()
