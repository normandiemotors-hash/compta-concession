"""Pages de fiche vehicule : detail, couts, vente, modifications."""
import sqlite3
from datetime import datetime

from . import db, reports, taxes
from .pages_core import _form_vehicule_values
from .util import CARBURANTS, CATEGORIES_COUTS, MODES_PAIEMENT, csrf_input, field, fmt_date, get_id, layout, money, parse_date, parse_float, veh_label
from .web import Response, redirect


def page_vehicule(req, ctx, conn, id):
    vid = get_id({"id": id})
    v = conn.execute("SELECT * FROM vehicules WHERE id = ?", (vid,)).fetchone() if vid else None
    if not v:
        return redirect("/vehicules", "Véhicule introuvable.", 0)
    couts = conn.execute("SELECT * FROM couts WHERE vehicule_id = ? ORDER BY date, id", (vid,)).fetchall()
    tc = reports.total_cout(conn, v)
    today = datetime.now().strftime("%Y-%m-%d")
    admin = req.user["role"] == "admin"

    info = f'''<section class="card">
<h2>{veh_label(v)}</h2>
<dl class="infos">
<dt>VIN</dt><dd>{v["vin"] or "—"}</dd>
<dt>Année</dt><dd>{v["annee"] if v["annee"] is not None else "—"}</dd>
<dt>Kilométrage</dt><dd>{v["kilometrage"] if v["kilometrage"] is not None else "—"}</dd>
<dt>Carburant</dt><dd>{v["carburant"] or "—"}</dd>
<dt>Acheté le</dt><dd>{fmt_date(v["date_achat"])} pour {money(conn, v["prix_achat"])}</dd>
<dt>Vendeur</dt><dd>{v["vendeur"] or "—"}</dd>
<dt>Statut</dt><dd>{"vendu" if v["statut"] == "vendu" else "en stock"}</dd>
<dt>Coût total (achat + coûts)</dt><dd><strong>{money(conn, tc)}</strong></dd>
<dt>Notes</dt><dd>{v["notes"] or "—"}</dd>
</dl>
</section>'''

    cout_rows = ""
    for c in couts:
        suppr = ""
        if admin:
            suppr = (f'<form method="post" action="/vehicules/{vid}/couts/{c["id"]}/supprimer" data-confirm="Supprimer ce coût ?">'
                     f'{csrf_input(req)}<button class="btn small danger">✕</button></form>')
        cout_rows += (
            f'<tr><td>{fmt_date(c["date"])}</td><td>{c["categorie"]}</td><td>{c["description"] or ""}</td>'
            f'<td>{money(conn, c["montant"])}</td><td>{suppr}</td></tr>'
        )
    if couts:
        couts_table = f'''<table><thead><tr><th>Date</th><th>Catégorie</th><th>Description</th><th>Montant</th><th></th></tr></thead>
<tbody>{cout_rows}</tbody>
<tfoot><tr><td colspan="3"><strong>Total coûts</strong></td><td><strong>{money(conn, sum(c["montant"] for c in couts))}</strong></td><td></td></tr></tfoot></table>'''
    else:
        couts_table = "<p>Aucun coût.</p>"
    couts_html = f'''<section class="card" id="couts">
<h2>Coûts du véhicule (transport, reconditionnement, réparations...)</h2>
{couts_table}
<form method="post" action="/vehicules/{vid}/couts" class="inline-form">
{csrf_input(req)}
{field("Date", "date", value=today, type="date", required=True)}
{field("Catégorie", "categorie", options=CATEGORIES_COUTS, required=True)}
{field("Description", "description")}
{field("Montant ($)", "montant", type="number", step="0.01", required=True)}
<button type="submit" class="btn small">+ Ajouter</button>
</form>
</section>'''

    if v["statut"] == "vendu":
        t = taxes.taxes_vente_vehicule(conn, v)
        marge = (v["prix_vente"] or 0) + (v["accessoires_ht"] or 0) - tc
        rouvrir = ""
        if admin:
            rouvrir = (f'<form method="post" action="/vehicules/{vid}/rouvrir" data-confirm="Annuler la vente et remettre le véhicule en stock ?">'
                       f'{csrf_input(req)}<button class="btn small">Remettre en stock (admin)</button></form>')
        vente_html = f'''<section class="card">
<h2>Vente</h2>
<dl class="infos">
<dt>Vendu le</dt><dd>{fmt_date(v["date_vente"])}</dd>
<dt>Prix de vente</dt><dd>{money(conn, v["prix_vente"])}</dd>
<dt>Accessoires HT (pièces, garantie...)</dt><dd>{money(conn, v["accessoires_ht"])}</dd>
<dt>Acheteur</dt><dd>{v["acheteur"] or "—"}</dd>
<dt>Mode de paiement</dt><dd>{v["mode_paiement"] or "—"}</dd>
<dt>Marge sur ce véhicule</dt><dd><strong>{money(conn, marge)}</strong></dd>
</dl>
<div class="taxbox">
<h3>Taxes estimées sur cette vente</h3>
<ul>
<li>TAVT Géorgie (taux {t["taux_tavt"] * 100:.2f} %) sur base {money(conn, taxes.base_tavt(v["prix_vente"], v["valeur_marche"]))} = <strong>{money(conn, t["tavt"])}</strong> — en Géorgie, le TAVT remplace la sales tax sur le véhicule ; en général payé par l'acheteur lors de l'immatriculation.</li>
<li>Sales tax ({t["taux_taxe_vente"] * 100:.2f} %) sur les accessoires {money(conn, v["accessoires_ht"])} = <strong>{money(conn, t["taxe_vente"])}</strong> — à reverser au fisc si vous collectez la taxe.</li>
</ul>
<p class="note">Estimations à valider avec un comptable (Géorgie / comté de Gwinnett) : taux en vigueur, payeur du TAVT, exemptions concessionnaire.</p>
</div>
{rouvrir}
</section>'''
    else:
        vente_html = f'''<section class="card">
<h2>Enregistrer la revente</h2>
<form method="post" action="/vehicules/{vid}/vendre">
{csrf_input(req)}
{field("Date de vente", "date_vente", value=today, type="date", required=True)}
{field("Prix de vente ($)", "prix_vente", type="number", step="0.01", required=True)}
{field("Acheteur", "acheteur")}
{field("Mode de paiement", "mode_paiement", options=[""] + MODES_PAIEMENT)}
{field("Accessoires vendus HT ($) — pièces, garantie...", "accessoires_ht", type="number", step="0.01")}
{field("Valeur marché Géorgie si connue ($) — base du TAVT si > prix de vente", "valeur_marche", type="number", step="0.01")}
<button type="submit" class="btn">Enregistrer la vente</button>
</form>
<p class="note">En Géorgie, le prix du véhicule n'est pas soumis à la sales tax : le TAVT s'applique à la place (voir Rapports &gt; Fiscal).</p>
</section>'''

    edit_form = f'''<details class="card">
<summary><h2 style="display:inline">Modifier le véhicule</h2></summary>
<form method="post" action="/vehicules/{vid}/modifier">
{csrf_input(req)}
{field("VIN", "vin", value=v["vin"] or "")}
{field("Année", "annee", value=v["annee"] if v["annee"] is not None else "", type="number")}
{field("Marque", "marque", value=v["marque"], required=True)}
{field("Modèle", "modele", value=v["modele"], required=True)}
{field("Kilométrage", "kilometrage", value=v["kilometrage"] if v["kilometrage"] is not None else "", type="number")}
{field("Carburant", "carburant", value=v["carburant"] or "", options=[""] + CARBURANTS)}
{field("Date d'achat", "date_achat", value=v["date_achat"], type="date", required=True)}
{field("Prix d'achat ($)", "prix_achat", value=v["prix_achat"], type="number", step="0.01", required=True)}
{field("Vendeur / source", "vendeur", value=v["vendeur"] or "")}
{field("Notes", "notes", value=v["notes"] or "", type="textarea")}
<button type="submit" class="btn small">Enregistrer</button>
</form>
</details>'''

    suppr = ""
    if admin:
        suppr = f'''<section class="card danger-zone">
<h2>Zone administrateur</h2>
<form method="post" action="/vehicules/{vid}/supprimer" data-confirm="SUPPRIMER définitivement ce véhicule et ses coûts ?">
{csrf_input(req)}
<button type="submit" class="btn danger">Supprimer le véhicule</button>
</form>
</section>'''

    body = info + couts_html + vente_html + edit_form + suppr
    return Response(layout(ctx, req, conn, veh_label(v), body, "vehicules"))


