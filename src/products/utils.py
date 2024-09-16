import json
from io import BytesIO

import pandas as pd
import requests

from database import Repository
from picker.utils import parse_excel_lines
from products.models import ProductModel, ReviewModel
from products.schemas import ProductSizeCreateSchema
from strings import *


async def process_reviews_xlsx(file, org_id, stars):
    excel_columns = {
        'ozon_article': 0,
        'text': 1,
        'strict_match': 2,
        'match': 3
    }

    xlsx_reviews_content = await file.read()
    xlsx_reviews = await parse_excel_lines(pd.read_excel(BytesIO(xlsx_reviews_content), dtype=str).values.tolist(),
                                           excel_columns)

    if len(xlsx_reviews) <= 6:
        raise Exception('В файле нет отзывов')

    if len(xlsx_reviews[6:]) > 1000:
        raise Exception('Допустимо не более 1000 отзывов')

    products = await Repository.get_records(
        ProductModel,
        filters=[
            ProductModel.org_id == org_id,
            ProductModel.status != 3
        ],
    )

    product_articles = [p.ozon_article for p in products]
    records_to_insert = []

    for line in xlsx_reviews[6:]:

        # Article check
        if not line['ozon_article']:
            raise Exception(f"Строка {line['line_number']}: артикул не указан")

        if line['ozon_article'].replace(' ', '') not in product_articles:
            raise Exception(f"Строка {line['line_number']}: товар не найден")

        # Size check
        selected_product = None
        for product in products:
            if product.ozon_article == line['ozon_article']:

                if not product.barcode:
                    raise Exception(f"Строка {line['line_number']}: штрих-код товара не указан в разделе Товары")

                selected_product = product
                break

        if not selected_product:
            raise Exception(f"Строка {line['line_number']}: товар не найден в разделе Товары")

        # Strict match check
        if line['strict_match'] is None:
            raise Exception(f"Строка {line['line_number']}: не указана необходимость в выборе аккаунта")

        try:
            int(str(line['strict_match']).replace(' ', ''))
        except:
            raise Exception(f"Строка {line['line_number']}: необходимость в выборе аккаунта должна быть целым числом")

        strict_match = int(str(line['strict_match']).replace(' ', ''))
        if strict_match not in [0, 1]:
            raise Exception(f"Строка {line['line_number']}: необходимость в выборе аккаунта должна быть 0 или 1")

        # Match check
        if line['match'] is None:
            raise Exception(f"Строка {line['line_number']}: не указано соответствие размеру")

        try:
            int(str(line['match']).replace(' ', ''))
        except:
            raise Exception(f"Строка {line['line_number']}: соответствие размеру должно быть целым числом")

        match = int(str(line['match']).replace(' ', ''))
        if match not in [0, 1, 2, 3]:
            raise Exception(f"Строка {line['line_number']}: соответствие размеру должно быть 0, 1, 2 или 3")

        records_to_insert.append(
            {
                'product_id': selected_product.id,
                'status': 1,
                'text': line['text'],
                'strict_match': strict_match,
                'match': match,
                'stars': stars
            }
        )

    await Repository.save_records([{'model': ReviewModel, 'records': records_to_insert}])


def parse_ozon_card(url, cookies, useragent):

    r = requests.get(f'http://185.253.181.112:9500/parse/{url}')

    product_data = json.loads(r.text)
    image_data = requests.get(product_data['image']).content

    res = {
        'title': product_data['title'],
        'price': product_data['price'],
        'article': product_data['article'],
        'image': image_data,
        'size': product_data['size'],
    }

    return res
