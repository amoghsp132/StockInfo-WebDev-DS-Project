from flask import Flask, render_template, Response, request,send_file,jsonify
import pandas as pd
import warnings
import numpy as np
import yfinance as yf
import sweetviz as sv
import os
import time
import matplotlib
matplotlib.use('Agg')
from flask_caching import Cache
import io
from xhtml2pdf import pisa




app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 3600})


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    stockcode = request.form.get('stockcode')
    return render_template('analytics.html', symbol="NASDAQ:" + stockcode.upper(), stockcode=stockcode.upper())

@app.route('/report')
@cache.cached(query_string=True)
def report():
    # Get ticker from query parameter
    ticker = request.args.get('ticker')
    
    if not ticker:
        return "Stockcode  not provided", 400

    # Patch numpy if needed
    if not hasattr(np, 'VisibleDeprecationWarning'):
        np.VisibleDeprecationWarning = type('VisibleDeprecationWarning', (Warning,), {})

    # Download data
    df = yf.download(ticker, period="3y", interval="1d")

    if df.empty:
        return f"No data found for {ticker}.", 404

    # Flatten DataFrame
    df.reset_index(inplace=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [' '.join(col).strip() if isinstance(col, tuple) else col for col in df.columns]

    warnings.simplefilter('default')

    # Create report
    report = sv.analyze(df)

    # Temporary file path
    output_file = f"{ticker}_sweetviz_report.html"
    report.show_html(output_file, open_browser=False )

    # Read file content
    with open(output_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Delete the temporary file
    if os.path.exists(output_file):
        time.sleep(10)
        os.remove(output_file)

    # Return as HTML response
    return Response(html_content, mimetype='text/html')


@app.route('/download_csv')
def download_csv():
    ticker = request.args.get('ticker')
    if not ticker:
        return "Stockcode  not provided", 400

    df = yf.download(ticker, period="3y", interval="1d")
    if df.empty:
        return f"No data found for {ticker}.", 404

    # Convert to CSV in memory
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer)
    csv_buffer.seek(0)

    return Response(
        csv_buffer.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment; filename={ticker}_market_data.csv"}
    )


def gen_summary_html(df, ticker):
    stats = df.describe().T.reset_index()
    html = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background: #f7fbfc;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 900px;
                margin: 48px auto 24px auto;
                background: #fff;
                border-radius: 18px;
                box-shadow: 0 8px 32px rgba(44,62,80,0.10);
                padding: 32px 36px 40px 36px;
            }}
            h1 {{
                color: #2c3e50;
                font-size: 2.2rem;
                font-weight: 700;
                margin-bottom: 8px;
                letter-spacing: 1px;
            }}
            .subheader {{
                color: #207788;
                font-size: 1.08rem;
                margin-bottom: 18px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin-top: 12px;
                margin-bottom: 22px;
                box-shadow: 0 2px 10px rgba(44,62,80,0.05);
            }}
            th, td {{
                border: 1.2px solid #dbe6ec;
                padding: 12px 20px;
                text-align: right;
                font-size: 1.02rem;
                min-width: 85px;
            }}
            th {{
                background: #f5fafc;
                color: #14314f;
                font-weight: 600;
            }}
            tr:nth-child(even) td {{
                background: #f3f7fa;
            }}
            td:first-child, th:first-child {{
                text-align: left;
                font-weight: 500;
                color: #307493;
                padding-left: 20px;
            }}
            .footer {{
                text-align: right;
                color: #999;
                margin-top: 30px;
                font-size: 0.92rem;
            }}
        </style>
    </head>
    <body>
        <div class='container'>
            <h1>Market Data Summary: {ticker.upper()}</h1>
            <div class="subheader">Automatically generated statistical summary (last 3 years)</div>
            <table>
                <tr>
                    {''.join(f'<th>{col}</th>' for col in stats.columns)}
                </tr>
                {''.join(
                    '<tr>' + ''.join(
                        f'<td>{row[col]:,.2f}</td>' if col != 'index' else f'<td>{row[col]}</td>'
                        for col in stats.columns
                    ) + '</tr>'
                    for _, row in stats.iterrows()
                )}
            </table>
            <div class="footer">Generated with pandas &amp; xhtml2pdf · © {pd.Timestamp.now().year}</div>
        </div>
    </body>
    </html>
    """
    return html



@app.route('/download_pdf')
def download_pdf():
    ticker = request.args.get('ticker')
    if not ticker:
        return "Stockcode not provided", 400

    df = yf.download(ticker, period="3y", interval="1d")
    if df.empty:
        return f"No data found for {ticker}.", 404

    df.reset_index(inplace=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [' '.join([str(i) for i in col]).strip() for col in df.columns]

    html_content = gen_summary_html(df, ticker)

    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer)

    if pisa_status.err:
        return "PDF creation failed", 500

    pdf_buffer.seek(0)
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        download_name=f"{ticker}_market_data.pdf",
        as_attachment=True
    )

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/raw')
def raw():
    ticker = request.args.get('ticker')
    if not ticker:
        return jsonify({"error": "Stockcode  not provided"}), 400

    try:
        stock = yf.Ticker(ticker)
        info = stock.info  # Fetch stock information as a dictionary
        
        # Optionally, limit the info to avoid too much data
        # For example: select only specific keys
        # filtered_info = {k: info[k] for k in ['symbol', 'shortName', 'previousClose', 'open'] if k in info}

        return jsonify(info)  # Return as JSON
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/api')
def api():
    return render_template('api.html')

@app.route('/donate')
def donate():
    return render_template('donate.html')

if __name__ == '__main__':
    app.run(debug=True)
