# main.py

import threading
import time
import yaml
from pathlib import Path

from src.components.source import Source
from src.components.load_balancer import LoadBalancer
from src.utils.logger_setup import get_logger

def load_config() -> dict:
    cfg_path = Path(__file__).parent / "config" / "config.yml"
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

if __name__ == "__main__":
    cfg         = load_config()
    SOURCE_CFG  = cfg["source"]
    LB1_CFG     = cfg["lb1"]
    LB2_CFG     = cfg["lb2"]

    main_logger = get_logger("MainOrchestrator")

    print("\n" + "="*60)
    print("      INÍCIO DA SIMULAÇÃO PASID-VALIDATOR")
    print("="*60 + "\n")
    main_logger.info("Iniciando o sistema PASID-VALIDATOR em Python...")

    threads = []

    # LB 2
    print("-"*60)
    print(f" CONFIGURANDO LoadBalancer 2 ({LB2_CFG['lb_name']})")
    print("-"*60)
    main_logger.info(f"--- Configurando LoadBalancer 2 ({LB2_CFG['lb_name']}) ---")
    lb2 = LoadBalancer(
        host=LB2_CFG["host"],
        port=LB2_CFG["port"],
        max_queue_size=LB2_CFG["max_queue_size"],
        initial_num_services=LB2_CFG["initial_num_services"],
        service_config=LB2_CFG["service_config"],
        lb_name=LB2_CFG["lb_name"]
    )
    lb2_thread = threading.Thread(target=lb2.start, name=f"{LB2_CFG['lb_name']}_MainThread", daemon=True)
    threads.append(lb2_thread)

    # LB 1
    print("\n" + "-"*60)
    print(f" CONFIGURANDO LoadBalancer 1 ({LB1_CFG['lb_name']})")
    print("-"*60)
    main_logger.info(f"--- Configurando LoadBalancer 1 ({LB1_CFG['lb_name']}) ---")
    lb1 = LoadBalancer(
        host=LB1_CFG["host"],
        port=LB1_CFG["port"],
        max_queue_size=LB1_CFG["max_queue_size"],
        initial_num_services=LB1_CFG["initial_num_services"],
        service_config=LB1_CFG["service_config"],
        lb_name=LB1_CFG["lb_name"]
    )
    lb1_thread = threading.Thread(target=lb1.start, name=f"{LB1_CFG['lb_name']}_MainThread", daemon=True)
    threads.append(lb1_thread)

    # Start LBs
    print("\n" + "."*60)
    print(" Iniciando LoadBalancers (aguardando 3 segundos)...")
    print("."*60 + "\n")
    lb2_thread.start()
    print(f" → {LB2_CFG['lb_name']} thread iniciada.")
    lb1_thread.start()
    print(f" → {LB1_CFG['lb_name']} thread iniciada.")
    main_logger.info("Aguardando LoadBalancers iniciarem (3 segundos)...")
    time.sleep(3)

    # Source
    print("\n" + "-"*60)
    print(f" CONFIGURANDO Source ({SOURCE_CFG['source_name']})")
    print("-"*60)
    main_logger.info(f"--- Configurando Source ({SOURCE_CFG['source_name']}) ---")
    source_node = Source(
        listen_host=SOURCE_CFG["listen_host"],
        listen_port=SOURCE_CFG["listen_port"],
        target_lb1_host=SOURCE_CFG["target_lb1_host"],
        target_lb1_port=SOURCE_CFG["target_lb1_port"],
        arrival_delay_ms=SOURCE_CFG["arrival_delay_ms"],
        max_messages_per_cycle=SOURCE_CFG["max_messages_per_cycle"],
        qtd_services_variation=SOURCE_CFG["qtd_services_variation"],
        config_target_lb_host=SOURCE_CFG["config_target_lb_host"],
        config_target_lb_port=SOURCE_CFG["config_target_lb_port"],
        source_name=SOURCE_CFG["source_name"]
    )
    source_thread = threading.Thread(
        target=source_node.start,
        name=f"{SOURCE_CFG['source_name']}_ExperimentThread"
    )
    threads.append(source_thread)

    print(f" → Thread para {SOURCE_CFG['source_name']} criada.")
    main_logger.info(f"Thread para {SOURCE_CFG['source_name']} criada.")
    source_thread.start()
    print(f" → {SOURCE_CFG['source_name']} thread iniciada. Iniciando experimento...\n")
    main_logger.info(f"{SOURCE_CFG['source_name']} thread iniciada. O experimento está em andamento.")

    source_thread.join()

    print("\n" + "="*60)
    print("       SIMULAÇÃO CONCLUÍDA")
    print("="*60 + "\n")
    main_logger.info("--- Simulação PASID-VALIDATOR Concluída ---")
