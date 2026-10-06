from flask import Flask, jsonify, request, send_file, render_template
from io import StringIO
import json
import os
from spreadsheet_core import SheetModel

app = Flask(__name__)

# One-sheet app for a simple Python-based spreadsheet application.
app.sheet = SheetModel()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/sheet', methods=['GET', 'POST'])
def sheet_api():
    if request.method == 'GET':
        return jsonify(app.sheet.to_dict())

    payload = request.get_json(silent=True) or {}
    if 'cells' in payload:
        app.sheet.load_from_dict(payload)
    return jsonify(app.sheet.to_dict())


@app.route('/api/cell', methods=['POST'])
def update_cell():
    payload = request.get_json(silent=True) or {}
    row = int(payload.get('row', 0))
    col = int(payload.get('col', 0))
    value = payload.get('value', '')
    app.sheet.set_cell(row, col, value)
    return jsonify({"ok": True, "cell": app.sheet.get_cell(row, col)})


@app.route('/api/export/csv')
def export_csv():
    stream = StringIO()
    app.sheet.export_csv(stream)
    stream.seek(0)
    return send_file(
        io := __import__('io').BytesIO(stream.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='sheet.csv'
    )


@app.route('/api/export/xlsx')
def export_xlsx():
    import pandas as pd
    from io import BytesIO

    data = app.sheet.to_matrix()
    df = pd.DataFrame(data)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, header=False)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='sheet.xlsx')


@app.route('/api/import/csv', methods=['POST'])
def import_csv():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file uploaded"}), 400
    text = file.read().decode('utf-8')
    app.sheet.load_csv(text)
    return jsonify(app.sheet.to_dict())


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
