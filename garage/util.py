"""Utilitaires de rendu HTML et de formatage (francais)."""
import csv
import io
import os
from datetime import datetime

from . import __version__, taxes
from .web import esc

CATEGORIES_COUTS = ["Transport", "Reconditionnement", "Réparations", "Pièces", "Détail", "Autres"]
CATEGORIES_DEPENSES = ["Loyer", "Assurance", "Électricité / eau", "Internet / téléphone", "Publicité", "Salaires", "Licence concessionnaire", "Banque", "Fournitures", "Divers"]
MODES_PAIEMENT = ["Comptant", "Chèque", "Carte bancaire", "Virement", "Financement"]
CARBURANTS = ["Essence", "Diesel", "Hybride", "Électrique", "GPL"]
ROLES = ["membre", "admin"]
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "$"}


def money(conn, x):
    if x is None:
        return "—"
    sym = SYMBOLS.get(taxes.get_param(conn, "devise", "USD").upper(), "$")
    return f"{sym}{x:,.2f}"


def fmt_date(iso):
    if not iso:
        return "—"
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%m/%d/%Y")
    except ValueError:
        return str(iso)


def parse_date(s):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_float(s):
    try:
        return float(str(s).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_int(s, lo=None, hi=None):
    try:
        v = int(str(s).strip())
    except (TypeError, ValueError):
        return None
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        return None
    return v


def get_id(params, name="id"):
    return parse_int(params.get(name, ""), 1, 10 ** 9)


def csrf_input(req):
    if req.session:
        return f'<input type="hidden" name="csrf" value="{esc(req.session["csrf"])}">'
    return ""


def cookie_session(token):
    return f"session={token}; Path=/; HttpOnly; SameSite=Lax"


def field(label, name, value="", type="text", required=False, step=None, options=None, note=None):
    req_attr = " required" if required else ""
    if options is not None:
        opts = "".join(
            f'<option value="{esc(o)}"{" selected" if str(value) == str(o) else ""}>{esc(o)}</option>'
            for o in options
        )
        ctrl = f'<select name="{name}"{req_attr}>{opts}</select>'
    elif type == "textarea":
        ctrl = f'<textarea name="{name}" rows="3">{esc(value)}</textarea>'
    else:
        val = f' value="{esc(value)}"' if value not in ("", None) else ""
        st = f' step="{step}"' if step else ""
        ctrl = f'<input type="{type}" name="{name}"{val}{req_attr}{st}>'
    note_html = f'<small>{esc(note)}</small>' if note else ""
    return f'<label class="field"><span>{esc(label)}</span>{ctrl}{note_html}</label>'


def veh_label(v):
    label = f"{v['annee'] or ''} {v['marque']} {v['modele']}".strip()
    if v["vin"]:
        label += f" · VIN {v['vin']}"
    return label


def layout(ctx, req, conn, title, body, active=""):
    nom = taxes.get_param(conn, "nom_concession", "Concession")
    nav_html = ""
    user_html = ""
    if req.user:
        nav = [
            ("/", "Tableau de bord", "dashboard"),
            ("/vehicules", "Véhicules", "vehicules"),
            ("/depenses", "Dépenses", "depenses"),
            ("/rapports", "Rapports", "rapports"),
            ("/export", "Export & sauvegarde", "export"),
        ]
        if req.user["role"] == "admin":
            nav += [
                ("/parametres", "Paramètres", "parametres"),
                ("/utilisateurs", "Comptes famille", "utilisateurs"),
                ("/audit", "Journal", "audit"),
            ]
        nav_html = "<nav>" + "".join(
            f'<a href="{href}" class="{"active" if key == active else ""}">{esc(label)}</a>'
            for href, label, key in nav
        ) + "</nav>"
        user_html = (
            f'<div class="user">Connecté : <strong>{esc(req.user["nom_utilisateur"])}</strong> '
            f'({esc(req.user["role"])}) '
            f'<form method="post" action="/logout" class="inline">{csrf_input(req)}'
            f'<button type="submit" class="btn small">Déconnexion</button></form></div>'
        )
    msg = req.q("msg")
    flash = ""
    if msg:
        ok = req.q("ok", "1") == "1"
        flash = f'<div class="flash {"ok" if ok else "ko"}">{esc(msg)}</div>'
    csrf_meta = ""
    if req.session:
        csrf_meta = f'<meta name="csrf" content="{esc(req.session["csrf"])}">'
    has_logo = os.path.exists(os.path.join(ctx.static_dir, "logo.png"))
    favicon = '<link rel="icon" type="image/png" href="/static/logo.png">' if has_logo else ""
    logo_html = '<img src="/static/logo.png" alt="logo" class="logo">' if has_logo else ""
    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{csrf_meta}
{favicon}
<title>{esc(title)} · {esc(nom)}</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header>
  <div class="brand">{logo_html}<h1>{esc(nom)}</h1></div>
  {user_html}
</header>
{nav_html}
<main>
{flash}
{body}
</main>
<footer>Compta Concession v{__version__} · Données locales : <code>data/garage.db</code> (copiez ce fichier pour transférer les données) · Estimations fiscales à valider avec un comptable (Géorgie, USA)</footer>
<script src="/static/app.js"></script>
</body>
</html>'''


def row_dict(row):
    return {k: row[k] for k in row.keys()}


def csv_number(x):
    if x is None:
        return ""
    return f"{x:.2f}".replace(".", ",")


def csv_response(nom_fichier, entetes, lignes):
    from .web import Response
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(entetes)
    w.writerows(lignes)
    return Response("﻿" + buf.getvalue(), 200, "text/csv; charset=utf-8", {"Content-Disposition": f'attachment; filename="{nom_fichier}"'})
