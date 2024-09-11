import json
from io import BytesIO

import pandas as pd
import requests

from database import Repository
from picker.utils import parse_excel_lines
from products.models import ProductModel, ReviewModel
from products.schemas import ProductSizeCreateSchema
from strings import *


async def process_reviews_xlsx(file, org_id):
    excel_columns = {
        'wb_article': 0,
        'wb_size_origName': 1,
        'text': 2,
        'strict_match': 3,
        'match': 4
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
        filters=[ProductModel.org_id == org_id],
        select_related=[ProductModel.sizes]
    )

    product_articles = [p.wb_article for p in products]
    records_to_insert = []

    for line in xlsx_reviews[6:]:
        print(line)
        # Article check
        if not line['wb_article']:
            raise Exception(f"Строка {line['line_number']}: артикул не указан")

        if line['wb_article'].replace(' ', '') not in product_articles:
            raise Exception(f"Строка {line['line_number']}: товар не найден")

        # Size check
        selected_size = None
        for product in products:
            if product.wb_article == line['wb_article']:

                # Search size
                for size in product.sizes:
                    if size.wb_size_origName == line['wb_size_origName']:
                        selected_size = size
                        break

                if line['wb_size_origName'] and not selected_size:
                    raise Exception(f"Строка {line['line_number']}: размер не найден")

                # Size not found
                if not selected_size:
                    if len(product.sizes) == 1 and product.sizes[0].wb_size_origName is None:
                        selected_size = product.sizes[0]
                    else:
                        for size in product.sizes:
                            if size.wb_in_stock and size.barcode:
                                selected_size = size
                                break

                if not selected_size:
                    raise Exception(
                        f"Строка {line['line_number']}: не удалось выбрать размер автоматически. Пожалуйста, укажите любой размер товара вручную")

                if not selected_size.wb_in_stock:
                    raise Exception(f"Строка {line['line_number']}: размер не в наличии")

                if not selected_size.barcode:
                    raise Exception(f"Строка {line['line_number']}: штрих-код размера не указан")

                break

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
                'size_id': selected_size.id,
                'status': 1,
                'text': line['text'],
                'strict_match': strict_match,
                'match': match,
            }
        )

    await Repository.save_records([{'model': ReviewModel, 'records': records_to_insert}])


def parse_ozon_card(url, cookies, useragent):
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': useragent,
        'Cookie': cookies
    }

    # Get size
    url_params = url.split('ozon.ru')[1]
    if '/?' in url_params:
        url_params = url_params.split('/?')[0]

    characteristics_request = requests.get(
        f'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url={url_params}%2F%3Fadvert%3DBeLssKwguc0z9gMzNLpKXOVaASysBPXyx5mScGciakLQsmUl3BLxdG_e8afbtCdn91kV4vwQzcPbrEdRlYQfPncU_2jXqkOBgyxybLZcyk2myqNBqyu7HRvjNN-2ieK8o4YgFXY167V2z4ow2NQkShC9JXG-4j34x-mApjm1AR1Vi75d5tKH3B0wJxj57b6PcKMZBnLUzQ_PavXS4LfzZTpMH6_eYPTYPvEp_AZv40nwosOHGnhjJ8H_9GR7s_6W%26avtc%3D1%26avte%3D2%26avts%3D1725617827%26layout_container%3DpdpPage2column%26layout_page_index%3D2%26sh%3Dcq6QBHW3jw%26start_page_id%3Dd5b8274c41ae42665e2d292d5ea82787',
        headers=headers
    )

    characteristics = json.loads(
        json.loads(characteristics_request.text)['widgetStates']['webCharacteristics-3282540-pdpPage2column-2'])
    size = None

    if characteristics['characteristics'][0].get('short'):
        for i in characteristics['characteristics'][0]['short']:
            if i['name'] == 'Российский размер':
                size = i['values'][0]['text']
    elif characteristics['characteristics'][0].get('long'):
        for i in characteristics['characteristics'][0]['long']:
            if i['name'] == 'Российский размер':
                size = i['values'][0]['text']
    else:
        raise Exception('Ошибка чтения характеристик товара')

    # Get title, price, article, image
    product_request_url = f'{url}/?avtc=1&avte=2&avts=1725617827'

    product_request = requests.get(
        product_request_url,
        headers=headers
    )
    data = json.loads(product_request.text.split('<script type="application/ld+json">')[1].split('</script>')[0])
    image_data = requests.get(data['image']).content

    res = {
        'title': data['name'],
        'price': int(data['offers']['price']),
        'article': data['sku'],
        'image': image_data,
        'size': size,
    }

    return res
