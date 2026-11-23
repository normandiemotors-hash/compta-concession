"""Pages depenses, rapports (P&L, fiscal), export CSV/JSON et import."""
import json
import re
from datetime import datetime

from . import db, reports, taxes
from .pages_core import TABLES_IMPORT
from .util import CATEGORIES_DEPENSES, csrf_input, csv_number, csv_response, field, fmt_date, get_id, layout, money, parse_date, parse_float, row_dict, veh_label
from .web import Response, redirect


def page_depenses(req, ctx, conn):
    mois = req.q("mois", "")
    sql = "SELECT * FROM depenses"
    params = ()
    if re.match(r"^\d{4}-\d{2}$", mois):
        sql += " WHERE substr(date,1,7) = ?"
        params = (mois,)
    sql += " ORDER BY date DESC, id DESC"
    rows = conn.execute(sql, params).fetchall()
    admin = req.user["role"] == "admin"
    today = datetime.now().strftime("%Y-%m-%d")
    trs = ""
    for d in rows:
        suppr = ""
        if admin:
            suppr = (f'<form method="post" action="/depenses/{d["id"]}/supprimer" data-confirm="Supprimer cette dépense ?">'
                     f'{csrf_input(req)}<button class="btn small danger">✕</button></form>')
        trs += (
            f'<tr><td>{fmt_date(d["date"])}</td><td>{d["categorie"]}</td><td>{d["description"] or ""}</td>'
            f'<td>{money(conn, d["montant"])}</td><td>{suppr}</td></tr>'
        )
    if rows:
        total = sum(d["montant"] for d in rows)
        table = f'''<table><thead><tr><th>Date</th><th>Catégorie</th><th>Description</th><th>Montant</th><th></th></tr></thead>
<tbody>{trs}</tbody><tfoot><tr><td colspan="3"><strong>Total</strong></td><td><strong>{money(conn, total)}</strong></td><td></td></tr></tfoot></table>'''
    else:
        table = "<p>Aucune dépense.</p>"
    body = f'''<section class="card">
<h2>Dépenses de la concession</h2>
<form method="get" action="/depenses" class="inline-form">
<label class="field"><span>Filtrer par mois</span><input type="month" name="mois" value="{mois}" data-autosubmit></label>
<button class="btn small">Filtrer</button>
</form>
{table}
</section>
<section class="card">
<h2>Ajouter une dépense</h2>
<form method="post" action="/depenses">
{csrf_input(req)}
{field("Date", "date", value=today, type="date", required=True)}
{field("Catégorie", "categorie", options=CATEGORIES_DEPENSES, required=True)}
{field("Description", "description")}
{field("Montant ($)", "montant", type="number", step="0.01", required=True)}
<button type="submit" class="btn">Ajouter</button>
</form>
</section>'''
    return Response(layout(ctx, req, conn, "Dépenses", body, "depenses"))


def post_depense(req, ctx, conn):
    f = req.form
    date_d = parse_date(f.get("date"))
    montant = parse_float(f.get("montant"))
    if not date_d or montant is None or montant <= 0:
        return redirect("/depenses", "Date et montant obligatoires.", 0)
    cur = conn.execute(
        "INSERT INTO depenses(date, categorie, description, montant, cree_par) VALUES (?,?,?,?,?)",
        (date_d, f.get("categorie", "").strip() or "Divers", f.get("description", "").strip() or None, montant, req.user["utilisateur_id"]),
    )
    conn.commit()
    db.audit(conn, req.user["utilisateur_id"], "ajout_depense", "depenses", cur.lastrowid, f"{montant}")
    return redirect("/depenses", "Dépense ajoutée.")


def post_depense_suppr(req, ctx, conn, id):
    conn.execute("DELETE FROM depenses WHERE id = ?", (get_id({"id": id}),))
    conn.commit()
    db.audit(conn, req.user["utilisateur_id"], "suppression_depense", "depenses", id)
    return redirect("/depenses", "Dépense supprimée.")


