"""Moteur de taxes : taux configurables (Georgie, USA) et calculs d'estimations."""

DEFAULT_PARAMS = [
    ("nom_concession", "Normandie Motors (Dacula, GA)", "Nom affiche dans l'en-tete de l'application."),
    ("devise", "USD", "Devise d'affichage (USD recommande aux USA)."),
    ("taux_tavt", "0.07", "TAVT Georgie (Title Ad Valorem Tax) - taux a VERIFIER aupres du GA Dept. of Revenue ou d'un comptable (6,6 % jusqu'en 2024, releve ensuite). S'applique a la valeur du vehicule, pas a la sales tax."),
    ("taxe_vente_etat", "0.04", "Sales tax Etat de Georgie (4 %)."),
    ("taxe_vente_comte", "0.02", "Taxe de vente locale, comte de Gwinnett (Dacula) - a VERIFIER (souvent 2 %, soit 6 % au total avec l'Etat). S'applique aux pieces, services et garanties vendus separement, PAS au prix du vehicule (remplace par le TAVT)."),
]


def get_param(conn, cle, defaut=""):
    row = conn.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    return row["valeur"] if row else defaut


def set_param(conn, cle, valeur):
    from datetime import datetime
    conn.execute(
        "UPDATE parametres SET valeur = ?, modifie_le = ? WHERE cle = ?",
        (valeur, datetime.now().isoformat(timespec="seconds"), cle),
    )


def get_float(conn, cle, defaut=0.0):
    try:
        return float(get_param(conn, cle, str(defaut)).replace(",", "."))
    except (TypeError, ValueError):
        return defaut


def taux_tavt(conn):
    return get_float(conn, "taux_tavt", 0.07)


def taux_taxe_vente(conn):
    return get_float(conn, "taxe_vente_etat", 0.04) + get_float(conn, "taxe_vente_comte", 0.02)


def base_tavt(prix_vente, valeur_marche=None):
    base = prix_vente or 0.0
    if valeur_marche and valeur_marche > base:
        base = valeur_marche
    return base


def tavt_estime(conn, prix_vente, valeur_marche=None):
    return round(base_tavt(prix_vente, valeur_marche) * taux_tavt(conn), 2)


def taxe_vente_accessoires(conn, accessoires_ht):
    return round((accessoires_ht or 0.0) * taux_taxe_vente(conn), 2)


def taxes_vente_vehicule(conn, row):
    """row: ligne de la table vehicules (statut 'vendu')."""
    return {
        "tavt": tavt_estime(conn, row["prix_vente"], row["valeur_marche"]),
        "taxe_vente": taxe_vente_accessoires(conn, row["accessoires_ht"]),
        "taux_tavt": taux_tavt(conn),
        "taux_taxe_vente": taux_taxe_vente(conn),
    }
