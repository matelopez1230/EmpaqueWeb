from flask import Flask, render_template, session, redirect, url_for
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Registrar blueprints
from routes.auth import auth_bp
from routes.pedidos import pedidos_bp
from routes.pickeo import pickeo_bp
from routes.empaques import empaques_bp
from routes.reportes import reportes_bp
from routes.deshacer import deshacer_bp
from routes.pallets import pallets_bp
from routes.control_pallet import control_pallet_bp
from routes.quitar_producto import quitar_producto_bp
from routes.trazabilidad import trazabilidad_bp
from routes.usuarios import usuarios_bp
from routes.pedidos_remitidos import pedidos_remitidos_bp
from routes.desempacar import desempacar_bp
from routes.visor_pdf import visor_pdf_bp
from routes.reportes_vencimientos import reportes_vencimientos_bp


app.register_blueprint(auth_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(pickeo_bp)
app.register_blueprint(empaques_bp)
app.register_blueprint(reportes_bp)
app.register_blueprint(deshacer_bp)
app.register_blueprint(pallets_bp)
app.register_blueprint(control_pallet_bp)
app.register_blueprint(quitar_producto_bp)
app.register_blueprint(trazabilidad_bp)
app.register_blueprint(usuarios_bp)
app.register_blueprint(pedidos_remitidos_bp)
app.register_blueprint(desempacar_bp)
app.register_blueprint(visor_pdf_bp)
app.register_blueprint(reportes_vencimientos_bp)


@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template('index.html')

@app.template_filter('format_date')
def format_date(value):
    if value:
        # Si es string en formato YYYY-MM-DD
        if isinstance(value, str) and len(value) >= 10:
            try:
                return value[8:10] + '/' + value[5:7] + '/' + value[:4]
            except:
                return value
        # Si es objeto date/datetime
        if hasattr(value, 'strftime'):
            return value.strftime('%d/%m/%Y')
    return ''

@app.template_filter('formato_cantidad')
def formato_cantidad(value):
    if value is None:
        return '0'
    try:
        # Si es un número entero (ej: 1.0, 2.0)
        if float(value).is_integer():
            return str(int(float(value)))
        # Si tiene decimales, mostrar con 2 decimales máximo
        else:
            # Eliminar ceros innecesarios al final
            return str(round(float(value), 2)).rstrip('0').rstrip('.') if '.' in str(round(float(value), 2)) else str(round(float(value), 2))
    except:
        return str(value)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
    #app.run(debug=True)
