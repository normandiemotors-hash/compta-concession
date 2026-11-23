"""Pages principales : auth, tableau de bord, vehicules, depenses, rapports, exports."""
import json
import re
import sqlite3
from datetime import datetime

from . import db, reports, security, taxes
from .util import (
    CATEGORIES_COUTS, CATEGORIES_DEPENSES, MODES_PAIEMENT, CARBURANTS,
    cookie_session, csv_number, csv_response, csrf_input, field, fmt_date,
    get_id, layout, money, parse_date, parse_float, parse_int, row_dict, veh_label,
)
from .web import Response, redirect

TABLES_IMPORT = {
    "vehicules": ["id", "vin", "annee", "marque", "modele", "kilometrage", "carburant", "date_achat", "prix_achat", "vendeur", "statut", "date_vente", "prix_vente", "acheteur", "mode_paiement", "accessoires_ht", "valeur_marche", "notes"],
    "couts": ["id", "vehicule_id", "date", "categorie", "description", "montant"],
    "depenses": ["id", "date", "categorie", "description", "montant"],
    "parametres": ["cle", "valeur", "description"],
}


def page_setup(req, ctx, conn):
    if conn.execute("SELECT COUNT(*) n FROM utilisateurs").fetchone()["n"]:
        return redirect("/login")
    body = f'''<section class="card">
<h2>Premier démarrage — créez le compte administrateur</h2>
<p>Ce compte pourra ensuite créer les comptes des autres membres de la famille.</p>
<form method="post" action="/setup">
{field("Nom d'utilisateur", "nom", required=True)}
{field("Mot de passe (8 caractères min.)", "mdp", type="password", required=True)}
{field("Confirmer le mot de passe", "mdp2", type="password", required=True)}
<button type="submit" class="btn">Créer le compte</button>
</form>
</section>'''
    return Response(layout(ctx, req, conn, "Configuration initiale", body))


def post_setup(req, ctx, conn):
    if conn.execute("SELECT COUNT(*) n FROM utilisateurs").fetchone()["n"]:
        return redirect("/login")
    f = req.form
    nom = f.get("nom", "").strip()
    mdp = f.get("mdp", "")
    if not nom or len(mdp) < 8 or mdp != f.get("mdp2", ""):
        return redirect("/setup", "Nom requis, mots de passe identiques et 8 caractères minimum.", 0)
    conn.execute("INSERT INTO utilisateurs(nom_utilisateur, hash_mdp, role) VALUES (?,?, 'admin')", (nom, security.hash_password(mdp)))
    conn.commit()
    user = conn.execute("SELECT * FROM utilisateurs WHERE nom_utilisateur = ?", (nom,)).fetchone()
    db.audit(conn, user["id"], "creation_admin_initial")
    token, _ = security.create_session(conn, user["id"])
    resp = redirect("/", f"Compte « {nom} » créé. Bienvenue !")
    resp.headers["Set-Cookie"] = cookie_session(token)
    return resp


def page_login(req, ctx, conn):
    if not conn.execute("SELECT COUNT(*) n FROM utilisateurs").fetchone()["n"]:
        return redirect("/setup")
    if req.user:
        return redirect("/")
    body = f'''<section class="card">
<h2>Connexion</h2>
<form method="post" action="/login">
{field("Nom d'utilisateur", "nom", required=True)}
{field("Mot de passe", "mdp", type="password", required=True)}
<button type="submit" class="btn">Se connecter</button>
</form>
</section>'''
    return Response(layout(ctx, req, conn, "Connexion", body))


def post_login(req, ctx, conn):
    f = req.form
    nom = f.get("nom", "").strip()
    user = conn.execute("SELECT * FROM utilisateurs WHERE nom_utilisateur = ?", (nom,)).fetchone()
    if user and security.verify_password(f.get("mdp", ""), user["hash_mdp"]):
        db.audit(conn, user["id"], "connexion")
        token, _ = security.create_session(conn, user["id"])
        resp = redirect("/", f"Bienvenue, {nom} !")
        resp.headers["Set-Cookie"] = cookie_session(token)
        return resp
    db.audit(conn, None, "connexion_echouee", detail=nom[:64])
    body = '<section class="card"><h2>Connexion</h2><div class="flash ko">Identifiants incorrects.</div>' \
           '<form method="post" action="/login">' \
           + field("Nom d'utilisateur", "nom", value=nom, required=True) \
           + field("Mot de passe", "mdp", type="password", required=True) \
           + '<button type="submit" class="btn">Se connecter</button></form></section>'
    return Response(layout(ctx, req, conn, "Connexion", body), 401)


