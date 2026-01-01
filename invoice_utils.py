# invoice_utils.py
from datetime import datetime
import os
import json

def invoice_to_html(invoice, user, out_dir='invoices'):
    os.makedirs(out_dir, exist_ok=True)
    filename = f"invoice_{invoice.id}.html"
    path = os.path.join(out_dir, filename)
    details = {}
    try:
        details = json.loads(invoice.details) if invoice.details else {}
    except Exception:
        details = {"raw": invoice.details}
    html = f"""
    <html>
    <head>
      <meta charset="utf-8">
      <title>Invoice #{invoice.id}</title>
      <style>
        body{{ font-family: Arial, sans-serif; padding: 20px; }}
        .card{{ border:1px solid #eee; padding:20px; border-radius:8px; max-width:800px; margin:auto }}
        .header{{ display:flex; justify-content:space-between; align-items:center }}
        table{{ width:100%; border-collapse: collapse; margin-top: 20px }}
        th, td{{ text-align:left; padding:8px; border-bottom:1px solid #ddd }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <div>
            <h2>WiFinity</h2>
            <div>Invoice #: {invoice.id}</div>
            <div>Date: {invoice.created_at.strftime('%Y-%m-%d')}</div>
          </div>
          <div>
            <strong>Bill To:</strong><br/>
            {user.name or user.phone}<br/>
            {user.email or ""}<br/>
            {user.phone}
          </div>
        </div>

        <table>
          <thead><tr><th>Description</th><th>Amount (KES)</th></tr></thead>
          <tbody>
            <tr>
              <td>Subscription charge ({invoice.period_start.date()} → {invoice.period_end.date()})</td>
              <td style="text-align:right">{invoice.amount:.2f}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr><th style="text-align:right">Total</th><th style="text-align:right">{invoice.amount:.2f}</th></tr>
          </tfoot>
        </table>

        <p>Details: <pre>{json.dumps(details, indent=2)}</pre></p>
        <p>Payment Status: {'Paid' if invoice.paid else 'Unpaid'}</p>
      </div>
    </body>
    </html>
    """
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path

def export_invoices_csv(invoices, out_path='invoices_export.csv'):
    import csv
    rows = []
    for inv in invoices:
        rows.append({
            'invoice_id': inv.id,
            'user_id': inv.user_id,
            'subscription_id': inv.subscription_id,
            'period_start': inv.period_start.isoformat(),
            'period_end': inv.period_end.isoformat(),
            'amount': inv.amount,
            'paid': inv.paid
        })
    keys = rows[0].keys() if rows else []
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    return out_path
