import json
import os
import psycopg2

# Функция для подключения к базе данных
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "proxyDB"),
        user=os.getenv("DB_USER", "aa"),
        password=os.getenv("DB_PASSWORD", "1")
    )
    return conn

def initialize_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    drop_requests_table_query = "DROP TABLE IF EXISTS responses CASCADE;"
    drop_responses_table_query = "DROP TABLE IF EXISTS requests CASCADE;"
    
    cursor.execute(drop_responses_table_query)
    cursor.execute(drop_requests_table_query)

    create_requests_table_query = """
    CREATE TABLE IF NOT EXISTS requests (
        id SERIAL PRIMARY KEY,
        method VARCHAR(10),
        path TEXT,
        headers JSONB,
        cookies JSONB,
        get_params JSONB,
        post_params JSONB,
        body TEXT,
        protocol VARCHAR(5),
        port VARCHAR(4)
    );
    """

    create_responses_table_query = """
    CREATE TABLE IF NOT EXISTS responses (
        id SERIAL PRIMARY KEY,
        request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
        response_code INTEGER,
        response_message TEXT,
        response_headers JSONB,
        response_body TEXT
    );
    """
    
    cursor.execute(create_requests_table_query)
    cursor.execute(create_responses_table_query)
    conn.commit()

    cursor.close()
    conn.close()

# Функция для вставки данных в таблицу запросов
def insert_request_and_response(method, path, headers, cookies, get_params, post_params, body, response_code, response_message, response_headers, response_body, protocol='http', port=80):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Преобразуем словари в формат JSON
        headers_json = json.dumps(headers)
        cookies_json = json.dumps(cookies)
        get_params_json = json.dumps(get_params)
        post_params_json = json.dumps(post_params) if post_params else None
        response_headers_json = json.dumps(response_headers) if response_headers else None
        
        print(method, path, headers_json, cookies_json, get_params_json, post_params_json, body)

        # Вставляем данные в таблицу
        insert_request_query = """
        INSERT INTO requests (method, path, headers, cookies, get_params, post_params, body, protocol, port)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """

        cursor.execute(insert_request_query, (method, path, headers_json, cookies_json, get_params_json, post_params_json, body, protocol, port))
        request_id = cursor.fetchone()[0]

        insert_response_query = """
        INSERT INTO responses (request_id, response_code, response_message, response_headers, response_body)
        VALUES (%s, %s, %s, %s, %s);
        """
        cursor.execute(insert_response_query, (request_id, response_code, response_message, response_headers_json, response_body))
        
        conn.commit()

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Failed to insert request data: {e}")

def insert_request(method, path, headers, cookies, get_params, post_params, body, protocol='http', port=80):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Преобразуем словари в формат JSON
        headers_json = json.dumps(headers)
        cookies_json = json.dumps(cookies)
        get_params_json = json.dumps(get_params)
        post_params_json = json.dumps(post_params) if post_params else None
        
        print(method, path, headers_json, cookies_json, get_params_json, post_params_json, body)

        # Вставляем данные в таблицу
        insert_request_query = """
        INSERT INTO requests (method, path, headers, cookies, get_params, post_params, body, protocol, port)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """

        cursor.execute(insert_request_query, (method, path, headers_json, cookies_json, get_params_json, post_params_json, body, protocol, port))
        request_id = cursor.fetchone()[0]
        conn.commit()

        cursor.close()
        conn.close()

        return request_id # возвращаем request id
    
    except Exception as e:
        print(f"Failed to insert request data: {e}")

def insert_response(response_code, response_message, response_headers, response_body, request_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Преобразуем словари в формат JSON
        response_headers_json = json.dumps(response_headers) if response_headers else None
        
        insert_response_query = """
        INSERT INTO responses (request_id, response_code, response_message, response_headers, response_body)
        VALUES (%s, %s, %s, %s, %s);
        """
        cursor.execute(insert_response_query, (request_id, response_code, response_message, response_headers_json, response_body))
        
        conn.commit()

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Failed to insert request data: {e}")


def setup_database():
    print("Initializing database...")
    initialize_db()
    print("Database initialized.")
