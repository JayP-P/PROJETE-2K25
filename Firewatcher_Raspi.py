import cv2
import numpy as np
from tflite_runtime.interpreter import Interpreter # Biblioteca otimizada para Pi
import time
import serial
import paho.mqtt.client as mqtt
import os
import sys

# --- CONFIGURAÇÕES ---
base_dir = "/home/jpime/Documents/Firewatcher"
MODEL_PATH_1 = os.path.join(base_dir, "tflite_learn_779649_31.tflite")
MODEL_PATH_2 = os.path.join(base_dir, "tflite_learn_782796_3.tflite")

DETECTION_THRESHOLD_1 = 0.65
DETECTION_THRESHOLD_2 = 0.70

# --- DEFINIÇÃO DAS CLASSES ---
LABELS_1 = ['uncertain', 'fire']
LABELS_2 = ['no_smoke', 'smoke']

# --- CONFIGURAÇÃO DO CICLO ---
TRIGGER_COUNT_THRESHOLD = 10
TRIGGER_COUNT_RESET_SECONDS = 3.0
COOLDOWN_SECONDS = 40.0

# --- CONFIGURAÇÃO SERIAL ---
# Porta serial principal do GPIO do Raspberry Pi. '/dev/serial0' é um link simbólico seguro.
SERIAL_PORT = '/dev/serial0' 
BAUD_RATE = 115200
# Lista de IDs de módulos que o sistema DEVE receber antes de iniciar a detecção.
REQUIRED_MODULES = ["Modulo_A", "Modulo_B"]

# --- CONFIGURAÇÃO MQTT ---
MQTT_BROKER = 'broker.emqx.io'
MQTT_PORT = 1883
MQTT_TOPIC = 'Purebatata'
MQTT_KEEPALIVE_INTERVAL = 300 

# --- Margens e Configurações Gerais ---
MARGIN_HORIZONTAL = 0.05
MARGIN_VERTICAL = 0.05
IP_CAMERA_URL = "rtsp://admin:projete3103@192.168.0.15:554/views"

# ===================================================================
# --- FUNÇÕES GLOBAIS E DE CALLBACK ---
# ===================================================================

def on_connect(client, userdata, flags, rc):
    """Callback para conexão MQTT."""
    if rc == 0:
        print("Conectado ao Broker MQTT com sucesso!")
    else:
        print(f"Falha ao conectar ao Broker MQTT, código de retorno: {rc}\n")

def publish_mqtt_status(detection_status):
    """Publica o status da detecção e os dados dos módulos via MQTT."""
    global last_mqtt_send_time
    if not client or not serial_data_storage:
        if not serial_data_storage: print("\n[MQTT] Aviso: Nenhuma data de módulo serial para enviar.")
        return

    print(f"\n--- Preparando para enviar Status MQTT (Status: {detection_status}) ---")
    for module_key, data in serial_data_storage.items():
        module_id, lat, lon = data
        output_payload = f"({module_id},{lat},{lon},{detection_status})"
        client.publish(MQTT_TOPIC, output_payload)
        print(f"[MQTT] Publicado para {module_id}: {output_payload}")
    last_mqtt_send_time = time.time()

