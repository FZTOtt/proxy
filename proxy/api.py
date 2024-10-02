import json
import subprocess
from flask import Flask, jsonify
from db import get_db_connection, insert_response

app = Flask(__name__)

# Подключение к базе данных
def get_request_by_id(request_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT method, path, headers, cookies, get_params, post_params, body, protocol, port FROM requests WHERE id = %s"
    cursor.execute(query, (request_id,))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return result

# Повторная отправка запроса
def resend_request(method, path, headers, get_params=None, post_params=None, body=None, cookies=None, protocol="HTTP", port=80):
    import requests
    
    # Восстановление URL из заголовков
    host = headers.get("Host").strip()  # получаем Host
    
    # Определяем протокол, если явно указано "HTTP" или "HTTPS"
    if protocol == "HTTPS" or port == 443:
        protocol = "https"
    else:
        protocol = "http"

    # Если порт не 80 или 443, добавляем его к URL
    if port not in [80, 443]:
        full_url = f"{protocol}://{host}:{port}{path}"
    else:
        full_url = f"{protocol}://{host}{path}"

    if get_params:
        params = '&'.join([f"{k}={v[0]}" for k, v in get_params.items()])
        full_url += f"?{params}"

    # Конвертируем заголовки из JSON обратно в формат словаря
    curl_headers = []
    for key, value in headers.items():
        curl_headers.append(f"--header '{key}: {value}'")

    curl_cookies = ""
    if cookies:
        cookies_str = "; ".join([f"{key}={value}" for key, value in cookies.items()])
        curl_cookies = f" -b '{cookies_str}'"
    
    proxy = "http://localhost:8080"

    # curl_cmd = f"curl -X {method} {full_url} {' '.join(curl_headers)} --proxy {proxy}{curl_cookies}"
    curl_cmd = f"curl -v -x {proxy} {full_url} " #{method} {' '.join(curl_headers)}{curl_cookies} "

    if method == "POST" and post_params:
        data = '&'.join([f"{k}={v[0]}" for k, v in post_params.items()])
        curl_cmd += f" --data '{data}'"
    elif method == "POST" and body:
        curl_cmd += f" --data '{body}'"

    print(f"Executing: {curl_cmd}")
    
    # Отправка запроса через прокси
    try:
        # Выполняем команду curl
        result = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)

        print(result.stdout, result.stderr)
        
        
        # Проверяем на ошибки выполнения
        if result.returncode != 0:
            print(f"Ошибка при выполнении curl: {result.stderr}")
            return None
        
        # Возвращаем результат
        return result
    except Exception as e:
        print(f"Не удалось повторить запрос: {e}")
        return None

# Маршрут для списка запросов
@app.route('/requests', methods=['GET'])
def list_requests():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM requests")
    requests = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(requests)

# Маршрут для вывода одного запроса по ID
@app.route('/requests/<int:id>', methods=['GET'])
def get_request(id):
    result = get_request_by_id(id)
    if result:
        method, path, headers, cookies, get_params, post_params, body, protocol, port = result
        return jsonify({
            "method": method,
            "path": path,
            "headers": headers,
            "cookies": cookies,
            "get_params": get_params,
            "post_params": post_params,
            "body": body,
            "protocol": protocol,
            "port": port
        })
    return jsonify({"error": "Request not found"}), 404

# Маршрут для повторной отправки запроса
@app.route('/repeat/<int:id>', methods=['GET'])
def repeat_request(id):
    result = get_request_by_id(id)
    print(result)
    if result:
        method, path, headers, cookies, get_params, post_params, body, protocol, port = result
        response = resend_request(method, path, headers, get_params, post_params, body, cookies, protocol, port)
        # print(response.returncode, response.reason, dict(response.headers), id)
        print(response.returncode)
        # Вставляем данные ответа в базу
        # insert_response(response.returncode, response.reason, dict(response.headers), response.body, id)

        return jsonify({
            "status_code": response.returncode,
            # "headers": dict(response.headers),
            # "body": response.text
        })
    return jsonify({"error": "Request not found"}), 404

def scan_for_sql_injection(method, path, headers, get_params, post_params, cookies):
    import requests
    
    # Функция для выполнения запроса и получения ответа
    def send_request(method, url, headers, get_params, post_params, cookies):
        if method == "POST":
            response = requests.post(url, headers=headers, params=get_params, data=post_params, cookies=cookies)
        else:
            response = requests.get(url, headers=headers, params=get_params, cookies=cookies)
        return response

    # Восстановление базового URL
    host = headers.get("Host").strip()
    protocol = "https" if "443" in host or host.endswith(".ru") else "http"
    base_url = f"{protocol}://{host}{path}"
    
    # Хранение результатов уязвимостей
    vulnerabilities = []

    # Подстановка символов SQL-инъекции
    sql_injection_payloads = ["'", '"']
    
    # Проверка GET параметров
    for key, value in get_params.items():
        for payload in sql_injection_payloads:
            modified_params = get_params.copy()
            modified_params[key] = value + payload
            
            # Отправляем запрос
            response = send_request(method, base_url, headers, modified_params, post_params, cookies)
            if response is not None:
                if response.status_code != 200 or len(response.content) != len(response.content):
                    vulnerabilities.append(f"GET параметр '{key}' уязвим с payload '{payload}'")

    # Проверка POST параметров
    for key, value in post_params.items():
        for payload in sql_injection_payloads:
            modified_params = post_params.copy()
            modified_params[key] = value + payload
            
            # Отправляем запрос
            response = send_request(method, base_url, headers, get_params, modified_params, cookies)
            if response is not None:
                if response.status_code != 200 or len(response.content) != len(response.content):
                    vulnerabilities.append(f"POST параметр '{key}' уязвим с payload '{payload}'")

    # Проверка Cookie
    for key, value in cookies.items():
        for payload in sql_injection_payloads:
            modified_cookies = cookies.copy()
            modified_cookies[key] = value + payload
            
            # Отправляем запрос
            response = send_request(method, base_url, headers, get_params, post_params, modified_cookies)
            if response is not None:
                if response.status_code != 200 or len(response.content) != len(response.content):
                    vulnerabilities.append(f"Cookie '{key}' уязвим с payload '{payload}'")

    return vulnerabilities


# Маршрут для сканирования запроса
@app.route('/scan/<int:id>', methods=['POST', 'GET'])
def scan(id):
    # Извлечение данных из базы данных по заданному ID
    connection = get_db_connection()  # Ваша функция для подключения к БД
    cursor = connection.cursor()
    
    # Извлечение запроса по ID
    cursor.execute("SELECT * FROM requests WHERE id = %s", (id,))
    request_data = cursor.fetchone()

    if request_data is None:
        return jsonify({"error": "Request not found"}), 404

    method = request_data[1]  # method
    path = request_data[2]    # path
    headers = request_data[3]  # headers
    cookies = request_data[4]   # cookies
    get_params = request_data[5]  # get_params
    post_params = request_data[6]  # post_params
    body = request_data[7]         # body (если нужно)

    # Конвертация заголовков и параметров из JSON
    headers = json.loads(headers)
    get_params = json.loads(get_params) if get_params else {}
    post_params = json.loads(post_params) if post_params else {}
    cookies = json.loads(cookies) if cookies else {}

    # Запуск сканирования
    vulnerabilities = scan_for_sql_injection(method, path, headers, get_params, post_params, cookies)

    # Возврат результатов сканирования
    return jsonify({"vulnerabilities": vulnerabilities})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
