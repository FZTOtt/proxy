import json
from flask import Flask, jsonify
from db import get_db_connection, insert_response

app = Flask(__name__)

# Подключение к базе данных
def get_request_by_id(request_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT method, path, headers, cookies, get_params, post_params, body FROM requests WHERE id = %s"
    cursor.execute(query, (request_id,))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return result

# Повторная отправка запроса
def resend_request(method, path, headers, post_params=None, body=None):
    import requests
    
    # Восстановление URL из заголовков
    host = headers.get("Host").strip()  # получаем Host
    protocol = "https" if "443" in host or host.endswith(".ru") else "http"  # определяем протокол
    full_url = f"{protocol}://{host}{path}"  # восстанавливаем полный URL

    # Конвертируем заголовки из JSON обратно в формат словаря
    headers = {k: v for k, v in headers.items() if k != 'Host'}
    
    proxies = {
        "http": "http://localhost:8080",
        "https": "http://localhost:8080"
    }
    
    # Отправка запроса через прокси
    try:
        if method == "POST":
            response = requests.post(full_url, data=post_params, headers=headers, proxies=proxies)
        elif method == "GET":
            response = requests.get(full_url, headers=headers, proxies=proxies)
        
        return response
    except requests.exceptions.RequestException as e:
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
        method, path, headers, cookies, get_params, post_params, body = result
        return jsonify({
            "method": method,
            "path": path,
            "headers": headers,
            "cookies": cookies,
            "get_params": get_params,
            "post_params": post_params,
            "body": body
        })
    return jsonify({"error": "Request not found"}), 404

# Маршрут для повторной отправки запроса
@app.route('/repeat/<int:id>', methods=['POST'])
def repeat_request(id):
    result = get_request_by_id(id)
    if result:
        method, path, headers, cookies, get_params, post_params, body = result
        response = resend_request(method, path, headers, post_params, body)

        # Вставляем данные ответа в базу
        insert_response(response.status_code, response.reason, dict(response.headers), response.text, id)

        return jsonify({
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text
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
@app.route('/scan/<int:id>', methods=['POST'])
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