# MODIFICADO: A função agora recebe o objeto 'ser' para poder enviar respostas
def process_serial_data(ser_object, serial_line, storage_dict):
    """
    Processa uma linha de dados da serial.
    - Se for um comando (ex: PING), responde apropriadamente.
    - Se forem dados de módulo, valida e atualiza o dicionário de armazenamento.
    - Se os dados não corresponderem a nenhum formato, eles são impressos.
    Retorna o ID do módulo se foi processado, "COMMAND_HANDLED" se foi um comando, senão None.
    """
    if not serial_line:
        return None

    # Lógica para lidar com comandos como PING
    if "PING" in serial_line:
        print(f"\n[SERIAL] Comando 'PING' recebido. Respondendo com 'ACK_PI'.")
        ser_object.write(b"ACK_PI\n")
        return "COMMAND_HANDLED"

    # Lógica para processar dados de localização
    try:
        cleaned_line = serial_line.replace('(', '').replace(')', '').replace('"', '').strip()
        parts = cleaned_line.split(',')
        
        if len(parts) == 3:
            module_id = parts[0].strip()
            if module_id in REQUIRED_MODULES:
                lat, lon = parts[1].strip(), parts[2].strip()
                storage_dict[module_id] = (module_id, lat, lon)
                return module_id # Retorna o ID para confirmar o processamento
    except Exception as e:
        print(f"\nErro ao processar linha de dados serial '{serial_line}': {e}")
    
    # NOVO: Se o código chegou até aqui, os dados não foram processados com sucesso.
    # Imprime os dados brutos recebidos para depuração.
    print(f"\n[SERIAL RAW] Dado não reconhecido recebido: '{serial_line}'")
    
    return None

# ===================================================================
# --- INICIALIZAÇÃO ---
# ===================================================================

print("--- Iniciando Módulos de Comunicação e IA ---")

# Inicializa cliente MQTT
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
client.on_connect = on_connect
try:
    print("Tentando conectar ao Broker MQTT...")
    client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
except Exception as e:
    print(f"AVISO: Não foi possível iniciar a conexão com o Broker MQTT. {e}")
    client = None

# Carrega modelos TFLite
try:
    print("Carregando modelos de IA...")
    interpreter_1 = Interpreter(model_path=MODEL_PATH_1)
    interpreter_1.allocate_tensors()
    input_details_1 = interpreter_1.get_input_details()
    output_details_1 = interpreter_1.get_output_details()
    
    interpreter_2 = Interpreter(model_path=MODEL_PATH_2)
    interpreter_2.allocate_tensors()
    input_details_2 = interpreter_2.get_input_details()
    output_details_2 = interpreter_2.get_output_details()
    
    INPUT_SIZE = (input_details_1[0]['shape'][2], input_details_1[0]['shape'][1])
    print(f"Modelos carregados. Tamanho de entrada: {INPUT_SIZE}")
except Exception as e:
    print(f"ERRO FATAL: Falha ao carregar modelos: {e}"); sys.exit()

# ===================================================================
# --- LOOP DE ESPERA PELOS MÓDulos SERIAIS ---
# ===================================================================

print(f"\n--- Aguardando dados dos módulos seriais requeridos: {', '.join(REQUIRED_MODULES)} ---")
ser = None
received_modules = set()
serial_data_storage = {}

while len(received_modules) < len(REQUIRED_MODULES):
    if not ser or not ser.is_open:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            print(f"Conectado à porta serial {SERIAL_PORT}. Aguardando: {', '.join(set(REQUIRED_MODULES) - received_modules)}")
        except serial.SerialException:
            print(f"AVISO: Porta serial '{SERIAL_PORT}' não encontrada. Tentando novamente em 5s...", end='\r')
            time.sleep(5)
            continue
    
    if ser.in_waiting > 0:
        serial_line = ser.readline().decode('utf-8', errors='ignore').strip()
        
        # MODIFICADO: Passa o objeto 'ser' para a função de processamento
        processed_result = process_serial_data(ser, serial_line, serial_data_storage)

        # MODIFICADO: Verifica se o resultado é um ID de módulo válido (e não um comando)
        if processed_result and processed_result != "COMMAND_HANDLED":
            if processed_result not in received_modules:
                received_modules.add(processed_result)
                print(f"\nMódulo '{processed_result}' recebido! Faltam {len(REQUIRED_MODULES) - len(received_modules)}.")

# ===================================================================
# --- INICIALIZAÇÃO DA CÂMERA E LOOP PRINCIPAL ---
# ===================================================================

