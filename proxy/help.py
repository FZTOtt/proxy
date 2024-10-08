import gzip
from http.cookies import SimpleCookie
import io
import os
import subprocess
from urllib.parse import parse_qs, urlparse

from db import insert_request, insert_response

# Пути к корневому сертификату и ключу
CA_CERT = 'ca.crt'
CA_KEY = 'ca.key'
CERTS_DIR = './certs/'  # Директория для временных сертификатов
last_request_id = 0
def parse_body(client_socket, method, headers):

    body = None

    if method == "POST" and "Content-Length" in headers:
        content_length = int(headers["Content-Length"])
        body = client_socket.recv(content_length).decode('utf-8')

    if headers.get("Content-Encoding") == "gzip":
        body = decompress_gzip(body.encode('utf-8'))

    return body

def decompress_gzip(data):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
        return f.read()
    
def parse_http_request(request):
    lines = request.split("\n")
    method, full_path, version = lines[0].split()

    # Парсим путь и GET параметры
    parsed_url = urlparse(full_path)
    path = parsed_url.path
    get_params = parse_qs(parsed_url.query)

    # Парсим заголовки
    headers = {}
    cookies = {}
    for line in lines[1:]:
        if ": " in line:
            key, value = line.split(": ", 1)
            headers[key] = value.replace('\r', '')
            if key == "Cookie":
                cookie = SimpleCookie()
                cookie.load(value)
                cookies = {k: v.value for k, v in cookie.items()}

    return method, path, headers, cookies, get_params

def get_post_parameters(method, headers, client_socket):
    post_params = {}

    
    if method == "POST" and client_socket:
        
        if "Content-Length" in headers:
            content_length = int(headers["Content-Length"])
            body = client_socket.recv(content_length).decode('utf-8')

            if "Content-Type" in headers and headers["Content-Type"] == "application/x-www-form-urlencoded":
                post_params = parse_qs(body)
    
    return post_params

def parse_http_response(response_data):
    try:
        response_text = response_data.decode('utf-8', errors='ignore')
        headers, body = response_text.split("\r\n\r\n", 1)

        # Разбираем строку статуса
        status_line = headers.splitlines()[0]
        protocol, status_code, status_message = status_line.split(" ", 2)

        # Разбираем заголовки
        header_lines = headers.splitlines()[1:]
        response_headers = {}
        for header_line in header_lines:
            if ": " in header_line:
                key, value = header_line.split(": ", 1)
                response_headers[key] = value

        return int(status_code), status_message, response_headers, body
    except Exception as e:
        print(f"Error parsing HTTP response: {e}")
        return None, None, None, None
    
def forward(source, destination):
    data=b""
    headers_end = b"\r\n\r\n"
    try:
        # Сначала считываем заголовки ответа
        while headers_end not in data:
            chunk = source.recv(4096)
            if not chunk:
                break
            data += chunk
            # destination.sendall(chunk)
        print("end_headers")
        
        # Разделяем заголовки и тело
        header_data, body_data = data.split(headers_end, 1)

        # Отправляем заголовки клиенту
        destination.sendall(header_data + headers_end)

        # Отправляем тело, если оно есть
        destination.sendall(body_data)

        headers = header_data.decode('utf-8').split("\r\n")
        content_length = None
        transfer_encoding_chunked = False

        for header in headers:
            if header.startswith("Content-Length"):
                content_length = int(header.split(":")[1].strip())
            elif "Transfer-Encoding: chunked" in header:
                transfer_encoding_chunked = True

        # Если есть Content-Length, считываем точно указанное количество байтов
        if content_length is not None:
            remaining = content_length - len(body_data)
            while remaining > 0:
                chunk = source.recv(min(4096, remaining))
                if not chunk:
                    break
                destination.sendall(chunk)
                body_data += chunk
                remaining -= len(chunk)

        # Если передача идет chunked, обрабатываем каждый chunk
        elif transfer_encoding_chunked:
            while True:
                # Читаем размер следующего chunk
                chunk_size_line = b""
                while b"\r\n" not in chunk_size_line:
                    chunk_size_line += source.recv(1)

                chunk_size = int(chunk_size_line.strip(), 16)
                if chunk_size == 0:
                    break

                # Читаем сам chunk
                chunk = source.recv(chunk_size)
                destination.sendall(chunk)
                body_data += chunk

                # Читаем \r\n после chunk
                source.recv(2)
            source.recv(2)
        else:
            while True:
                chunk = source.recv(4096)
                if not chunk:
                    break
                destination.sendall(chunk)
                body_data += chunk

        print("end_body")

    except Exception as e:
        print(f"Error during forwarding: {e}")

    source.close()
    destination.close()
    print(header_data + headers_end + body_data)
    
    return parse_http_response(header_data + headers_end + body_data)

def forward_https(source, destination, client):
    data=b""
    headers_end = b"\r\n\r\n"
    try:
        while True:
            chunk = source.recv(4096)
            if not chunk:
                break
            data += chunk
            destination.sendall(chunk)
    except Exception as e:
        print(f"Error during forwarding: {e}")
    finally:
        source.close()
        destination.close()

    if client:
        print(data)
        header_data, body_data = data.split(headers_end, 1)
        lines = header_data.decode('utf-8').split('\n')
        first_line = lines[0].split()
        method, full_url, protocol = first_line
        host_line = next((line for line in lines if line.startswith('Host:')), None)
        host = host_line.split()[1]
        if ':' in host:
            host, port = host.split(':')
            port = int(port)
        else:
            port = 80
        method, path, headers, cookies, get_params = parse_http_request(data.decode('utf-8'))

        post_params = {}

        body = None

        # Проверка на наличие тела (например, если это POST запрос)
        if method == "POST" and "Content-Length" in headers:
            content_length = int(headers["Content-Length"])
            body = body_data[:content_length]

            # Определяем, как парсить тело запроса на основе заголовка Content-Type
            if headers.get("Content-Type") == "application/x-www-form-urlencoded":
                post_params = parse_qs(body.decode('utf-8'))

        if headers.get("Content-Encoding") == "gzip":
            body = decompress_gzip(body.encode('utf-8'))

        last_request_id = insert_request(method, path, headers, cookies, get_params, post_params, body, protocol, port)

    else:
        response_code, response_message, response_headers, response_body = parse_http_response(data)
        insert_response(response_code, response_message, response_headers, response_body, last_request_id)

def generate_cert(domain):
    print(domain)
    cert_path = os.path.join(CERTS_DIR, f'{domain}.crt')
    key_path = os.path.join(CERTS_DIR, f'{domain}.key')
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    try:
        subprocess.run(["openssl", "genrsa", "-out", key_path, "2048"])

        csr_file = f"certs/{domain}.csr"

        subprocess.run(["openssl", "req", "-new", "-key", key_path, "-out", csr_file,
                        "-subj", f"/C=RU/ST=Moscow/L=Moscow/O=MyProxy/CN={domain}"])
        
        subprocess.run(["openssl", "x509", "-req", "-in", csr_file, "-CA", CA_CERT, "-CAkey", CA_KEY,
                        "-CAcreateserial", "-out", cert_path, "-days", "365", "-sha256"])

    except subprocess.CalledProcessError as e:
        print(f"Error during OpenSSL call: {e}")
    
    return cert_path, key_path