import socket
import threading
import time
import random
import numpy as np
from src.utils.logger_setup import get_logger
from tensorflow.keras.applications.resnet50 import ResNet50, preprocess_input, decode_predictions
from tensorflow.keras.preprocessing import image

class Service:
    def __init__(self, host, port, target_host, target_port,
                 service_time_mean, service_time_std_dev,
                 is_target_source=False, service_name="Service"):

        self.host = host
        self.port = port
        self.target_host = target_host
        self.target_port = target_port
        self.service_time_mean = service_time_mean
        self.service_time_std_dev = service_time_std_dev
        self.is_target_source = is_target_source
        self.service_name = service_name if "_Managed_By_" in service_name else f"{service_name}_{port}"

        self.logger = get_logger(self.service_name)

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.current_message_to_process = None
        self.processing_lock = threading.Lock()
        self.logger.info(f"Ouvindo em {self.host}:{self.port}")

        # Carregar modelo de IA apenas uma vez
        self.model = ResNet50(weights="imagenet")
        self.logger.info("Modelo ResNet50 carregado.")

    def _register_time(self, message_parts):
        current_time = time.time()
        try:
            last_timestamp_str = message_parts[-2]
            last_timestamp = float(last_timestamp_str)
            time_since_last = (current_time - last_timestamp) * 1000
        except (ValueError, IndexError):
            last_timestamp = current_time
            time_since_last = 0.0

        message_parts.append(f"{current_time:.6f}")
        message_parts.append(f"{time_since_last:.3f}")
        return message_parts

    def _simulate_processing(self, message_parts):
        start_time = time.time()
        try:
            img_path = "sample.png"
            img = image.load_img(img_path, target_size=(224, 224))
            x = image.img_to_array(img)
            x = np.expand_dims(x, axis=0)
            x = preprocess_input(x)

            preds = self.model.predict(x, verbose=0)
            decode_predictions(preds, top=1)

        except Exception as e:
            self.logger.error(f"Erro no processamento IA: {e}")
            time.sleep(1.0)

        end_time = time.time()
        tempo_ms = (end_time - start_time) * 1000
        self.logger.debug(f"Tempo IA: {tempo_ms:.3f} ms")

        message_parts.append(f"{end_time:.6f}")
        message_parts.append(f"{tempo_ms:.3f}")
        return message_parts

    def _send_to_target(self, message):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as target_socket:
                target_socket.connect((self.target_host, self.target_port))
                target_socket.sendall(message.encode('utf-8'))
                self.logger.debug(f"Enviada para destino: {message[:30].strip()}...")
        except Exception as e:
            self.logger.error(f"Erro ao enviar para destino: {e}")

    def handle_client_connection(self, client_socket, address):
        self.logger.info(f"Conexão aceita de {address}")
        try:
            data = client_socket.recv(1024)
            if not data:
                return

            message = data.decode('utf-8').strip()
            if message.lower() == "ping":
                with self.processing_lock:
                    status = "busy" if self.current_message_to_process else "free"
                client_socket.sendall(status.encode('utf-8'))
                return

            with self.processing_lock:
                if self.current_message_to_process:
                    client_socket.sendall("busy".encode('utf-8'))
                    return
                self.current_message_to_process = message

            client_socket.sendall("ack_received".encode('utf-8'))

            message_parts = message.split(';')
            message_parts = self._register_time(message_parts)
            message_parts = self._simulate_processing(message_parts)

            processed_message = ";".join(message_parts)
            self._send_to_target(processed_message + "\n")

            with self.processing_lock:
                self.current_message_to_process = None

        except Exception as e:
            self.logger.error(f"Erro com {address}: {e}")
        finally:
            client_socket.close()

    def start(self):
        threading.current_thread().name = f"{self.service_name}_AcceptThread"
        while True:
            try:
                client_socket, address = self.server_socket.accept()
                thread = threading.Thread(
                    target=self.handle_client_connection,
                    args=(client_socket, address),
                    name=f"{self.service_name}_Conn_{address[1]}"
                )
                thread.daemon = True
                thread.start()
            except Exception as e:
                self.logger.error(f"Erro ao aceitar conexão: {e}")
                break

        if self.server_socket:
            self.server_socket.close()
            self.logger.info("Socket fechado.")
