FROM python:3.10

RUN mkdir /crm

WORKDIR /crm

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

WORKDIR src

CMD gunicorn main:app --workers 5 --worker-class uvicorn.workers.UvicornWorker --bind=0.0.0.0:8000 --timeout 300