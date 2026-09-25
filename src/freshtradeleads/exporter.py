from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import xlsxwriter

DISCLAIMER = "FreshTradeLeads is not affiliated with the California Contractors State License Board (CSLB). Licensing status can change; verify current status directly with CSLB before acting."


def _plain(value):
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, Decimal): return str(value)
    return "" if value is None else value


def export_csv(rows, columns, path: Path, metadata: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        f.write(f"# Generated: {metadata['generated_at']}\n# Source data as of: {metadata['source_as_of']}\n# {DISCLAIMER}\n")
        writer=csv.DictWriter(f,fieldnames=columns); writer.writeheader()
        for row in rows: writer.writerow({k:_plain(row[k]) for k in columns})


def export_xlsx(rows, columns, path: Path, metadata: dict, *, info_sheet_name: str = "Report Information", notice: str = DISCLAIMER):
    path.parent.mkdir(parents=True, exist_ok=True)
    wb=xlsxwriter.Workbook(path)
    ws=wb.add_worksheet("Leads"); info=wb.add_worksheet(info_sheet_name)
    header=wb.add_format({"bold":True,"font_color":"white","bg_color":"#176B5B","border":1,"text_wrap":True})
    date_fmt=wb.add_format({"num_format":"yyyy-mm-dd"}); money=wb.add_format({"num_format":"$#,##0"}); wrap=wb.add_format({"text_wrap":True,"valign":"top"})
    for c,name in enumerate(columns): ws.write(0,c,name,header)
    for r,row in enumerate(rows,1):
        for c,name in enumerate(columns):
            v=row[name]
            if isinstance(v,datetime): ws.write_datetime(r,c,v,date_fmt)
            elif isinstance(v,date): ws.write_datetime(r,c,datetime.combine(v,datetime.min.time()),date_fmt)
            elif isinstance(v,Decimal): ws.write_number(r,c,float(v),money if "Amount" in name else None)
            elif v is None: ws.write_blank(r,c,None)
            else: ws.write(r,c,v,wrap if name in {"Business Name","Address","Trade / Classification Description"} else None)
    ws.freeze_panes(1,0); ws.autofilter(0,0,max(len(rows),1),len(columns)-1)
    widths={"Business Name":32,"License Number":15,"Classification Code(s)":22,"Trade / Classification Description":42,"Original Issue Date":17,"Current License Status":20,"Business Type":18,"Phone":18,"Address":34,"City":20,"County":18,"State":8,"ZIP":12,"Workers Compensation Coverage Type":34,"Workers Compensation Carrier":36,"Contractor Bond Surety":38,"Contractor Bond Amount":22}
    for c,name in enumerate(columns): ws.set_column(c,c,widths.get(name,18))
    info.set_column(0,0,24); info.set_column(1,1,110); info.write_row(0,0,["FreshTradeLeads Report","Value"],header)
    info.write(1,0,"Generated (UTC)"); info.write(1,1,metadata["generated_at"]); info.write(2,0,"Source data as of"); info.write(2,1,metadata["source_as_of"]); info.write(3,0,"Source SHA-256"); info.write(3,1,metadata["source_sha256"]); info.write(4,0,"Records"); info.write_number(4,1,len(rows)); info.write(6,0,"Important notice"); info.write(6,1,notice,wrap)
    wb.close()
