"""Import page: upload an Excel/CSV file → check the column matching and preview → confirm."""
import os
import secrets
import tempfile
from pathlib import Path

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from . import importer
from .stock import log_activity

MAX_BYTES = 10 * 1024 * 1024
TMP = Path(tempfile.gettempdir())


def _path(state):
    return TMP / f"ms-import-{state['token']}{state['ext']}"


def _cleanup(request):
    state = request.session.pop('import', None)
    if state:
        try:
            os.remove(_path(state))
        except OSError:
            pass


def import_data(request):
    state = request.session.get('import')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'cancel':
            _cleanup(request)
            return redirect('import_data')

        if action == 'upload':
            _cleanup(request)
            upload = request.FILES.get('file')
            kind = request.POST.get('kind')
            ext = os.path.splitext(upload.name)[1].lower() if upload else ''
            if not upload or kind not in importer.FIELDS:
                messages.error(request, _("Choose what you are importing and a file."))
            elif ext not in ('.xlsx', '.csv'):
                messages.error(request, _("Please upload an Excel .xlsx or a .csv file (in Excel: File → Save As → .xlsx)."))
            elif upload.size > MAX_BYTES:
                messages.error(request, _("The file is larger than 10 MB."))
            else:
                state = {'token': secrets.token_hex(8), 'ext': ext, 'kind': kind, 'filename': upload.name[:120]}
                with open(_path(state), 'wb') as fh:
                    for chunk in upload.chunks():
                        fh.write(chunk)
                try:
                    headers, rows = importer.read_table(_path(state))
                except Exception:
                    headers, rows = [], []
                if not headers or not rows:
                    os.remove(_path(state))
                    messages.error(request, _("Could not find any rows in this file. Check that the first sheet has a header row."))
                else:
                    request.session['import'] = state
            return redirect('import_data')

        if not state or not _path(state).exists():
            _cleanup(request)
            messages.error(request, _("The uploaded file has expired — please upload it again."))
            return redirect('import_data')

        headers, rows = importer.read_table(_path(state))
        kind = state['kind']
        mapping = importer.mapping_from_post(request.POST, kind, headers)
        state['mapping'] = mapping
        request.session['import'] = state

        if action == 'commit':
            if not any(f in mapping for f in importer.REQUIRED[kind]):
                messages.error(request, _("Choose which column holds the name (or code) first."))
                return redirect('import_data')
            if kind == 'items':
                plan = importer.plan_items(rows, mapping)
                result = importer.apply_items(plan, request.user if request.user.is_authenticated else None)
            else:
                plan = importer.plan_clients(rows, mapping)
                result = importer.apply_clients(plan)
            counts = importer.summarize(plan)
            log_activity(request, 'data_import',
                         f"{state['filename']}: +{result['created']} / ~{result['updated']}")
            filename = state['filename']
            _cleanup(request)
            return render(request, 'tracker/import_done.html', {
                'kind': kind, 'result': result, 'counts': counts, 'filename': filename,
                'skipped': [p for p in plan if p['action'] == 'skip'][:100],
            })
        return redirect('import_data')

    if not state:
        return render(request, 'tracker/import.html', {'step': 'upload', 'kinds': importer.FIELDS})

    if not _path(state).exists():
        _cleanup(request)
        messages.error(request, _("The uploaded file has expired — please upload it again."))
        return redirect('import_data')

    kind = state['kind']
    headers, rows = importer.read_table(_path(state))
    mapping = state.get('mapping') or importer.guess_mapping(headers, kind)
    plan = importer.plan_items(rows, mapping) if kind == 'items' else importer.plan_clients(rows, mapping)
    counts = importer.summarize(plan)
    fields = [{'key': key, 'label': label, 'col': mapping.get(key)} for key, label, _kw in importer.FIELDS[kind]]
    preview = [p for p in plan if p['action'] in ('create', 'update')][:30]
    labels = {key: label for key, label, _kw in importer.FIELDS[kind]}
    for p in preview:
        p['change_list'] = [(labels.get(f, f), v) for f, v in p.get('changes', {}).items()]
    return render(request, 'tracker/import.html', {
        'step': 'preview', 'kind': kind, 'filename': state['filename'], 'headers': list(enumerate(headers)),
        'fields': fields, 'counts': counts, 'preview': preview, 'total_rows': len(rows),
        'skipped': [p for p in plan if p['action'] == 'skip'][:30],
        'sample': rows[:3], 'has_required': any(f in mapping for f in importer.REQUIRED[kind]),
    })


def import_template(request, kind):
    """A ready-to-fill example .xlsx with the column names the importer understands."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    if kind not in importer.FIELDS:
        kind = 'items'
    examples = {
        'items': {'part_code': 'VIC-AGM100', 'part_name': 'AGM battery 100Ah', 'category': 'Electrical', 'quantity': 4,
                  'unit_cost': 180, 'sale_price': 245, 'location': 'Bin B1', 'reorder_level': 2, 'supplier': 'Victron Energy GR'},
        'clients': {'name': 'Aegean Shipping', 'code': 'C-0042', 'tax_id': '099999999', 'tax_office': 'Α΄ Πειραιά',
                    'phone': '+30 210 000 0000', 'email': 'info@example.com', 'address': 'Akti Miaouli 1', 'city': 'Piraeus'},
    }[kind]
    order = [f for f, _l, _k in importer.FIELDS[kind]]
    order.sort(key=lambda f: 0 if f in ('part_code', 'part_name', 'name', 'code') else 1)
    wb = Workbook()
    ws = wb.active
    ws.append([str(dict((f, l) for f, l, _k in importer.FIELDS[kind])[f]) for f in order])
    ws.append([examples.get(f, '') for f in order])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        ws.column_dimensions[cell.column_letter].width = 22
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="marine-import-{kind}.xlsx"'
    wb.save(response)
    return response