def page_rapports(req, ctx, conn):
    pnl = reports.pnl_par_mois(conn, 12)
    pnl_rows = "".join(
        f'<tr><td>{r["mois"]}</td><td>{r["ventes"]}</td><td>{money(conn, r["ca"])}</td><td>{money(conn, r["cout"])}</td>'
        f'<td>{money(conn, r["marge_brute"])}</td><td>{money(conn, r["depenses"])}</td><td><strong>{money(conn, r["marge_nette"])}</strong></td></tr>'
        for r in pnl
    )
    pnl_html = f'''<section class="card">
<h2>Compte de résultat (12 derniers mois)</h2>
<table><thead><tr><th>Mois</th><th>Ventes</th><th>Chiffre d'affaires</th><th>Coût des véhicules vendus</th><th>Marge brute</th><th>Dépenses</th><th>Marge nette</th></tr></thead>
<tbody>{pnl_rows}</tbody></table>
</section>'''
    mv = reports.marge_vehicules(conn)
    if mv:
        mv_rows = "".join(
            f'<tr><td><a href="/vehicules/{r["v"]["id"]}">{veh_label(r["v"])}</a></td>'
            f'<td>{money(conn, r["cout_total"])}</td><td>{money(conn, r["ca"]) if r["v"]["statut"] == "vendu" else "—"}</td>'
            f'<td>{money(conn, r["marge"]) if r["marge"] is not None else "—"}</td>'
            f'<td>{"%.1f %%" % r["marge_pct"] if r["marge_pct"] is not None else "—"}</td>'
            f'<td>{r["jours"] if r["jours"] is not None else "—"}</td></tr>'
            for r in mv
        )
        mv_html = f'''<section class="card">
<h2>Marge par véhicule</h2>
<table><thead><tr><th>Véhicule</th><th>Coût total</th><th>CA</th><th>Marge</th><th>Marge %</th><th>Jours</th></tr></thead><tbody>{mv_rows}</tbody></table>
</section>'''
    else:
        mv_html = '<section class="card"><h2>Marge par véhicule</h2><p>Aucun véhicule.</p></section>'
    body = pnl_html + mv_html + '<p><a class="btn" href="/rapports/fiscal">Rapport fiscal (taxes) →</a></p>'
    return Response(layout(ctx, req, conn, "Rapports", body, "rapports"))


def page_fiscal(req, ctx, conn):
    mois = req.q("mois") or datetime.now().strftime("%Y-%m")
    if not re.match(r"^\d{4}-\d{2}$", mois):
        mois = datetime.now().strftime("%Y-%m")
    r = reports.rapport_fiscal(conn, mois)
    rows = ""
    for l in r["lignes"]:
        v = l["v"]
        rows += (
            f'<tr><td>{fmt_date(v["date_vente"])}</td><td><a href="/vehicules/{v["id"]}">{veh_label(v)}</a></td>'
            f'<td>{money(conn, v["prix_vente"])}</td><td>{money(conn, v["accessoires_ht"])}</td>'
            f'<td>{money(conn, l["taxe_vente"])}</td><td>{money(conn, l["tavt"])}</td></tr>'
        )
    if r["lignes"]:
        table = f'''<table><thead><tr><th>Vente le</th><th>Véhicule</th><th>Prix de vente</th><th>Accessoires HT</th><th>Sales tax collectée</th><th>TAVT estimé</th></tr></thead>
<tbody>{rows}</tbody>
<tfoot><tr><td colspan="3"><strong>Totaux {mois}</strong> ({r["achats_mois"]["n"]} achat(s) ce mois : {money(conn, r["achats_mois"]["s"])})</td>
<td><strong>{money(conn, r["total_accessoires"])}</strong></td><td><strong>{money(conn, r["total_taxe_vente"])}</strong></td><td><strong>{money(conn, r["total_tavt"])}</strong></td></tr></tfoot></table>'''
    else:
        table = "<p>Aucune vente ce mois-ci.</p>"
    etat = taxes.get_float(conn, "taxe_vente_etat", 0.04) * 100
    comte = taxes.get_float(conn, "taxe_vente_comte", 0.02) * 100
    body = f'''<section class="card">
<h2>Rapport fiscal — {mois}</h2>
<form method="get" action="/rapports/fiscal" class="inline-form">
<label class="field"><span>Mois</span><input type="month" name="mois" value="{mois}" data-autosubmit></label>
<button class="btn small">Voir</button>
</form>
{table}
</section>
<section class="card taxbox">
<h2>Rappel des règles (Géorgie, USA) — à valider avec un comptable</h2>
<ul>
<li><strong>TAVT</strong> (Title Ad Valorem Tax, taux configuré : {r["taux_tavt"] * 100:.2f} %) : en Géorgie, il remplace la sales tax sur le prix du véhicule, sur la base de la <em>valeur du véhicule</em> (valeur marché de l'État, ou prix de vente si plus élevé). En général payé par l'acheteur à l'immatriculation.</li>
<li><strong>Sales tax</strong> (État {etat:.2f} % + local {comte:.2f} % = {r["taux_taxe_vente"] * 100:.2f} % à Dacula / Gwinnett) : s'applique aux <em>ventes séparées</em> (pièces, réparations, contrats de garantie...), pas au prix du véhicule.</li>
<li>Concessionnaire : licence dealer, éventuelles taxes sur l'inventaire et véhicules de démonstration — <strong>à confirmer avec un CPA en Géorgie</strong>.</li>
</ul>
<p class="note">Ce logiciel fournit des <strong>estimations</strong> : les taux et règles fiscales changent et dépendent de votre situation exacte. Ne les utilisez pas pour vos déclarations sans validation professionnelle.</p>
<p><a class="btn small" href="/parametres">Modifier les taux (admin)</a></p>
</section>'''
    return Response(layout(ctx, req, conn, "Rapport fiscal", body, "rapports"))


