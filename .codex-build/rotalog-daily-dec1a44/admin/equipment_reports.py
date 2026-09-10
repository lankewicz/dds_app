"""Relatórios de equipamentos do cadastro de equipes."""
import csv
import io
from datetime import datetime, time, timedelta, timezone
from flask import request, render_template, Response, abort, current_app
LABELS = {"tablet": "Tablet", "cameraCopel": "Câmera Copel", "cameraVeicular": "Câmera veicular"}
FIELDS = ("identifier", "serial", "patrimonio", "imei", "phoneNumber", "email")
TZ = timezone(timedelta(hours=-3))

def describe(value):
    value = value or {}
    return " / ".join(str(value.get(f)) for f in FIELDS if value.get(f)) or value.get("summary") or "Sem cadastro"

def csv_content(headers, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    def safe(value):
        text = str(value or "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
    writer.writerow(headers)
    writer.writerows([safe(v) for v in row] for row in rows)
    return "\ufeff" + output.getvalue()

def report():
    from monitor.services.teams_service import list_teams_map, db, COLLECTION_NAME, EQUIPMENT_HISTORY_SUBCOLLECTION
    mode = request.args.get("mode", "current")
    kind = request.args.get("equipment", "")
    active = request.args.get("active", "active")
    selected_team = request.args.get("team", "")
    if mode not in ("current", "missing", "history") or kind not in ("", *LABELS) or active not in ("all", "active", "inactive"):
        abort(400, description="Filtro inválido.")
    today = datetime.now(TZ).date()
    start_date = request.args.get("start_date", today.replace(day=1).isoformat())
    end_date = request.args.get("end_date", today.isoformat())
    try:
        start = datetime.combine(datetime.strptime(start_date, "%Y-%m-%d").date(), time.min, TZ)
        end = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d").date() + timedelta(days=1), time.min, TZ)
        if start >= end:
            raise ValueError()
    except ValueError:
        abort(400, description="Informe um período válido.")
    headers = (["Equipe", "Nome", "Equipamento", "Data (Brasília)", "Anterior", "Novo", "Responsável", "Motivo"] if mode == "history" else
               ["Equipe", "Nome", "Equipamento", "Situação", "Identificação", "Serial", "Patrimônio", "IMEI", "Telefone", "E-mail"])
    rows, teams, error = [], {}, None
    try:
        teams = list_teams_map(active=None)
        history = []
        for key, team in sorted(teams.items()):
            if selected_team and selected_team != key:
                continue
            if active != "all" and bool(team.get("active", True)) != (active == "active"):
                continue
            name = team.get("displayName") or key
            if mode == "history":
                query = db.collection(COLLECTION_NAME).document(key).collection(EQUIPMENT_HISTORY_SUBCOLLECTION)
                for snap in query.where("changedAt", ">=", start).where("changedAt", "<", end).stream():
                    entry = snap.to_dict() or {}
                    equipment_type = entry.get("equipmentType")
                    if equipment_type not in LABELS or (kind and kind != equipment_type):
                        continue
                    changed = entry.get("changedAt")
                    if not isinstance(changed, datetime):
                        continue
                    if changed.tzinfo is None:
                        changed = changed.replace(tzinfo=timezone.utc)
                    history.append((changed, [key, name, LABELS[equipment_type], changed.astimezone(TZ).strftime("%d/%m/%Y %H:%M:%S"), describe(entry.get("before")), describe(entry.get("after")), entry.get("changedByName") or "", entry.get("changeReason") or ""]))
            else:
                for equipment_type, label in LABELS.items():
                    if kind and kind != equipment_type:
                        continue
                    equipment = (team.get("equipment") or {}).get(equipment_type) or {}
                    present = any(str(equipment.get(f) or "").strip() for f in (*FIELDS, "summary"))
                    if mode == "missing" and present:
                        continue
                    rows.append([key, name, label, "Cadastrado" if present else "Sem cadastro", *[equipment.get(f) or "" for f in FIELDS]])
        if mode == "history":
            rows = [row for changed, row in sorted(history, key=lambda item: item[0], reverse=True)]
    except Exception:
        current_app.logger.exception("Falha no relatório de equipamentos")
        error = "Não foi possível carregar o relatório. Tente novamente."
    if request.args.get("export") == "csv" and not error:
        return Response(csv_content(headers, rows), content_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="equipamentos-{mode}.csv"'})
    return render_template("equipment_reports.html", rows=rows, headers=headers, teams=teams, labels=LABELS,
                           mode=mode, kind=kind, active=active, selected_team=selected_team,
                           start_date=start_date, end_date=end_date, error=error), (503 if error else 200)
