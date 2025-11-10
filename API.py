import paho.mqtt.client as mqtt
import time
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.orm import declarative_base, sessionmaker

# --- Configurações do Banco de Dados ---
# Substitua 'sua_senha' pela senha do seu PostgreSQL.
DATABASE_URL = 'postgresql://postgres:26122007@localhost:5432/firebanco'

Base = declarative_base()


mapeamento_modulos = {
    'A': 'Modulo A',
    'B': 'Modulo B'
    # Adicione mais módulos aqui, se necessário
}


class Modulos(Base):
    """Representa a tabela de módulos para armazenar dados estáticos de cada caixa."""
    __tablename__ = 'modulos'

    id = Column(Integer, primary_key=True)
    nome_modulo = Column(String, unique=True, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)



class Alertas(Base):
    """Representa a tabela de alertas, que registra o resultado da análise da IA."""
    __tablename__ = 'alertas'

    id = Column(Integer, primary_key=True)
    nome_modulo = Column(String, nullable=False)
    nivel = Column(String, nullable=False)  # 'Crítico' ou 'Informativo'
    descricao = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    data_hora = Column(DateTime, default=datetime.now)


def criar_sessao():
    """Cria e retorna uma sessão com o banco de dados."""
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


# --- Configurações do MQTT ---
BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPICO_DADOS = "pro/test"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Conectado ao broker MQTT com sucesso!")
        client.subscribe(TOPICO_DADOS)
    else:
        print(f"Falha na conexão, código: {rc}")


def on_message(client, userdata, msg):
    print(f"Mensagem recebida no tópico '{msg.topic}'")

    try:
        dados_str = msg.payload.decode('utf-8')
        partes = dados_str.split(',')

        letra_modulo = partes[0]
        # Converte a letra do módulo para o nome completo usando o dicionário
        nome_modulo_completo = mapeamento_modulos.get(letra_modulo, f"Módulo {letra_modulo}")
        latitude = float(partes[1])
        longitude = float(partes[2])
        incendio_detectado = int(partes[3])  # '0' ou '1'

        session = criar_sessao()

        # Salva o resultado da IA no banco de dados
        novo_alerta = Alertas(
            nome_modulo=nome_modulo_completo,
            nivel="Crítico" if incendio_detectado == 1 else "Informativo",
            descricao="Incêndio detectado pela IA" if incendio_detectado == 1 else "Alarme falso detectado pela IA",
            latitude=latitude,
            longitude=longitude,
            data_hora=datetime.now()
        )
        session.add(novo_alerta)
        session.commit()

        modulo_existente = session.query(Modulos).filter_by(nome_modulo=nome_modulo_completo).first()

        if modulo_existente:
            # Atualiza posição
            modulo_existente.latitude = latitude
            modulo_existente.longitude = longitude
        else:
            # Cria novo registro
            novo_modulo = Modulos(
                nome_modulo=nome_modulo_completo,
                latitude=latitude,
                longitude=longitude
            )
            session.add(novo_modulo)

        session.commit()
        session.close()

        print(f"Alerta IA salvo: Modulo: {nome_modulo_completo}, Incêndio: {'Sim' if incendio_detectado == 1 else 'Não'}")

    except Exception as e:
        print(f"Ocorreu um erro ao processar a mensagem: {e}")


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER_HOST, BROKER_PORT, 60)
        print("Aguardando alertas da IA...")
        client.loop_forever()
    except Exception as e:
        print(f"Não foi possível conectar ao broker MQTT: {e}")


if __name__ == '__main__':
    main()