def get_export(req, ctx, conn, kind):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if kind == "vehicules.csv":
        entetes = ["ID", "VIN", "Année", "Marque", "Modèle", "Km", "Carburant", "Date achat", "Prix achat", "Vendeur", "Statut", "Date vente", "Prix vente", "Acheteur", "Mode paiement", "Accessoires HT", "Valeur marché", "Coûts", "Coût total", "CA", "Marge", "Marge %", "Jours", "Notes"]
        lignes = []
        for r in reports.marge_vehicules(conn):
            v = r["v"]
            lignes.append([
                v["id"], v["vin"] or "", v["annee"] or "", v["marque"], v["modele"],
                v["kilometrage"] if v["kilometrage"] is not None else "", v["carburant"] or "",
                v["date_achat"], csv_number(v["prix_achat"]), v["vendeur"] or "", v["statut"],
                v["date_vente"] or "", csv_number(v["prix_vente"]), v["acheteur"] or "", v["mode_paiement"] or "",
                csv_number(v["accessoires_ht"]), csv_number(v["valeur_marche"]),
                csv_number(r["cout_total"] - (v["prix_achat"] or 0)), csv_number(r["cout_total"]),
                csv_number(r["ca"]) if v["statut"] == "vendu" else "",
                csv_number(r["marge"]) if r["marge"] is not None else "",
                ("%.1f" % r["marge_pct"]).replace(".", ",") if r["marge_pct"] is not None else "",
                r["jours"] if r["jours"] is not None else "", v["notes"] or "",
            ])
        return csv_response(f"vehicules-{stamp}.csv", entetes, lignes)
    if kind == "couts.csv":
        entetes = ["ID coût", "ID véhicule", "Véhicule", "Date", "Catégorie", "Description", "Montant"]
        lignes = []
        for c in conn.execute("SELECT c.*, v.marque, v.modele, v.annee FROM couts c LEFT JOIN vehicules v ON v.id = c.vehicule_id ORDER BY c.date, c.id").fetchall():
            lignes.append([c["id"], c["vehicule_id"], f'{c["annee"] or ""} {c["marque"]} {c["modele"]}'.strip(), c["date"], c["categorie"], c["description"] or "", csv_number(c["montant"])])
        return csv_response(f"couts-{stamp}.csv", entetes, lignes)
    if kind == "depenses.csv":
        entetes = ["ID", "Date", "Catégorie", "Description", "Montant"]
        lignes = [[d["id"], d["date"], d["categorie"], d["description"] or "", csv_number(d["montant"])] for d in conn.execute("SELECT * FROM depenses ORDER BY date, id").fetchall()]
        return csv_response(f"depenses-{stamp}.csv", entetes, lignes)
    if kind == "ventes.csv":
        entetes = ["ID", "Véhicule", "Date vente", "Prix vente", "Accessoires HT", "CA total", "Coût total", "Marge", "Sales tax collectée (est.)", "TAVT estimé", "Taux TAVT", "Taux sales tax"]
        lignes = []
        for r in reports.marge_vehicules(conn, "vendu"):
            v = r["v"]
            t = taxes.taxes_vente_vehicule(conn, v)
            lignes.append([v["id"], veh_label(v), v["date_vente"], csv_number(v["prix_vente"]), csv_number(v["accessoires_ht"]), csv_number(r["ca"]), csv_number(r["cout_total"]), csv_number(r["marge"]), csv_number(t["taxe_vente"]), csv_number(t["tavt"]), str(t["taux_tavt"]).replace(".", ","), str(t["taux_taxe_vente"]).replace(".", ",")])
        return csv_response(f"ventes-taxes-{stamp}.csv", entetes, lignes)
    if kind == "backup.json":
        data = {
            "version": 1,
            "application": "compta-concession",
            "export_le": datetime.now().isoformat(timespec="seconds"),
            "parametres": [row_dict(r) for r in conn.execute("SELECT cle, valeur, description FROM parametres ORDER BY cle").fetchall()],
            "vehicules": [row_dict(r) for r in conn.execute("SELECT * FROM vehicules ORDER BY id").fetchall()],
            "couts": [row_dict(r) for r in conn.execute("SELECT * FROM couts ORDER BY id").fetchall()],
            "depenses": [row_dict(r) for r in conn.execute("SELECT * FROM depenses ORDER BY id").fetchall()],
        }
        return Response(json.dumps(data, ensure_ascii=False, indent=1), 200, "application/json; charset=utf-8", {"Content-Disposition": f'attachment; filename="sauvegarde-compta-{stamp}.json"'})
    return Response("Export inconnu.", 404, "text/plain; charset=utf-8")


