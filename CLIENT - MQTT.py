from paho.mqtt import client as mqtt_client
import psycopg2
import time
import json

broker = '192.168.0.8'
port = 1883
topic_monitoramento = "topic/modulos"  

last_message = time.time() 
TIMEOUT_LIMIT = 85

def connect_mqtt() -> mqtt_client:
    
    def on_connect(client, userdata, flags, rc, props):
        if rc == 0:
            print('\nConectado ao Broker !\n')
        elif rc == 5:
            print("\nFalha na autenticação: Credenciais inválidas.\n")
        else:
            print(f"\nFalha ao tentar se conectar, Código de retorno: {rc}\n")

    client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
    client.username_pw_set("Admin_user", "projete2025")
    client.on_connect = on_connect  # CallBack - ou seja quando determinada situação ocorrer , execute a outra ação.

    try:
        # Linha que realmente efetua a conexão com o broker.
        client.connect(broker, port, 50)
    except Exception as e:
        print(f"\nFalhou ao tentar se conectar no Broker ! Erro: {e}")
        print("Verifique sua conexão com a internet e a URL do broker.\n")
        exit()

    return client

def subscribe_to_monitoring(client: mqtt_client):
   
    def on_message(client, userdata, msg):
        
        global last_message
        
        conn = None
        cursor = None
    
        try:
        # Decodifica a mensagem JSON do MQTT
            data = json.loads(msg.payload.decode())

        # Estabelece a conexão com o banco de dados
            conn = connect_to_db()

            if conn is not None:
              
                id_modulo = data.get("id_caixa", "N/D")
                mq7 = data.get("mq7", "N/D")
                mq2 = data.get("mq2", "N/D")
                latitude = data.get("latitude", "N/D")
                id_modulo = data.get("id_caixa", "N/D")
                longitude = data.get("longitude", "N/D")
                data_hora = data.get("data_hora", "N/D")
            
                # Imprime os dados para confirmação
                print("\n===========================")
                print(" Dados de Monitoramento Recebidos ")
                print(f" Identificação do módulo: {id_modulo}")
                print(f" Coleta MQ7: {mq7}")
                print(f" Coleta MQ2: {mq2}")
                print(f" Latitude: {latitude}")
                print(f" Longitude: {longitude}")
                print(f" Data: {data_hora}")
                print("===========================")
                
                cursor = conn.cursor()
                sql_insert_query = """INSERT INTO coletas (id_modulo, mq7, mq2, latitude, longitude, data_hora) 
                                    VALUES (%s, %s, %s, %s, %s, %s);"""
                cursor.execute(sql_insert_query, (id_modulo, mq7, mq2, latitude, longitude, data_hora))
                conn.commit()
                print("\n")
                print("Dados inseridos no banco de dados com sucesso!")

        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar a mensagem JSON: {e}. Mensagem não está no formato correto.")
        except (psycopg2.Error, Exception) as e:
            print(f"Ocorreu um erro no processamento de dados ou no banco de dados: {e}")
        
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()
                
        last_message = time.time()
    
    client.subscribe(topic_monitoramento)
    client.on_message = on_message
    print(f">>> Inscrito no tópico '{topic_monitoramento}'. Aguardando mensagens...\n")

def connect_to_db():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="FireWatcher",
            user="postgres",
            password="777444",
            host="localhost",
            port="5432",
            client_encoding='utf8'
        )
        print("\nConexão com o banco de dados bem-sucedida!\n")
        return conn
    except (Exception, psycopg2.Error) as error:
        print("Erro ao conectar no PostgreSQL:", error)
        return None

def run():
    client = connect_mqtt()
    client.loop_start()

    time.sleep(2)  # Pausa para garantir a conexão

    subscribe_to_monitoring(client)

    keep_running = True

    try:
        while keep_running:
            # Verifica o timeout e desliga a flag se for o caso
            if (time.time() - last_message) > TIMEOUT_LIMIT:
                print("\nTimeout! Não foram recebidos dados do 'topic/modulos'. Encerrando o programa.")
                keep_running = False

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nDesconectando do broker...")
        keep_running = False

    finally:
        client.loop_stop()
        client.disconnect()
        print("\nDesconectado.\n")


if __name__ == '__main__':
    run()