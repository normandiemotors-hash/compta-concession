"""Calculs des tableaux de bord et rapports (P&L, fiscal, aging)."""
from datetime import date, datetime

from . import taxes


def _aujourdhui():
    return date.today().isoformat()


def couts_par_vehicule(conn):
    rows = conn.execute("SELECT vehicule_id, SUM(montant) s FROM couts GROUP BY vehicule_id").fetchall()
    return {r["vehicule_id"]: r["s"] or 0.0 for r in rows}


def total_cout(conn, v, couts=None):
    if couts is None:
        couts = couts_par_vehicule(conn)
    return (v["prix_achat"] or 0.0) + couts.get(v["id"], 0.0)


def jours_stock(v, today=None):
    today = today or _aujourdhui()
    fin = v["date_vente"] or today
    try:
        return (datetime.strptime(fin, "%Y-%m-%d").date() - datetime.strptime(v["date_achat"], "%Y-%m-%d").date()).days
    except (TypeError, ValueError):
        return None


def dashboard(conn, today=None):
    today = today or _aujourdhui()
    mois = today[:7]
    en_stock = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(prix_achat),0) s FROM vehicules WHERE statut='en_stock'"
    ).fetchone()
    couts_stock = conn.execute(
        """SELECT COALESCE(SUM(c.montant),0) s FROM couts c
           JOIN vehicules v ON v.id = c.vehicule_id WHERE v.statut='en_stock'"""
    ).fetchone()["s"]
    ventes = conn.execute(
        """SELECT COUNT(*) n, COALESCE(SUM(prix_vente + accessoires_ht),0) ca
           FROM vehicules WHERE statut='vendu' AND substr(date_vente,1,7) = ?""",
        (mois,),
    ).fetchone()
    depenses = conn.execute(
        "SELECT COALESCE(SUM(montant),0) s FROM depenses WHERE substr(date,1,7) = ?", (mois,)
    ).fetchone()["s"]
    couts = couts_par_vehicule(conn)
    vendus_mois = conn.execute(
        "SELECT * FROM vehicules WHERE statut='vendu' AND substr(date_vente,1,7) = ?", (mois,)
    ).fetchall()
    cout_vendus = sum(total_cout(conn, v, couts) for v in vendus_mois)
    accessoires = sum(v["accessoires_ht"] or 0.0 for v in vendus_mois)
    tavt = sum(taxes.tavt_estime(conn, v["prix_vente"], v["valeur_marche"]) for v in vendus_mois)
    return {
        "en_stock": en_stock["n"],
        "valeur_stock": en_stock["s"] + (couts_stock or 0.0),
        "ventes_nb": ventes["n"],
        "ca_mois": ventes["ca"],
        "cout_vendus_mois": cout_vendus,
        "marge_mois": ventes["ca"] - cout_vendus,
        "depenses_mois": depenses,
        "marge_nette_mois": ventes["ca"] - cout_vendus - depenses,
        "taxe_vente_mois": taxes.taxe_vente_accessoires(conn, accessoires),
        "tavt_mois": round(tavt, 2),
    }


def pnl_par_mois(conn, nb_mois=12, today=None):
    today = today or _aujourdhui()
    annee, mois = int(today[:4]), int(today[5:7])
    mois_liste = []
    for _ in range(nb_mois):
        mois_liste.append(f"{annee:04d}-{mois:02d}")
        mois -= 1
        if mois == 0:
            mois, annee = 12, annee - 1
    couts = couts_par_vehicule(conn)
    depenses = {
        r["m"]: r["s"] for r in conn.execute(
            "SELECT substr(date,1,7) m, SUM(montant) s FROM depenses GROUP BY m"
        ).fetchall()
    }
    vendus = conn.execute("SELECT * FROM vehicules WHERE statut='vendu'").fetchall()
    par_mois = {}
    for v in vendus:
        m = (v["date_vente"] or "")[:7]
        d = par_mois.setdefault(m, {"n": 0, "ca": 0.0, "cout": 0.0})
        d["n"] += 1
        d["ca"] += (v["prix_vente"] or 0.0) + (v["accessoires_ht"] or 0.0)
        d["cout"] += total_cout(conn, v, couts)
    result = []
    for m in mois_liste:
        d = par_mois.get(m, {"n": 0, "ca": 0.0, "cout": 0.0})
        dep = depenses.get(m, 0.0)
        result.append({
            "mois": m, "ventes": d["n"], "ca": d["ca"], "cout": d["cout"],
            "marge_brute": d["ca"] - d["cout"], "depenses": dep,
            "marge_nette": d["ca"] - d["cout"] - dep,
        })
    return result


def marge_vehicules(conn, statut=None):
    couts = couts_par_vehicule(conn)
    sql = "SELECT * FROM vehicules"
    params = ()
    if statut:
        sql += " WHERE statut = ?"
        params = (statut,)
    sql += " ORDER BY date_achat DESC"
    out = []
    for v in conn.execute(sql, params).fetchall():
        tc = total_cout(conn, v, couts)
        ca = (v["prix_vente"] or 0.0) + (v["accessoires_ht"] or 0.0) if v["statut"] == "vendu" else 0.0
        marge = ca - tc if v["statut"] == "vendu" else None
        out.append({
            "v": v, "cout_total": tc, "ca": ca, "marge": marge,
            "marge_pct": (marge / tc * 100.0) if marge is not None and tc else None,
            "jours": jours_stock(v),
        })
    return out


def rapport_fiscal(conn, mois):
    rows = conn.execute(
        "SELECT * FROM vehicules WHERE statut='vendu' AND substr(date_vente,1,7) = ? ORDER BY date_vente",
        (mois,),
    ).fetchall()
    lignes = []
    for v in rows:
        t = taxes.taxes_vente_vehicule(conn, v)
        lignes.append({"v": v, "tavt": t["tavt"], "taxe_vente": t["taxe_vente"]})
    return {
        "mois": mois,
        "lignes": lignes,
        "total_accessoires": sum((l["v"]["accessoires_ht"] or 0.0) for l in lignes),
        "total_taxe_vente": round(sum(l["taxe_vente"] for l in lignes), 2),
        "total_tavt": round(sum(l["tavt"] for l in lignes), 2),
        "taux_tavt": taxes.taux_tavt(conn),
        "taux_taxe_vente": taxes.taux_taxe_vente(conn),
        "achats_mois": conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(prix_achat),0) s FROM vehicules WHERE substr(date_achat,1,7) = ?",
            (mois,),
        ).fetchone(),
    }


def aging(conn, seuil_jours=60, today=None):
    out = []
    for v in conn.execute("SELECT * FROM vehicules WHERE statut='en_stock' ORDER BY date_achat").fetchall():
        j = jours_stock(v, today)
        if j is not None and j >= seuil_jours:
            out.append({"v": v, "jours": j})
    return out