def post_logout(req, ctx, conn):
    security.destroy_session(conn, req.cookies.get("session"))
    resp = redirect("/login", "Vous êtes déconnecté.")
    resp.headers["Set-Cookie"] = "session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
    return resp


def page_dashboard(req, ctx, conn):
    d = reports.dashboard(conn)
    cards = f'''<div class="cards">
<div class="card stat"><span>Véhicules en stock</span><strong>{d["en_stock"]}</strong></div>
<div class="card stat"><span>Valeur du stock (coût total)</span><strong>{money(conn, d["valeur_stock"])}</strong></div>
<div class="card stat"><span>Ventes ce mois</span><strong>{d["ventes_nb"]} · {money(conn, d["ca_mois"])}</strong></div>
<div class="card stat"><span>Marge brute ce mois</span><strong>{money(conn, d["marge_mois"])}</strong></div>
<div class="card stat"><span>Dépenses ce mois</span><strong>{money(conn, d["depenses_mois"])}</strong></div>
<div class="card stat"><span>Marge nette ce mois</span><strong>{money(conn, d["marge_nette_mois"])}</strong></div>
<div class="card stat warn"><span>Sales tax collectée (est.)</span><strong>{money(conn, d["taxe_vente_mois"])}</strong></div>
<div class="card stat warn"><span>TAVT estimé sur les ventes</span><strong>{money(conn, d["tavt_mois"])}</strong></div>
</div>'''
    aging = reports.aging(conn, 60)
    couts = reports.couts_par_vehicule(conn)
    if aging:
        aging_rows = "".join(
            f'<tr><td><a href="/vehicules/{a["v"]["id"]}">{veh_label(a["v"])}</a></td>'
            f'<td>{fmt_date(a["v"]["date_achat"])}</td><td>{a["jours"]}</td>'
            f'<td>{money(conn, reports.total_cout(conn, a["v"], couts))}</td></tr>'
            for a in aging
        )
        aging_html = f'''<section class="card">
<h2>Stock vieillissant (≥ 60 jours)</h2>
<table><thead><tr><th>Véhicule</th><th>Acheté le</th><th>Jours en stock</th><th>Coût total</th></tr></thead><tbody>{aging_rows}</tbody></table>
</section>'''
    else:
        aging_html = '<section class="card"><h2>Stock vieillissant (≥ 60 jours)</h2><p>Aucun véhicule en stock depuis 60 jours ou plus.</p></section>'
    recentes = conn.execute("SELECT * FROM vehicules WHERE statut='vendu' ORDER BY date_vente DESC, id DESC LIMIT 5").fetchall()
    if recentes:
        rec_rows = "".join(
            f'<tr><td><a href="/vehicules/{v["id"]}">{veh_label(v)}</a></td><td>{fmt_date(v["date_vente"])}</td>'
            f'<td>{money(conn, v["prix_vente"])}</td><td>{money(conn, (v["prix_vente"] or 0) + (v["accessoires_ht"] or 0) - reports.total_cout(conn, v, couts))}</td></tr>'
            for v in recentes
        )
        rec_html = f'''<section class="card">
<h2>Dernières ventes</h2>
<table><thead><tr><th>Véhicule</th><th>Vendu le</th><th>Prix de vente</th><th>Marge</th></tr></thead><tbody>{rec_rows}</tbody></table>
</section>'''
    else:
        rec_html = '<section class="card"><h2>Dernières ventes</h2><p>Aucune vente pour l\'instant.</p></section>'
    body = cards + aging_html + rec_html + '<p><a class="btn" href="/vehicules/nouveau">+ Ajouter un véhicule</a></p>'
    return Response(layout(ctx, req, conn, "Tableau de bord", body, "dashboard"))