def post_modifier(req, ctx, conn, id):
    vid = get_id({"id": id})
    v = conn.execute("SELECT * FROM vehicules WHERE id = ?", (vid,)).fetchone() if vid else None
    if not v:
        return redirect("/vehicules", "Véhicule introuvable.", 0)
    vals = _form_vehicule_values(req.form)
    if not vals["marque"] or not vals["modele"]:
        return redirect(f"/vehicules/{vid}", "Marque et modèle sont obligatoires.", 0)
    if vals["prix_achat"] is None or vals["prix_achat"] < 0:
        return redirect(f"/vehicules/{vid}", "Prix d'achat invalide.", 0)
    try:
        conn.execute(
            """UPDATE vehicules SET vin=?, annee=?, marque=?, modele=?, kilometrage=?, carburant=?, date_achat=?, prix_achat=?, vendeur=?, notes=?, modifie_par=?, modifie_le=? WHERE id=?""",
            (vals["vin"], vals["annee"], vals["marque"], vals["modele"], vals["kilometrage"], vals["carburant"], vals["date_achat"], vals["prix_achat"], vals["vendeur"], vals["notes"], req.user["utilisateur_id"], datetime.now().isoformat(timespec="seconds"), vid),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return redirect(f"/vehicules/{vid}", "Ce VIN est déjà utilisé par un autre véhicule.", 0)
    db.audit(conn, req.user["utilisateur_id"], "modification_vehicule", "vehicules", vid, f'{vals["marque"]} {vals["modele"]}')
    return redirect(f"/vehicules/{vid}", "Véhicule modifié.")


def post_cout(req, ctx, conn, id):
    vid = get_id({"id": id})
    v = conn.execute("SELECT id FROM vehicules WHERE id = ?", (vid,)).fetchone() if vid else None
    if not v:
        return redirect("/vehicules", "Véhicule introuvable.", 0)
    f = req.form
    date_c = parse_date(f.get("date")) or datetime.now().strftime("%Y-%m-%d")
    montant = parse_float(f.get("montant"))
    if montant is None or montant <= 0:
        return redirect(f"/vehicules/{vid}#couts", "Montant invalide.", 0)
    cur = conn.execute(
        "INSERT INTO couts(vehicule_id, date, categorie, description, montant, cree_par) VALUES (?,?,?,?,?,?)",
        (vid, date_c, f.get("categorie", "").strip() or "Autres", f.get("description", "").strip() or None, montant, req.user["utilisateur_id"]),
    )
    conn.commit()
    db.audit(conn, req.user["utilisateur_id"], "ajout_cout", "couts", cur.lastrowid, f"vehicule #{vid} : {montant}")
    return redirect(f"/vehicules/{vid}#couts", "Coût ajouté.")


def post_cout_suppr(req, ctx, conn, id, cid):
    vid = get_id({"id": id})
    conn.execute("DELETE FROM couts WHERE id = ? AND vehicule_id = ?", (get_id({"id": cid}), vid))
    conn.commit()
    db.audit(conn, req.user["utilisateur_id"], "suppression_cout", "couts", cid, f"vehicule #{vid}")
    return redirect(f"/vehicules/{vid}#couts", "Coût supprimé.")


def post_vendre(req, ctx, conn, id):
    vid = get_id({"id": id})
    v = conn.execute("SELECT * FROM vehicules WHERE id = ?", (vid,)).fetchone() if vid else None
    if not v:
        return redirect("/vehicules", "Véhicule introuvable.", 0)
    if v["statut"] != "en_stock":
        return redirect(f"/vehicules/{vid}", "Ce véhicule est déjà vendu.", 0)
    f = req.form
    date_vente = parse_date(f.get("date_vente"))
    prix_vente = parse_float(f.get("prix_vente"))
    if not date_vente or prix_vente is None or prix_vente <= 0:
        return redirect(f"/vehicules/{vid}", "Date et prix de vente sont obligatoires.", 0)
    accessoires = parse_float(f.get("accessoires_ht")) or 0.0
    valeur_marche = parse_float(f.get("valeur_marche"))
    conn.execute(
        """UPDATE vehicules SET statut='vendu', date_vente=?, prix_vente=?, acheteur=?, mode_paiement=?, accessoires_ht=?, valeur_marche=?, modifie_par=?, modifie_le=? WHERE id=?""",
        (date_vente, prix_vente, f.get("acheteur", "").strip() or None, f.get("mode_paiement", "").strip() or None, accessoires, valeur_marche, req.user["utilisateur_id"], datetime.now().isoformat(timespec="seconds"), vid),
    )
    conn.commit()
    tc = reports.total_cout(conn, v)
    marge = prix_vente + accessoires - tc
    db.audit(conn, req.user["utilisateur_id"], "vente_vehicule", "vehicules", vid, f"prix={prix_vente} marge={marge:.2f}")
    return redirect(f"/vehicules/{vid}", f"Vente enregistrée. Marge estimée : {marge:,.2f} $.")


def post_rouvrir(req, ctx, conn, id):
    vid = get_id({"id": id})
    conn.execute(
        """UPDATE vehicules SET statut='en_stock', date_vente=NULL, prix_vente=NULL, acheteur=NULL, mode_paiement=NULL, accessoires_ht=0, valeur_marche=NULL, modifie_par=?, modifie_le=? WHERE id=?""",
        (req.user["utilisateur_id"], datetime.now().isoformat(timespec="seconds"), vid),
    )
    conn.commit()
    db.audit(conn, req.user["utilisateur_id"], "annulation_vente", "vehicules", vid)
    return redirect(f"/vehicules/{vid}", "Vente annulée, véhicule remis en stock.")


def post_vehicule_suppr(req, ctx, conn, id):
    vid = get_id({"id": id})
    conn.execute("DELETE FROM vehicules WHERE id = ?", (vid,))
    conn.commit()
    db.audit(conn, req.user["utilisateur_id"], "suppression_vehicule", "vehicules", vid)
    return redirect("/vehicules", "Véhicule supprimé.")
