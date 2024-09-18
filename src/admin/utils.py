import datetime
from io import BytesIO

import pandas as pd

from database import Repository
from payments.models import BalanceHistoryModel
from payments.router import current_prices
from picker.utils import parse_excel_lines
from products.models import ReviewModel,  ProductModel


def set_type(value, field_type):
    if field_type == 'INTEGER':
        if value == 0:
            return value

        return int(value) if value else None

    elif field_type == 'VARCHAR':
        return str(value) if value else None

    elif field_type == 'BOOLEAN':
        return bool(value)

    elif field_type == 'DATETIME':
        return datetime.datetime.fromisoformat(value) if value else None

    elif field_type == 'DATE':
        return datetime.date.fromisoformat(value) if value else None

    elif field_type == 'TIME':
        return datetime.datetime.strptime(value, '%H:%M:%S').time() if value else None

    elif field_type == 'FLOAT':
        return float(value) if value else None

    return value


async def process_reviews_tasks_xlsx(file):
    excel_columns = {
        'status': 11,
        'review_id': 13,
    }

    xlsx_reviews_content = await file.read()
    xlsx_reviews = await parse_excel_lines(pd.read_excel(BytesIO(xlsx_reviews_content), dtype=str).values.tolist(),
                                           excel_columns)

    # xlsx check
    for line in xlsx_reviews:
        if line['status'] is None:
            raise Exception(f"Строка {line['line_number']}: статус не указан")

        if line['review_id'] is None:
            raise Exception(f"Строка {line['line_number']}: системный id не указан")

        try:
            int(str(line['review_id']).replace(' ', ''))
        except:
            raise Exception(f"Строка {line['line_number']}: системный id должен быть целым числом")

    # reviews check
    reviews = await Repository.get_records(
        ReviewModel,
        filters=[ReviewModel.id.in_([int(str(l['review_id']).replace(' ', '')) for l in xlsx_reviews])],
        select_related=[ReviewModel.product],
        deep_related=[
            [ReviewModel.product, ProductModel.organization]
        ]
    )

    reviews_to_process = []
    for line in xlsx_reviews:

        selected_review = None

        for review in reviews:
            if review.id == int(str(line['review_id']).replace(' ', '')):
                selected_review = review
                if review.status != 2:
                    raise Exception(f"Строка {line['line_number']}: отзыв с указанным id не со статусом 'В работе'")
                break

        if selected_review is None:
            raise Exception(f"Строка {line['line_number']}: отзыв с указанным id не найден в базе данных")

        reviews_to_process.append([selected_review, line['status']])

    # process reviews
    organizations_prices = {}
    for review in reviews_to_process:
        if not organizations_prices.get(review[0].product.organization.id):
            level, purchases = await current_prices(review[0].product.organization)
            organizations_prices[review[0].product.organization.id] = level

    review_records = []
    balance_records = []

    for review in reviews_to_process:

        if 'Оставлен' in review[1]:
            review_records.append(
                {
                    'id': review[0].id,
                    'status': 3,
                    'description': review[1],
                }
            )

            balance_records.append({
                'amount': organizations_prices[review[0].product.organization.id].price_review,
                'org_id': review[0].product.organization.id,
                'target_id': 7,
                'record_id': review[0].id,
                'action_id': 3
            })

    await Repository.save_records(
        [
            {'model': ReviewModel, 'records': review_records},
            {'model': BalanceHistoryModel, 'records': balance_records}
        ]
    )
