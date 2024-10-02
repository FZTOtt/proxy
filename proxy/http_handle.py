import socket
from db import insert_request_and_response
from help import decompress_gzip, forward, get_post_parameters, parse_body, parse_http_request, parse_http_response


def handle_http_request(client_socket, request):
    
    method, path, headers, cookies, get_params = parse_http_request(request)

    post_params = get_post_parameters(method, headers, client_socket)
    
    body = parse_body(client_socket, method, headers)

    # Разбираем заголовок
    lines = request.split('\n')
    first_line = lines[0].split()
    if len(first_line) < 3:
        print("Invalid HTTP request")
        client_socket.close()
        return
    
    method, full_url, protocol = first_line
    # Извлекаем хост и порт
    host_line = next((line for line in lines if line.startswith('Host:')), None)
    if not host_line:
        print("No Host header found")
        client_socket.close()
        return
    
    host = host_line.split()[1]
    if ':' in host:
        host, port = host.split(':')
        port = int(port)
    else:
        port = 80
    
    print(f"Forwarding HTTP request to {host}:{port}")
    
    # Подключаемся к целевому серверу
    try:
        server_socket = socket.create_connection((host, port))
    except Exception as e:
        print(f"Failed to connect to target server: {e}")
        client_socket.close()
        return

    path = full_url.split(host, 1)[1] if host in full_url else full_url
    request = request.replace(full_url, path, 1)

    request = "\n".join([line for line in request.split("\n") if not line.startswith("Proxy-Connection")])

    # Пересылаем запрос серверу
    server_socket.sendall(request.encode('utf-8'))

    # Перехватываем ответ от сервера
    response_code, response_message, response_headers, response_body = forward(server_socket, client_socket)

    print(protocol.split('/')[0], port)
    
    insert_request_and_response(method, path, headers, cookies, get_params, post_params, body, response_code, response_message, response_headers, response_body, protocol.split('/')[0], port)
