#!/usr/bin/env python3
"""Test de fumee : demarre le serveur sur 127.0.0.1 et enchaine les actions principales."""
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8123
ORIGIN = f"http://127.0.0.1:{PORT}"


def main():
    tmp = tempfile.mkdtemp(prefix="compta-test-")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE, "app.py"), "--host", "127.0.0.1", "--port", str(PORT), "--data", tmp, "--demo"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

        def get(path):
            try:
                with opener.open(ORIGIN + path, timeout=10) as r:
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")

        def post(path, data=None, raw=None, ctype=None):
            if raw is not None:
                req = urllib.request.Request(ORIGIN + path, data=raw.encode("utf-8"), method="POST")
                req.add_header("Content-Type", ctype or "application/json")
                m = re.search(r'name="csrf" content="([^"]+)"', globals().get("_last_page", ""))
                if m:
                    req.add_header("X-CSRF-Token", m.group(1))
            else:
                body = urllib.parse.urlencode(data or {}).encode("utf-8")
                req = urllib.request.Request(ORIGIN + path, data=body, method="POST")
            try:
                with opener.open(req, timeout=10) as r:
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")

        def wait_ready():
            for _ in range(60):
                try:
                    with urllib.request.urlopen(ORIGIN + "/login", timeout=2) as r:
                        if r.status == 200:
                            return
                except Exception:
                    time.sleep(0.5)
            raise RuntimeError("serveur non demarre")

        wait_ready()

        s, page = get("/setup")
        assert s == 200 and "Premier démarrage" in page, "page setup"
        s, page = post("/setup", {"nom": "admin", "mdp": "motdepasse123", "mdp2": "motdepasse123"})
        assert s == 200 and "Tableau de bord" in page, "setup+login auto"
        globals()["_last_page"] = page

        s, page = get("/")
        assert "Véhicules en stock" in page, "dashboard"
        assert "Toyota" in page or "Camry" in page, "demo seed visible"
        assert "/static/logo.png" in page, "logo dans l'en-tete"
        s, logo = get("/static/logo.png")
        assert s == 200, "logo servi"
        globals()["_last_page"] = page

        s, page = post("/vehicules", {
            "vin": "TESTVIN0001", "annee": "2019", "marque": "Mazda", "modele": "CX-5",
            "kilometrage": "65000", "carburant": "Essence", "date_achat": "2025-04-01",
            "prix_achat": "13500", "vendeur": "Encheres", "notes": "test", "csrf": re.search(r'name="csrf" value="([^"]+)"', page).group(1),
        })
        assert s == 200 and "/vehicules/4" in page or "Achat enregistré" in page, "creation vehicule"
        globals()["_last_page"] = page

        m = re.search(r'csrf" value="([^"]+)"', page)
        csrf = m.group(1)
        s, page = post("/vehicules/4/couts", {"date": "2025-04-03", "categorie": "Transport", "description": "Livraison", "montant": "500", "csrf": csrf})
        assert "Coût ajouté" in page or "Livraison" in page, "ajout cout"
        globals()["_last_page"] = page

        s, page = post("/vehicules/4/vendre", {"date_vente": "2025-04-20", "prix_vente": "17200", "acheteur": "Acheteur Test", "mode_paiement": "Comptant", "accessoires_ht": "300", "valeur_marche": "", "csrf": csrf})
        assert "Vente enregistrée" in page, "vente"
        assert "TAVT" in page, "taxbox TAVT"
        globals()["_last_page"] = page

        s, page = post("/depenses", {"date": "2025-04-05", "categorie": "Publicité", "description": " petites annonces", "montant": "150", "csrf": csrf})
        assert "Dépense ajoutée" in page, "depense"
        globals()["_last_page"] = page

        s, page = get("/rapports")
        assert "Compte de résultat" in page and "Marge par véhicule" in page, "rapports"
        s, page = get("/rapports/fiscal?mois=2025-04")
        assert "Rapport fiscal" in page and "TAVT estimé" in page, "fiscal"
        s, page = get("/export")
        assert "sauvegarde-compta" not in page and "backup.json" in page, "page export"
        globals()["_last_page"] = page

        s, page = get("/export/vehicules.csv")
        assert "Mazda" in page and ";" in page, "csv vehicules"
        s, page = get("/export/ventes.csv")
        assert "TAVT" in page, "csv ventes taxes"
        s, page = get("/export/backup.json")
        data = json.loads(page)
        assert any(v.get("marque") == "Mazda" for v in data["vehicules"]), "backup json"

        s, page = post("/import", raw=page)
        assert s == 200 and json.loads(page)["ok"] is True, f"import json: {s} {page[:300]}"
        globals()["_last_page"] = page

        s, page = get("/parametres")
        assert "taux_tavt" in page, "parametres admin"
        s, page = post("/utilisateurs", {"nom": "papa", "mdp": "motdepasse456", "role": "membre", "csrf": re.search(r'name="csrf" value="([^"]+)"', page).group(1)})
        assert "papa" in page, "creation compte famille"
        s, page = get("/utilisateurs")
        assert "papa" in page and "membre" in page, "liste comptes"
        s, page = get("/audit")
        assert "vente_vehicule" in page, "journal"

        s, page = post("/logout", {"csrf": re.search(r'name="csrf" value="([^"]+)"', page).group(1)})
        assert "Connexion" in page, "logout"

        print("SMOKE TEST OK")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
