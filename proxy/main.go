package main

import (
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"strings"
)

func handleTunnel(w http.ResponseWriter, r *http.Request) {
	targetHost := r.Host
	if !strings.Contains(targetHost, ":") {
		targetHost += ":443" // если порт не указан, добавляем порт 443 по умолчанию
	}

	// Установка соединения с целевым сервером
	serverConn, err := net.Dial("tcp", targetHost)
	if err != nil {
		http.Error(w, "Failed to connect to target host", http.StatusServiceUnavailable)
		return
	}
	defer serverConn.Close()

	// Ответ клиенту, что туннель установлен
	w.WriteHeader(http.StatusOK)
	hijacker, ok := w.(http.Hijacker)
	if !ok {
		http.Error(w, "Hijacking not supported", http.StatusInternalServerError)
		return
	}

	clientConn, _, err := hijacker.Hijack()
	if err != nil {
		http.Error(w, err.Error(), http.StatusServiceUnavailable)
		return
	}
	defer clientConn.Close()

	// Копирование данных между клиентом и сервером (туннель)
	go io.Copy(serverConn, clientConn)
	io.Copy(clientConn, serverConn)
}

func handleProxy(w http.ResponseWriter, r *http.Request) {

	// log.Println("Received request:")
	// log.Println("Method:", r.Method)
	// log.Println("URL:", r.URL.String())
	// log.Println("Host:", r.Host)
	// log.Println("Headers:")
	// for name, values := range r.Header {
	// 	for _, value := range values {
	// 		log.Println(name, ":", value)
	// 	}
	// }

	if r.Method == http.MethodConnect {
		// Если запрос - CONNECT, передаем на обработчик туннелей
		handleTunnel(w, r)
		return
	}

	r.Header.Del("Proxy-Connection")

	host := r.Host
	if host == "" {
		http.Error(w, "Host header is missing", http.StatusBadRequest)
		return
	}

	scheme := "http"
	if r.URL.Scheme == "https" || r.Method == http.MethodConnect {
		scheme = "https"
	}

	targetURL := &url.URL{
		Scheme:   scheme,
		Host:     host,
		Path:     r.URL.Path,
		RawQuery: r.URL.RawQuery,
	}

	println("Путь", targetURL.String())
	// Новый запрос, который будет отправлен на целевой сервер
	// req, err := http.NewRequest(r.Method, targetURL.String(), r.Body)
	req, err := http.NewRequest(r.Method, targetURL.String(), r.Body)
	if err != nil {
		http.Error(w, "Bad Request", http.StatusBadRequest)
		return
	}

	// Копирование заголовков
	req.Header = r.Header
	req.Host = r.Host

	log.Println("> Sending request to target server:")
	log.Println("> Method:", req.Method)
	log.Println("> URL:", req.URL.String())
	log.Println("> Host:", req.Host)
	for name, values := range req.Header {
		for _, value := range values {
			log.Printf("> %s: %s\n", name, value)
		}
	}

	// Отправка запроса
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		http.Error(w, "Failed to reach server", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	// Копирование заголовков ответа
	for name, values := range resp.Header {
		for _, value := range values {
			w.Header().Add(name, value)
		}
	}
	// Установка кода ответа
	w.WriteHeader(resp.StatusCode)

	// Копирование тела ответа
	io.Copy(w, resp.Body)
}

func main() {
	// Настройка маршрутизации на обработчик
	http.HandleFunc("/", handleProxy)
	log.Println("Proxy server running on port 8080...")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