def page_vehicules(req, ctx, conn):
    statut = req.q("statut", "")
    rows = reports.marge_vehicules(conn, statut or None)
    tabs = f'''<div class="tabs">
<a href="/vehicules" class="{"active" if not statut else ""}">Tous</a>
<a href="/vehicules?statut=en_stock" class="{"active" if statut == "en_stock" else ""}">En stock</a>
<a href="/vehicules?statut=vendu" class="{"active" if statut == "vendu" else ""}">Vendus</a>
</div>'''
    trs = ""
    for r in rows:
        v = r["v"]
        statut_html = '<span class="badge ok">vendu</span>' if v["statut"] == "vendu" else '<span class="badge">en stock</span>'
        vente = money(conn, r["ca"]) if v["statut"] == "vendu" else "—"
        marge = money(conn, r["marge"]) if r["marge"] is not None else "—"
        trs += (
            f'<tr><td><a href="/vehicules/{v["id"]}">{veh_label(v)}</a></td>'
            f'<td>{money(conn, v["prix_achat"])}</td><td>{money(conn, r["cout_total"] - (v["prix_achat"] or 0))}</td>'
            f'<td>{money(conn, r["cout_total"])}</td><td>{statut_html}</td><td>{fmt_date(v["date_vente"])}</td>'
            f'<td>{vente}</td><td>{marge}</td><td>{r["jours"] if r["jours"] is not None else "—"}</td></tr>'
        )
    if rows:
        table = f'''<table><thead><tr>
<th>Véhicule</th><th>Achat</th><th>Coûts</th><th>Coût total</th><th>Statut</th><th>Vente le</th><th>Prix vente</th><th>Marge</th><th>Jours</th>
</tr></thead><tbody>{trs}</tbody></table>'''
    else:
        table = "<p>Aucun véhicule.</p>"
    body = tabs + f'<section class="card"><h2>Véhicules</h2>{table}<p><a class="btn" href="/vehicules/nouveau">+ Ajouter un véhicule</a></p></section>'
    return Response(layout(ctx, req, conn, "Véhicules", body, "vehicules"))


def _form_vehicule_values(f):
    return {
        "vin": (f.get("vin") or "").strip().upper() or None,
        "annee": parse_int(f.get("annee"), 1900, 2100),
        "marque": f.get("marque", "").strip(),
        "modele": f.get("modele", "").strip(),
        "kilometrage": parse_int(f.get("kilometrage"), 0, 10 ** 7),
        "carburant": f.get("carburant", "").strip() or None,
        "date_achat": parse_date(f.get("date_achat")) or datetime.now().strftime("%Y-%m-%d"),
        "prix_achat": parse_float(f.get("prix_achat")),
        "vendeur": f.get("vendeur", "").strip() or None,
        "notes": f.get("notes", "").strip() or None,
    }


def page_vehicule_new(req, ctx, conn):
    today = datetime.now().strftime("%Y-%m-%d")
    body = f'''<section class="card">
<h2>Ajouter un véhicule (achat)</h2>
<form method="post" action="/vehicules">
{csrf_input(req)}
{field("VIN (optionnel, unique)", "vin")}
{field("Année", "annee", type="number")}
{field("Marque", "marque", required=True)}
{field("Modèle", "modele", required=True)}
{field("Kilométrage", "kilometrage", type="number")}
{field("Carburant", "carburant", options=[""] + CARBURANTS)}
{field("Date d'achat", "date_achat", value=today, type="date", required=True)}
{field("Prix d'achat ($)", "prix_achat", type="number", step="0.01", required=True)}
{field("Vendeur / source (enchères, particulier...)", "vendeur")}
{field("Notes", "notes", type="textarea")}
<button type="submit" class="btn">Enregistrer l'achat</button>
</form>
</section>'''
    return Response(layout(ctx, req, conn, "Nouveau véhicule", body, "vehicules"))


def post_vehicule(req, ctx, conn):
    v = _form_vehicule_values(req.form)
    if not v["marque"] or not v["modele"]:
        return redirect("/vehicules/nouveau", "Marque et modèle sont obligatoires.", 0)
    if v["prix_achat"] is None or v["prix_achat"] < 0:
        return redirect("/vehicules/nouveau", "Prix d'achat invalide.", 0)
    try:
        cur = conn.execute(
            """INSERT INTO vehicules(vin, annee, marque, modele, kilometrage, carburant, date_achat, prix_achat, vendeur, notes, cree_par)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (v["vin"], v["annee"], v["marque"], v["modele"], v["kilometrage"], v["carburant"], v["date_achat"], v["prix_achat"], v["vendeur"], v["notes"], req.user["utilisateur_id"]),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return redirect("/vehicules/nouveau", "Ce VIN est déjà enregistré.", 0)
    vid = cur.lastrowid
    db.audit(conn, req.user["utilisateur_id"], "creation_vehicule", "vehicules", vid, f'{v["marque"]} {v["modele"]}')
    return redirect(f"/vehicules/{vid}", "Achat enregistré.")
