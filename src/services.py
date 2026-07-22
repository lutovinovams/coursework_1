import logging
from math import ceil
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_investment_rounded_amount(amount: float, limit: int) -> float:
    """Вычисляет сумму округления для одной транзакции на основе заданного лимита."""
    if limit <= 0:
        return 0.0
    abs_amount = abs(amount)
    rounded_amount = ceil(abs_amount / limit) * limit
    return round(rounded_amount - abs_amount, 2)


def investment_bank(month: str, transactions: List[Dict[str, Any]], limit: int) -> float:
    """Рассчитывает сумму округления трат за определенный месяц для инвесткопилки."""
    logger.info(f"Запуск расчета инвесткопилки за месяц {month} с шагом округления {limit}")

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

    savings = map(lambda t: get_investment_rounded_amount(t["Сумма операции"], limit), valid_transactions)

    total_savings = sum(savings)
    logger.info(f"Расчет завершен. В инвесткопилку отложено: {total_savings} руб.")
    return round(total_savings, 2)


if __name__ == "__main__":
    sample_transactions = [
        {"Дата операции": "2021-12-01", "Сумма операции": -1712.0, "Категория": "Супермаркеты"},
        {"Дата операции": "2021-12-05", "Сумма операции": -230.50, "Категория": "Кафе"},
        {"Дата операции": "2021-12-15", "Сумма операции": 5000.0, "Категория": "Пополнения"},
        {"Дата операции": "2021-11-28", "Сумма операции": -150.0, "Категория": "Транспорт"},
    ]

    print("--- Тестовый расчет инвесткопилки ---")
    result = investment_bank("2021-12", sample_transactions, 50)
    print(f"Итого сохранено: {result} руб.")