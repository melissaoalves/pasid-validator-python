import socket
import threading
import time
import statistics
from src.utils.logger_setup import get_logger 
import matplotlib.pyplot as plt
from collections import defaultdict
import itertools

class Source:
    def __init__(self, listen_host, listen_port, target_lb1_host, target_lb1_port,
             arrival_delay_ms, images_per_cycle_list,
             qtd_services_variation, config_target_lb_host, config_target_lb_port,
             source_name="Source"):

        self.listen_host = listen_host
        self.listen_port = listen_port
        self.target_lb1_host = target_lb1_host
        self.target_lb1_port = target_lb1_port
        self.arrival_delay_sec = arrival_delay_ms / 1000.0
        self.images_per_cycle_list = [int(x) for x in images_per_cycle_list]
        self.qtd_services_variation = qtd_services_variation
        self.config_target_lb_host = config_target_lb_host
        self.config_target_lb_port = config_target_lb_port
        self.source_name = source_name

        self.logger = get_logger(f"{self.source_name}_{self.listen_port}")

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.listen_host, self.listen_port))
        self.server_socket.listen(5)
        self.logger.info(f"Ouvindo por respostas em {self.listen_host}:{self.listen_port}")

        self.received_messages_data = []
        self.response_times_ms_current_cycle = []
        self.message_counter_current_cycle = 0
        self.total_messages_received_current_cycle = 0

        self.lock = threading.Lock()
        self.all_cycles_completed_event = threading.Event()
        self.experiment_results = []


    def _send_config_message(self, num_services_to_configure):
        config_message = f"config;{num_services_to_configure};\n"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as config_socket:
                config_socket.connect((self.config_target_lb_host, self.config_target_lb_port))
                config_socket.sendall(config_message.encode('utf-8'))
                self.logger.info(f"Mensagem de config '{config_message.strip()}' enviada para {self.config_target_lb_host}:{self.config_target_lb_port}")
                response = config_socket.recv(1024).decode('utf-8')
                self.logger.info(f"Resposta da config do LB: {response.strip()}")
                if "Configuration has finished" not in response:
                    self.logger.warning("LB não confirmou a configuração corretamente.")
        except Exception as e:
            self.logger.error(f"Erro ao enviar mensagem de config: {e}")
            return False
        return True

    def _send_message_to_lb1(self, cycle_id, message_id):
        timestamp_saida_source = time.time()
        message = f"{cycle_id};{message_id};{timestamp_saida_source:.6f}"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.target_lb1_host, self.target_lb1_port))
                s.sendall(message.encode('utf-8'))
                # self.logger.debug(f"Mensagem {cycle_id}-{message_id} enviada para LB1: {message}")
        except ConnectionRefusedError:
            self.logger.error(f"Conexão recusada por LB1 ao enviar msg {cycle_id}-{message_id}. O LB1 está rodando?")
        except Exception as e:
            self.logger.error(f"Erro ao enviar msg {cycle_id}-{message_id} para LB1: {e}")

    def _calculate_mrt_and_stddev(self, response_times_ms):
        if not response_times_ms:
            return 0, 0
        mean_mrt = statistics.mean(response_times_ms)
        std_dev = statistics.stdev(response_times_ms) if len(response_times_ms) > 1 else 0
        return mean_mrt, std_dev

    def _process_received_message(self, received_message_str):
        self.logger.debug(f"MENSAGEM COMPLETA RETORNADA AO SOURCE: {received_message_str.strip()}")
        parts = received_message_str.strip().split(';')
        try:
            cycle_id_str, msg_id_str, ts_saida_source_str = parts[0], parts[1], parts[2]
            ts_saida_source = float(ts_saida_source_str)
            ts_chegada_source_final = time.time()
            mrt_ms = (ts_chegada_source_final - ts_saida_source) * 1000.0

            with self.lock:
                self.total_messages_received_current_cycle += 1
                self.response_times_ms_current_cycle.append(mrt_ms)
                self.received_messages_data.append({
                    'cycle_id': int(cycle_id_str),
                    'msg_id': int(msg_id_str),
                    'mrt_ms': mrt_ms,
                    'full_message': received_message_str.strip()
                })
                self.logger.info(f"Mensagem {cycle_id_str}-{msg_id_str} recebida. MRT: {mrt_ms:.3f} ms. Total no ciclo: {self.total_messages_received_current_cycle}/{self.message_counter_current_cycle}")
                self.logger.debug(f"Conteúdo msg {cycle_id_str}-{msg_id_str} recebida: {received_message_str.strip()}")


        except (IndexError, ValueError) as e:
            self.logger.error(f"Erro ao processar mensagem recebida '{received_message_str}': {e}")

    def _listen_for_responses(self):
        while not self.all_cycles_completed_event.is_set():
            try:
                self.server_socket.settimeout(1.0)
                client_socket, address = self.server_socket.accept()
                # self.logger.debug(f"Conexão de resposta de {address}")
                try:
                    data = client_socket.recv(2048)
                    if data:
                        self._process_received_message(data.decode('utf-8'))
                except socket.timeout:
                    self.logger.warning(f"Timeout ao receber dados de {address}")
                except Exception as e_recv:
                    self.logger.error(f"Erro ao receber de {address}: {e_recv}")
                finally:
                    client_socket.close()
            except socket.timeout:
                continue
            except Exception as e_accept:
                if not self.all_cycles_completed_event.is_set():
                    self.logger.error(f"Erro ao aceitar conexão de resposta: {e_accept}")
                break
        self.logger.info("Listener de respostas encerrado.")

    def run_experiment_cycles(self):
        listener_thread = threading.Thread(target=self._listen_for_responses, name=f"{self.source_name}_ListenerThread")
        listener_thread.daemon = True
        listener_thread.start()

        combinations = list(itertools.product(self.qtd_services_variation, self.images_per_cycle_list))
        total_cycles = len(combinations)

        for cycle_idx, (num_services, total_images) in enumerate(combinations):
            self.logger.info(f"=== INICIANDO CICLO {cycle_idx + 1}/{total_cycles} | Serviços: {num_services} | Imagens: {total_images} ===")

            if not self._send_config_message(num_services):
                self.logger.error(f"Falha ao configurar LB para {num_services} serviços. Abortando ciclo.")
                continue

            self.logger.info("Aguardando LB reconfigurar (5 segundos)...")
            time.sleep(5)

            with self.lock:
                self.response_times_ms_current_cycle.clear()
                self.message_counter_current_cycle = 0
                self.total_messages_received_current_cycle = 0

            for _ in range(total_images):
                with self.lock:
                    self.message_counter_current_cycle += 1
                self._send_message_to_lb1(cycle_id=cycle_idx, message_id=self.message_counter_current_cycle)
                time.sleep(self.arrival_delay_sec)

            self.logger.info(f"Todas as {total_images} imagens do ciclo {cycle_idx+1} enviadas. Aguardando respostas...")

            cycle_timeout_seconds = 60
            start_wait_time = time.time()
            while True:
                with self.lock:
                    if self.total_messages_received_current_cycle >= self.message_counter_current_cycle:
                        self.logger.info(f"Todas as {self.total_messages_received_current_cycle} respostas do ciclo {cycle_idx+1} recebidas.")
                        break
                if time.time() - start_wait_time > cycle_timeout_seconds:
                    self.logger.warning(f"Timeout esperando respostas para o ciclo {cycle_idx+1}. Recebidas: {self.total_messages_received_current_cycle}/{self.message_counter_current_cycle}")
                    break
                time.sleep(0.5)

            with self.lock:
                mrt_ciclo, std_dev_ciclo = self._calculate_mrt_and_stddev(self.response_times_ms_current_cycle)
                tempo_total_envio = total_images * self.arrival_delay_sec
                arrival_rate = total_images / tempo_total_envio if tempo_total_envio > 0 else 0
                self.logger.info(f"=== RESULTADOS CICLO {cycle_idx + 1} ({num_services} serviço(s)) ===")
                self.logger.info(f"MRT: {mrt_ciclo:.3f} ms | SD: {std_dev_ciclo:.3f} ms | Arrival Rate: {arrival_rate:.2f} msg/s")

                self.experiment_results.append({
                    'cycle_id': cycle_idx,
                    'qtd_services': num_services,
                    'arrival_rate': arrival_rate,
                    'num_images': total_images,
                    'mrt_ms': mrt_ciclo,
                    'std_dev_ms': std_dev_ciclo,
                    'raw_mrts_ms': list(self.response_times_ms_current_cycle)
                })

        self.all_cycles_completed_event.set()
        listener_thread.join(timeout=2)

        try:
            self.server_socket.close()
            self.logger.info("Socket de escuta do Source fechado.")
        except Exception as e:
            self.logger.error(f"Erro ao fechar socket do Source: {e}")

        self.logger.info("=== EXPERIMENTO COMPLETO ===")
        for result in self.experiment_results:
            self.logger.info(
                f"Ciclo {result['cycle_id']+1} (Serviços: {result['qtd_services']} | Imagens: {result['num_images']} | Rate: {result['arrival_rate']:.2f}): MRT={result['mrt_ms']:.2f}ms"
            )

        self.print_final_times_like_java_feed()

    def print_final_times_like_java_feed(self):
        self.logger.info("--- Tempos Intermediários Médios (Tx) ---")
        expected_delta_indices = {
            "T1": 4, "T2": 6, "T3": 10, "T4": 14, "T5": 18
        }
        intermediate_times_map = {key: [] for key in expected_delta_indices}

        if not self.received_messages_data:
            self.logger.debug("print_final_times: Nenhuma mensagem recebida para extrair tempos Tx.")
            for t_label in sorted(expected_delta_indices.keys()):
                 self.logger.info(f"{t_label} = N/A (sem dados)")
            return

        for msg_data in self.received_messages_data:
            parts = msg_data['full_message'].strip().split(';')
            # self.logger.debug(f"print_final_times: Processando msg com {len(parts)} partes: {msg_data['full_message'][:60]}...")

            for t_label, idx in expected_delta_indices.items():
                if idx < len(parts):
                    try:
                        delta_val_str = parts[idx]
                        delta_val = float(delta_val_str)
                        intermediate_times_map[t_label].append(delta_val)
                    except ValueError:
                        self.logger.warning(f"print_final_times: Não foi possível converter delta '{delta_val_str}' para {t_label} na msg: {msg_data['full_message'][:70]}...")
                    except IndexError:
                        pass 
                # else:
                    # self.logger.debug(f"print_final_times: Mensagem muito curta ({len(parts)} partes) para extrair {t_label} (índice {idx}).")
        
        if not any(val for val_list in intermediate_times_map.values() for val in val_list if val_list):
            self.logger.warning("print_final_times: Nenhum tempo Tx válido pôde ser extraído das mensagens recebidas.")
            for t_label in sorted(expected_delta_indices.keys()):
                 self.logger.info(f"{t_label} = N/A (erro na extração geral)")
            return

        for t_label, times_list in sorted(intermediate_times_map.items()):
            if times_list:
                avg_time = statistics.mean(times_list)
                self.logger.info(f"{t_label} = {avg_time:.3f} ms")
            else:
                self.logger.info(f"{t_label} = N/A (sem dados válidos para este T ou mensagens incompletas)")

    def gerar_grafico_mrt(self):
        grouped = defaultdict(list)
        for res in self.experiment_results: 
            grouped[res['qtd_services']].append((res['num_images'], res['mrt_ms']))

        plt.figure(figsize=(10, 6))
        for qtd_services, values in grouped.items():
            values.sort()
            x = [v[0] for v in values]
            y = [v[1] for v in values]
            plt.plot(x, y, marker='o', label=f'{qtd_services} serviço(s)')

        plt.xlabel("Quantidade de Imagens por Ciclo")
        plt.ylabel("MRT (ms)")
        plt.title("Tempo Médio de Resposta (MRT) por Quantidade de Imagens")
        plt.legend(title="Qtd. Serviços")
        plt.grid(True)
        plt.tight_layout()
        plt.savefig("entrega2.png")

        

    def start(self):
        self.run_experiment_cycles()
        self.print_final_times_like_java_feed()
        self.gerar_grafico_mrt()
