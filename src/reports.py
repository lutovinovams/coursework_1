import os
import json
import logging
from functools import wraps
from datetime import datetime
from typing import Optional, Callable, Any
import pandas as pd

is_debug = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
log_level = logging.DEBUG if is_debug else logging.INFO

logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def report_to_file(filename_or_func: Optional[Any] = None) -> Callable:
    """Декоратор для сохранения результатов отчета в Excel или JSON файл.

    Может использоваться без параметров или принимать имя файла в качестве аргумента.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)

            if isinstance(filename_or_func, str):
                out_name = filename_or_func
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_name = f"report_{func.__name__}_{timestamp}.xlsx"

            os.makedirs("data", exist_ok=True)
            target_path = os.path.join("data", out_name)

            logger.info(f"Сохранение отчета '{func.__name__}' в файл: {target_path}")

            if isinstance(result, pd.DataFrame):
                if target_path.endswith(".csv"):
                    result.to_csv(target_path, index=False, encoding="utf-8")
                else:
                    if not target_path.endswith(".xlsx"):
                        target_path += ".xlsx"
                    result.to_excel(target_path, index=False)
            elif isinstance(result, (dict, list)):
                if not target_path.endswith(".json"):
                    target_path += ".json"
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=4)

            return result

        return wrapper

    if callable(filename_or_func):
        func_to_decorate = filename_or_func
        filename_or_func = None
        return decorator(func_to_decorate)

    return decorator


@report_to_file
def spending_by_category(
        transactions: pd.DataFrame,
        category: str,
        date: Optional[str] = None
) -> pd.DataFrame:
    """Возвращает траты по заданной категории за последние три месяца от переданной даты."""
    logger.info(f"Формирование отчета по категории '{category}', опорная дата: {date or 'текущая'}")

    if transactions.empty:
        return pd.DataFrame(columns=["Дата операции", "Сумма операции", "Категория"])

    working_df = transactions.copy()
    working_df["Дата операции"] = pd.to_datetime(working_df["Дата операции"], dayfirst=True)

    if working_df["Сумма операции"].dtype == object:
        working_df["Сумма операции"] = (
            working_df["Сумма операции"].astype(str).str.replace(",", ".").str.replace(" ", "")
        )
    working_df["Сумма операции"] = pd.to_numeric(working_df["Сумма операции"], errors="coerce").fillna(0)

    if date:
        formats = ["%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]
        end_date = None
        for fmt in formats:
            try:
                end_date = datetime.strptime(date, fmt)
                break
            except ValueError:
                continue
        if not end_date:
            raise ValueError(f"Неподдерживаемый формат даты: {date}")
    else:
        end_date = datetime.now()

    start_date = end_date - pd.DateOffset(months=3)

    cond_date_start = working_df["Дата операции"] >= start_date
    cond_date_end = working_df["Дата операции"] <= end_date
    cond_category = working_df["Категория"] == category
    cond_expense = working_df["Сумма операции"] < 0

    # Объединяем маски
    mask = cond_date_start & cond_date_end & cond_category & cond_expense

    filtered_df = working_df[mask].copy()
    filtered_df["Сумма операции"] = filtered_df["Сумма операции"].abs()

    return filtered_df.sort_values(by="Дата операции", ascending=False)
