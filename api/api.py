import json
import subprocess
from flask import Flask, jsonify
from db import get_db_connection

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
        curl_headers.append(f'--header "{key}: {value}"')

    curl_cookies = ""
    if cookies:
        cookies_str = "; ".join([f"{key}={value}" for key, value in cookies.items()])
        curl_cookies = f" -b '{cookies_str}'"
    
    proxy = "http://proxy:8080"

    curl_cmd = f"curl -X {method} {full_url} {' '.join(curl_headers)} --proxy {proxy}{curl_cookies}"

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
    if result:
        method, path, headers, cookies, get_params, post_params, body, protocol, port = result
        response = resend_request(method, path, headers, get_params, post_params, body, cookies, protocol, port)
        print(response.returncode)

        return jsonify({
            "status_code": response.returncode
        })
    return jsonify({"error": "Request not found"}), 404

def scan_for_sql_injection(method, path, headers, cookies, get_params, post_params, body, protocol, port, request_id):

    # Хранение результатов уязвимостей
    vulnerabilities = []

    # Подстановка символов SQL-инъекции
    sql_injection_payloads = ["'", '"']

    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT response_code, response_message, response_headers, response_body FROM responses WHERE request_id = %s", (request_id, ))
    master_response = cursor.fetchall()

    cursor.close()
    conn.close()
    
    # Проверка GET параметров
    if get_params is not None:
        for key, value in get_params.items():
            for payload in sql_injection_payloads:
                modified_params = get_params.copy()
                modified_params[key] = value + payload
                
                response = resend_request(method, path, headers, cookies, modified_params, post_params, body, protocol, port)
                if response.returncode == 0:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    query = """
                    SELECT response_code, response_message, response_headers, response_body 
                    FROM responses 
                    ORDER BY id DESC 
                    LIMIT 1
                    """
                    cursor.execute(query)
                    last_response = cursor.fetchall()
                    if (master_response.response_code != last_response.responce_code or master_response.response_headers['Content-Length'] != last_response.response_headers['Content-Length']):
                        vulnerabilities.append(f"GET параметр '{key}' уязвим с payload '{payload}'")

    # Проверка POST параметров
    if post_params is not None:
        for key, value in post_params.items():
            for payload in sql_injection_payloads:
                modified_params = post_params.copy()
                modified_params[key] = value + payload
                
                response = resend_request(method, path, headers, cookies, get_params, modified_params, body, protocol, port)
                if response.returncode == 0:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    query = """
                    SELECT response_code, response_message, response_headers, response_body 
                    FROM responses 
                    ORDER BY id DESC 
                    LIMIT 1
                    """
                    cursor.execute(query)
                    last_response = cursor.fetchall()
                    if (master_response.response_code != last_response.responce_code or master_response.response_headers['Content-Length'] != last_response.response_headers['Content-Length']):
                        vulnerabilities.append(f"GET параметр '{key}' уязвим с payload '{payload}'")

    # Проверка Cookie
    for key, value in cookies.items():
        for payload in sql_injection_payloads:
            modified_cookies = cookies.copy()
            modified_cookies[key] = value + payload
            
            # Отправляем запрос
            response = resend_request(method, path, headers, cookies, get_params, modified_params, body, protocol, port)
            if response.returncode == 0:
                conn = get_db_connection()
                cursor = conn.cursor()
                query = """
                SELECT response_code, response_message, response_headers, response_body 
                FROM responses 
                ORDER BY id DESC 
                LIMIT 1
                """
                cursor.execute(query)
                last_response = cursor.fetchall()
                if (master_response.response_code != last_response.responce_code or master_response.response_headers['Content-Length'] != last_response.response_headers['Content-Length']):
                    vulnerabilities.append(f"GET параметр '{key}' уязвим с payload '{payload}'")

    return vulnerabilities


# Маршрут для сканирования запроса
@app.route('/scan/<int:id>', methods=['POST', 'GET'])
def scan(id):

    result = get_request_by_id(id)

    if result:
        method, path, headers, cookies, get_params, post_params, body, protocol, port = result
        vulnerabilities = scan_for_sql_injection(method, path, headers, cookies, get_params, post_params, body, protocol, port, id)

    # Возврат результатов сканирования
    return jsonify({"vulnerabilities": vulnerabilities})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
