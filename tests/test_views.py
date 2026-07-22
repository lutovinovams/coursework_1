import sys
import os
import json
from datetime import datetime
import pandas as pd
from unittest.mock import patch, mock_open

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src import views  # noqa: E402


def test_load_user_settings():
    """Проверяет корректность парсинга пользовательских настроек из JSON."""
    mock_data = json.dumps({
        "user_currencies": ["EUR"],
        "user_stocks": ["SBER"]
    })

    with patch("os.path.exists", return_value=True), \
            patch("builtins.open", mock_open(read_data=mock_data)):
        currencies, stocks = views.load_user_settings()

    assert currencies == ["EUR"]
    assert stocks == ["SBER"]


def test_process_financial_data_aggregation():
    """Проверяет фильтрацию, убывающую сортировку и ограничение Топ-7 с категорией 'Остальное'."""
    raw_data = [
        {"Дата операции": "15.12.2021 12:00:00", "Сумма операции": f"-{i * 100}", "Категория": f"Кат_{i}"}
        for i in range(1, 10)
    ]
    raw_data.extend([
        {"Дата операции": "20.12.2021 10:00:00", "Сумма операции": "-500", "Категория": "Наличные"},
        {"Дата операции": "21.12.2021 11:00:00", "Сумма операции": "-1500", "Категория": "Переводы"},
        {"Дата операции": "25.12.2021 09:00:00", "Сумма операции": "50000", "Категория": "Зарплата"},
        {"Дата операции": "01.11.2021 12:00:00", "Сумма операции": "-9999", "Категория": "Супермаркеты"}
    ])

    df = pd.DataFrame(raw_data)
    start_date = datetime(2021, 12, 1)
    end_date = datetime(2021, 12, 31)

    result = views.process_financial_data(df, start_date, end_date)

    assert result["expenses"]["total_amount"] == 6500
    assert result["income"]["total_amount"] == 50000

    main_cats = result["expenses"]["main"]
    assert len(main_cats) == 8
    assert main_cats[-1]["category"] == "Остальное"
    assert main_cats[-1]["amount"] == 300
    assert main_cats[0]["category"] == "Кат_9"
    assert main_cats[0]["amount"] == 900

    transfers = result["expenses"]["transfers_and_cash"]
    assert transfers[0]["category"] == "Переводы"
    assert transfers[0]["amount"] == 1500


@patch("src.views.fetch_currency_rates")
@patch("src.views.fetch_stock_prices")
@patch("src.views.load_user_settings")
def test_get_events_page_data_output(mock_settings, mock_stocks, mock_rates):
    """Проверяет финальную структуру и ключи результирующего JSON-отчета."""
    mock_settings.return_value = (["USD"], ["SBER"])
    mock_rates.return_value = [{"currency": "USD", "rate": 73.21}]
    mock_stocks.return_value = [{"stock": "SBER", "price": 295.5}]

    raw_data = [
        {"Дата операции": "20.12.2021", "Сумма операции": "-1000", "Категория": "Супермаркеты"}
    ]
    df = pd.DataFrame(raw_data)

    json_str = views.get_events_page_data(df, "30.12.2021")
    data = json.loads(json_str)

    assert "expenses" in data
    assert "income" in data
    assert "currency_rates" in data
    assert "stock_prices" in data

    assert data["expenses"]["total_amount"] == 1000
    assert data["currency_rates"][0]["currency"] == "USD"
    assert data["stock_prices"][0]["stock"] == "SBER"
