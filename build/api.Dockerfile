FROM python:3.10.2

WORKDIR /api

COPY build/requirements.txt .
COPY proxy/db.py .

RUN pip install -r requirements.txt

COPY /api/ .

EXPOSE 8000

CMD ["python", "-u", "api.py"]