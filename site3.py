from flask import Flask, render_template, jsonify
from sqlalchemy import desc
from API import criar_sessao, Alertas, Modulos
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def homepage():
    """Página inicial com alertas críticos recentes."""
    session = criar_sessao()
    alertas_recentes = (session.query(Alertas)
                        .filter_by(nivel='Crítico')
                        .order_by(desc(Alertas.data_hora))
                        .limit(5)
                        .all())
    session.close()

    alertas_para_html = []
    for alerta in alertas_recentes:
        alertas_para_html.append({
            'nome_modulo': alerta.nome_modulo,
            'descricao': alerta.descricao,
            'latitude': alerta.latitude,
            'longitude': alerta.longitude,
            'data_hora': alerta.data_hora
        })

    return render_template("homepage3.html", alertas=alertas_para_html)

@app.route('/leituras')
def dashboard_leituras():
    """Dashboard de leituras. O HTML buscará os dados via JSON."""
    return render_template("leituras.html")

@app.route('/modulos.json')
def modulos_json():
    """Retorna todos os módulos com status, coordenadas e última atualização."""
    session = criar_sessao()
    todos_modulos = session.query(Modulos).all()

    # Se não houver módulos no banco, cria módulos de teste
    if not todos_modulos:
        todos_modulos = [
            type('M', (), {'nome': 'A', 'latitude': -23.55, 'longitude': -46.63})(),
            type('M', (), {'nome': 'B', 'latitude': -23.551, 'longitude': -46.634})()
        ]

    modulos_lista = []
    for m in todos_modulos:
        alerta = (session.query(Alertas)
                  .filter_by(nome_modulo=m.nome_modulo)
                  .order_by(desc(Alertas.data_hora))
                  .first())
        status = 'Não Detectado' if not alerta or alerta.nivel == 'Informativo' else 'Detectado'
        ultima_atualizacao = alerta.data_hora.strftime('%d/%m/%Y %H:%M:%S') if alerta else 'N/A'

        modulos_lista.append({
            'nome_modulo': m.nome_modulo,
            'latitude': m.latitude,
            'longitude': m.longitude,
            'status': status,
            'ultima_atualizacao': ultima_atualizacao
        })

    session.close()
    return jsonify(modulos_lista)

if __name__ == '__main__':
    app.run(debug=True)