print("\nTodos os módulos seriais recebidos! Iniciando detecção...")
cap = None
if IP_CAMERA_URL:
    print(f"Tentando conectar à câmera IP: {IP_CAMERA_URL}...")
    cap = cv2.VideoCapture(IP_CAMERA_URL)
else:
    print("Utilizando a câmera local (índice 0)...")
    cap = cv2.VideoCapture(0)

if not cap or not cap.isOpened():
    print("ERRO FATAL: Nenhuma fonte de vídeo pôde ser aberta."); sys.exit()

print(f"\nIniciando loop principal. Pressione CTRL+C para sair.")
# ... O restante do seu código permanece igual ...

# Variáveis de estado
pipeline_state = 'MONITORANDO'
m1_streak_count, m2_streak_count = 0, 0
m1_last_detection_time = 0
cooldown_start_time = 0
prev_frame_time = 0
last_mqtt_send_time = time.time()
last_detection_activity_time = time.time()

# Função de contagem de detecções (sem alterações)
def count_detections(output_grid, labels, threshold, model_index=0):
    squeezed_grid = np.squeeze(output_grid)
    grid_h, grid_w, num_classes = squeezed_grid.shape
    total_detection_count = 0
    margin_x_start, margin_x_end = int(grid_w * MARGIN_HORIZONTAL), int(grid_w * (1 - MARGIN_HORIZONTAL))
    margin_y_start, margin_y_end = int(grid_h * MARGIN_VERTICAL), int(grid_h * (1 - MARGIN_VERTICAL))

    for y in range(grid_h):
        for x in range(grid_w):
            if model_index == 0 and not (margin_x_start <= x < margin_x_end and margin_y_start <= y < margin_y_end):
                continue
            scores = squeezed_grid[y][x]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if class_id >= len(labels): continue
            is_background = (class_id == 0) or (labels[class_id].lower() in ['background', 'uncertain'])
            if confidence > threshold and not is_background:
                total_detection_count += 1
    return total_detection_count

