"""Pages d'administration : parametres, comptes famille, journal d'audit."""
import sqlite3

from . import db, security, taxes
from .util import ROLES, csrf_input, field, get_id, layout
from .web import Response, redirect


def page_parametres(req, ctx, conn):
    rows = conn.execute("SELECT * FROM parametres ORDER BY cle").fetchall()
    champs = "".join(field(r["cle"], "p_" + r["cle"], r["valeur"], note=r["description"]) for r in rows)
    body = f'''<section class="card">
<h2>Paramètres</h2>
<form method="post" action="/parametres">
{csrf_input(req)}
{champs}
<button type="submit" class="btn">Enregistrer</button>
</form>
</section>
<section class="card taxbox">
<h2>Attention — paramètres fiscaux</h2>
<p>Les taux (TAVT Géorgie, sales tax État + comté de Gwinnett) sont des <strong>valeurs par défaut</strong>. Faites-les vérifier et ajuster par un comptable avant toute déclaration fiscale.</p>
</section>'''
    return Response(layout(ctx, req, conn, "Paramètres", body, "parametres"))


def post_params(req, ctx, conn):
    f = req.form
    for r in conn.execute("SELECT cle FROM parametres").fetchall():
        cle = r["cle"]
        if "p_" + cle in f:
            taxes.set_param(conn, cle, f["p_" + cle].strip())
    conn.commit()
    db.audit(conn, req.user["utilisateur_id"], "modification_parametres")
    return redirect("/parametres", "Paramètres enregistrés.")


def page_utilisateurs(req, ctx, conn):
    users = conn.execute("SELECT id, nom_utilisateur, role, cree_le FROM utilisateurs ORDER BY id").fetchall()
    trs = ""
    for u in users:
        self_flag = " (vous)" if u["id"] == req.user["utilisateur_id"] else ""
        trs += (
            f'<tr><td>{u["nom_utilisateur"]}{self_flag}</td><td>{u["role"]}</td><td>{u["cree_le"][:19]}</td>'
            f'<td><form method="post" action="/utilisateurs/{u["id"]}/supprimer" data-confirm="Supprimer le compte {u["nom_utilisateur"]} ?">{csrf_input(req)}<button class="btn small danger">✕</button></form></td></tr>'
        )
    body = f'''<section class="card">
<h2>Comptes de la famille</h2>
<table><thead><tr><th>Nom d'utilisateur</th><th>Rôle</th><th>Créé le</th><th></th></tr></thead><tbody>{trs}</tbody></table>
<p class="note">Rôles : <strong>admin</strong> (tout, y compris suppressions et paramètres) · <strong>membre</strong> (ajoute/modifie véhicules et dépenses). Chaque action est tracée dans le journal.</p>
</section>
<section class="card">
<h2>Créer un compte</h2>
<form method="post" action="/utilisateurs">
{csrf_input(req)}
{field("Nom d'utilisateur", "nom", required=True)}
{field("Mot de passe (8 caractères min.)", "mdp", type="password", required=True)}
{field("Rôle", "role", options=ROLES, required=True)}
<button type="submit" class="btn">Créer le compte</button>
</form>
</section>'''
    return Response(layout(ctx, req, conn, "Comptes famille", body, "utilisateurs"))


def post_user(req, ctx, conn):
    f = req.form
    nom = f.get("nom", "").strip()
    mdp = f.get("mdp", "")
    role = f.get("role", "membre")
    if not nom or len(mdp) < 8 or role not in ROLES:
        return redirect("/utilisateurs", "Nom requis, mot de passe 8 caractères min., rôle valide.", 0)
    try:
        conn.execute("INSERT INTO utilisateurs(nom_utilisateur, hash_mdp, role) VALUES (?,?,?)", (nom, security.hash_password(mdp), role))
        conn.commit()
    except sqlite3.IntegrityError:
        return redirect("/utilisateurs", "Ce nom d'utilisateur existe déjà.", 0)
    db.audit(conn, req.user["utilisateur_id"], "creation_utilisateur", "utilisateurs", None, f"{nom} ({role})")
    return redirect("/utilisateurs", f"Compte « {nom} » créé.")


def post_user_suppr(req, ctx, conn, id):
    uid = get_id({"id": id})
    if uid is None:
        return redirect("/utilisateurs", "Compte introuvable.", 0)
    if uid == req.user["utilisateur_id"]:
        return redirect("/utilisateurs", "Vous ne pouvez pas supprimer votre propre compte.", 0)
    target = conn.execute("SELECT * FROM utilisateurs WHERE id = ?", (uid,)).fetchone()
    if not target:
        return redirect("/utilisateurs", "Compte introuvable.", 0)
    if target["role"] == "admin":
        n = conn.execute("SELECT COUNT(*) n FROM utilisateurs WHERE role='admin'").fetchone()["n"]
        if n <= 1:
            return redirect("/utilisateurs", "Gardez au moins un compte administrateur.", 0)
    conn.execute("DELETE FROM utilisateurs WHERE id = ?", (uid,))
    conn.commit()
    db.audit(conn, req.user["utilisateur_id"], "suppression_utilisateur", "utilisateurs", uid, target["nom_utilisateur"])
    return redirect("/utilisateurs", f"Compte « {target['nom_utilisateur']} » supprimé.")


def page_audit(req, ctx, conn):
    rows = conn.execute(
        """SELECT a.id, a.date, a.action, a.table_cible, a.id_cible, a.detail, u.nom_utilisateur
           FROM audit a LEFT JOIN utilisateurs u ON u.id = a.utilisateur_id ORDER BY a.id DESC LIMIT 300"""
    ).fetchall()
    trs = ""
    for r in rows:
        cible = r["table_cible"] or ""
        if r["id_cible"]:
            cible += f" #{r['id_cible']}"
        trs += (
            f'<tr><td>{r["date"][:19]}</td><td>{r["nom_utilisateur"] or "—"}</td><td>{r["action"]}</td>'
            f'<td>{cible}</td><td>{r["detail"] or ""}</td></tr>'
        )
    table = f'<table><thead><tr><th>Date</th><th>Utilisateur</th><th>Action</th><th>Cible</th><th>Détail</th></tr></thead><tbody>{trs}</tbody></table>' if rows else "<p>Journal vide.</p>"
    body = f"<section class=\"card\"><h2>Journal d'activité (300 dernières actions)</h2>{table}</section>"
    return Response(layout(ctx, req, conn, "Journal", body, "audit"))
