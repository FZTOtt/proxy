# Основной прокси-сервер, который обрабатывает как HTTP, так и HTTPS запросы
import os
import socket
from threading import Thread

from db import setup_database
from help import CERTS_DIR
from http_handle import handle_http_request
from https_handle import handle_https_tunnel



def start_proxy(port=8080):
    if not os.path.exists(CERTS_DIR):
        os.makedirs(CERTS_DIR)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('0.0.0.0', port))
        sock.listen(5)
        print(f"Proxy server listening on port {port}...")

        while True:
            client_socket, address = sock.accept()
            print(f"Connection from {address}")

            # Получаем первый запрос от клиента
            request = client_socket.recv(4096).decode('utf-8')
            
            # Если это HTTPS (CONNECT), то обрабатываем туннель
            if request.startswith('CONNECT'):
                Thread(target=handle_https_tunnel, args=(client_socket, request)).start()
                pass
            else:
                # Обрабатываем HTTP-запрос
                Thread(target=handle_http_request, args=(client_socket, request)).start()

if __name__ == '__main__':
    setup_database()
    start_proxy()