try:
    while True:
        new_frame_time = time.time()
        ret, frame = cap.read()
        if not ret: 
            print("\nErro ao ler frame, tentando reconectar...")
            cap.release()
            time.sleep(5)
            cap = cv2.VideoCapture(IP_CAMERA_URL if IP_CAMERA_URL else 0)
            continue
        
        # --- RECEBIMENTO SERIAL CONTÍNUO ---
        # MODIFICADO: A lógica de leitura serial agora também lida com comandos
        if ser and ser.in_waiting > 0:
            serial_line = ser.readline().decode('utf-8', errors='ignore').strip()
            # Usa a mesma função centralizada para atualizar dados ou responder a PINGs
            process_serial_data(ser, serial_line, serial_data_storage)
        
        # --- PREPARAÇÃO DO FRAME PARA INFERÊNCIA ---
        input_image = cv2.resize(frame, INPUT_SIZE)
        input_image = cv2.cvtColor(input_image, cv2.COLOR_BGR2RGB)
        if input_details_1[0]['dtype'] == np.uint8:
            input_data = np.expand_dims(input_image, axis=0)
        else:
            input_data = np.expand_dims(input_image, axis=0).astype(np.float32) / 255.0

        m1_objects_found, m2_objects_found = 0, 0
        inference_time_m1, inference_time_m2 = 0, 0
        
        # --- LÓGICA DA MÁQUINA DE ESTADOS (PIPELINE) ---
        if pipeline_state == 'MONITORANDO':
            start_time_m1 = time.time()
            interpreter_1.set_tensor(input_details_1[0]['index'], input_data)
            interpreter_1.invoke()
            output_data_1 = interpreter_1.get_tensor(output_details_1[0]['index'])
            inference_time_m1 = time.time() - start_time_m1
            m1_objects_found = count_detections(output_data_1, LABELS_1, DETECTION_THRESHOLD_1, 0)
            
            if m1_objects_found > 0:
                last_detection_activity_time = time.time()
                m1_streak_count += m1_objects_found
                m1_last_detection_time = time.time()
            else:
                if time.time() - m1_last_detection_time > TRIGGER_COUNT_RESET_SECONDS: m1_streak_count = 0
            
            if m1_streak_count >= TRIGGER_COUNT_THRESHOLD:
                print(f"\n[PIPELINE ATIVADO] Motivo: Acumulo ({m1_streak_count} objs).")
                pipeline_state = 'CONFIRMANDO'

        elif pipeline_state == 'CONFIRMANDO':
            start_time_m2 = time.time()
            interpreter_2.set_tensor(input_details_2[0]['index'], input_data)
            interpreter_2.invoke()
            output_data_2 = interpreter_2.get_tensor(output_details_2[0]['index'])
            inference_time_m2 = time.time() - start_time_m2
            m2_objects_found = count_detections(output_data_2, LABELS_2, DETECTION_THRESHOLD_2, 1)

            if m2_objects_found > 0:
                last_detection_activity_time = time.time()
                m2_streak_count += m2_objects_found
            
            if m2_streak_count >= TRIGGER_COUNT_THRESHOLD:
                print(f"\n[ALVO CONFIRMADO] Modelo 2 detectou {m2_streak_count} objs.")
                publish_mqtt_status(1)
                pipeline_state = 'RESETANDO'
                cooldown_start_time = time.time()

        elif pipeline_state == 'RESETANDO':
            if (time.time() - cooldown_start_time) >= COOLDOWN_SECONDS:
                print("\n[CICLO COMPLETO] Resetando sistema.")
                publish_mqtt_status(0) # Envia status 0 ao final do cooldown
                pipeline_state = 'MONITORANDO'
                m1_streak_count, m2_streak_count = 0, 0
        
        # --- LÓGICA DE KEEP-ALIVE MQTT ---
        time_since_last_send = time.time() - last_mqtt_send_time
        time_since_last_activity = time.time() - last_detection_activity_time
        if time_since_last_send > MQTT_KEEPALIVE_INTERVAL and time_since_last_activity > MQTT_KEEPALIVE_INTERVAL:
            print(f"\n[MQTT Keep-Alive] Sem atividade. Enviando status (0).")
            publish_mqtt_status(0)

        # --- EXIBIÇÃO DE STATUS NO TERMINAL ---
        fps = 1 / (new_frame_time - prev_frame_time) if (new_frame_time - prev_frame_time) > 0 else 0
        prev_frame_time = new_frame_time

        if pipeline_state == 'MONITORANDO':
            status_line = f"Estado: {pipeline_state} | FPS: {fps:.1f} | Acumulo M1: [{m1_streak_count}/{TRIGGER_COUNT_THRESHOLD}] | Infer: {inference_time_m1*1000:.1f}ms   "
        elif pipeline_state == 'CONFIRMANDO':
            status_line = f"Estado: {pipeline_state} | FPS: {fps:.1f} | Acumulo M2: [{m2_streak_count}/{TRIGGER_COUNT_THRESHOLD}] | Infer: {inference_time_m2*1000:.1f}ms   "
        else: # RESETANDO
            remaining_time = max(0, COOLDOWN_SECONDS - (time.time() - cooldown_start_time))
            status_line = f"Estado: {pipeline_state} | Resetando em {remaining_time:.0f}s...                                     "
        
        print(status_line, end='\r')

except KeyboardInterrupt:
    print("\n\nPrograma interrompido pelo usuário.")

finally:
    print("Iniciando limpeza de recursos...")
    if ser and ser.is_open:
        ser.close()
        print("Porta serial fechada.")
    if client:
        client.loop_stop()
        client.disconnect()
        print("Desconectado do Broker MQTT.")
    if cap:
        cap.release()
        print("Recurso de câmera liberado.")
    print("Limpeza concluída. Saindo.")