def page_export(req, ctx, conn):
    admin = req.user["role"] == "admin"
    import_html = ""
    if admin:
        import_html = f'''<section class="card">
<h2>Restaurer une sauvegarde JSON (admin)</h2>
<form id="import-form">
<input type="file" id="import-file" accept=".json,application/json">
<button type="submit" class="btn danger">Importer (remplace véhicules, coûts, dépenses et paramètres)</button>
</form>
<p class="note">Les comptes utilisateurs et le journal ne sont pas touchés.</p>
</section>'''
    body = f'''<section class="card">
<h2>Exports (CSV ouvrable dans Excel, « ; » comme séparateur)</h2>
<ul class="exports">
<li><a class="btn" href="/export/vehicules.csv">Véhicules (tous, avec coûts et marges)</a></li>
<li><a class="btn" href="/export/couts.csv">Coûts par véhicule</a></li>
<li><a class="btn" href="/export/depenses.csv">Dépenses</a></li>
<li><a class="btn" href="/export/ventes.csv">Ventes + taxes estimées (pour le comptable)</a></li>
<li><a class="btn" href="/export/backup.json">Sauvegarde complète JSON</a></li>
</ul>
</section>
<section class="card">
<h2>Transférer l'application sur un autre ordinateur (famille)</h2>
<ol>
<li>Copiez <strong>tout le dossier</strong> de l'application sur une clé USB / le cloud, ou</li>
<li>copiez seulement le fichier <code>data/garage.db</code> (toutes les données) dans le dossier <code>data/</code> de l'autre ordinateur, puis lancez <code>app.py</code>, ou</li>
<li>exportez la sauvegarde JSON ici, puis importez-la sur l'autre machine (admin uniquement).</li>
</ol>
<p class="note">Aucune connexion Internet n'est nécessaire : tout reste sur votre ordinateur / votre réseau local.</p>
</section>
{import_html}'''
    return Response(layout(ctx, req, conn, "Export & sauvegarde", body, "export"))


def post_import(req, ctx, conn):
    try:
        data = json.loads(req.body.decode("utf-8"))
    except Exception:
        return Response(json.dumps({"ok": False, "message": "JSON invalide."}), 400, "application/json; charset=utf-8")
    if not isinstance(data, dict) or "vehicules" not in data:
        return Response(json.dumps({"ok": False, "message": "Fichier de sauvegarde non reconnu."}), 400, "application/json; charset=utf-8")
    try:
        with conn:
            conn.execute("DELETE FROM couts")
            conn.execute("DELETE FROM vehicules")
            conn.execute("DELETE FROM depenses")
            conn.execute("DELETE FROM parametres")
            for table, cols in TABLES_IMPORT.items():
                for row in data.get(table) or []:
                    if not isinstance(row, dict):
                        continue
                    vals = [row.get(c) for c in cols]
                    conn.execute(f"INSERT INTO {table}({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
            for cle, valeur, description in taxes.DEFAULT_PARAMS:
                conn.execute("INSERT OR IGNORE INTO parametres(cle, valeur, description) VALUES (?,?,?)", (cle, valeur, description))
    except Exception as exc:
        return Response(json.dumps({"ok": False, "message": f"Import refusé : {exc}"}), 400, "application/json; charset=utf-8")
    db.audit(conn, req.user["utilisateur_id"], "import_sauvegarde")
    return Response(json.dumps({"ok": True, "message": "Sauvegarde importée."}), 200, "application/json; charset=utf-8")
