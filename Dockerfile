FROM python:3.10

RUN apt-get update && \
    apt-get install -y tzdata && \
    ln -fs /usr/share/zoneinfo/Europe/Moscow /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

RUN mkdir /crm

WORKDIR /crm

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

WORKDIR src

CMD gunicorn main:app --workers 3 --worker-class uvicorn.workers.UvicornWorker --bind=0.0.0.0:8000 --timeout 300