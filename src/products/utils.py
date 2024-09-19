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
        'advs': 1,
        'disadvs': 2,
        'text': 3,
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

        records_to_insert.append(
            {
                'product_id': selected_product.id,
                'status': 1,
                'text': line['text'],
                'advs': line['advs'],
                'disadvs': line['disadvs'],
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
