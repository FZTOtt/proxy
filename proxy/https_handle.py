import socket
import ssl
from threading import Thread

from help import forward_https, generate_cert

def handle_https_tunnel(client_socket, request):
    try:

        # Парсим первую строку запроса
        lines = request.split('\n')
        first_line = lines[0].split()
        if len(first_line) < 2 or first_line[0] != "CONNECT":
            print("Invalid CONNECT request")
            client_socket.close()
            return
        
        client_socket.sendall(b"HTTP/1.0 200 Connection established\r\n\r\n")

        # Получаем хост и порт
        target_host, target_port = first_line[1].split(":")
        target_port = int(target_port)
        
        print(f"Подключились к {target_host}:{target_port}")

        # Коннект к целевому серверу
        try:
            server_socket = socket.create_connection((target_host, target_port))
            context = ssl.create_default_context()
            server_socket = context.wrap_socket(server_socket, server_hostname=target_host)
            print(f"Настроили {target_host}:{target_port} SSL")
        except Exception as e:
            print(f"Не подключились к серверу: {e}")
            client_socket.close()
            return
        
        cert_path, key_path = generate_cert(target_host)

        print('genned sert')

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        client_socket = context.wrap_socket(client_socket, server_side=True)

        Thread(target=forward_https, args=(client_socket, server_socket, True)).start()
        Thread(target=forward_https, args=(server_socket, client_socket, False)).start()

    except Exception as e:
        print(f"https handle error: {e}")
        client_socket.close()
        server_socket.close()