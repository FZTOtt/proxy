FROM python:3.10.2

WORKDIR /api

COPY /build/requirements.txt .

RUN pip install requirements.txt

COPY /api/ .

EXPOSE 8000

CMD [ "python", "api.py" ]