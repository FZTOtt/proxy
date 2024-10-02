FROM python:3.10.2

WORKDIR /proxy

COPY build/requirements.txt .

RUN pip install -r requirements.txt

COPY /proxy/ .

EXPOSE 8080

CMD ["python", "-u", "only_proxy.py"]