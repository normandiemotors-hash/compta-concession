#!/usr/bin/env python3
"""Point d'entree : lancer la comptabilite de la concession.

Usage :
    python3 app.py                 # http://127.0.0.1:8000 (cet ordinateur uniquement)
    python3 app.py --host 0.0.0.0  # accessible depuis le reseau local (famille)
    python3 app.py --demo          # charge des donnees de demonstration
"""
import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from garage import db, server, views  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Comptabilite de concession automobile (Dacula, Georgie, USA)")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'ecoute (127.0.0.1 par defaut, 0.0.0.0 pour le reseau local)")
    parser.add_argument("--port", type=int, default=8000, help="Port (8000 par defaut)")
    parser.add_argument("--data", default=os.path.join(BASE_DIR, "data"), help="Dossier contenant la base garage.db")
    parser.add_argument("--demo", action="store_true", help="Charger des donnees de demonstration si la base est vide")
    args = parser.parse_args()

    os.makedirs(args.data, exist_ok=True)
    db_path = os.path.join(args.data, "garage.db")
    db.init_db(db_path)
    if args.demo:
        conn = db.connect(db_path)
        try:
            db.seed_demo(conn)
        finally:
            conn.close()

    ctx = server.make_context(db_path, os.path.join(BASE_DIR, "garage", "static"))
    views.register(ctx.router, ctx)
    httpd = server.run(ctx, args.host, args.port)

    if args.host in ("0.0.0.0", "::"):
        import socket
        try:
            ip = socket.gethostbyname(socket.gethostname())
            print(f"  -> aussi accessible sur votre reseau local : http://{ip}:{args.port}")
        except OSError:
            pass
        print("  -> ATTENTION : n'exposez ceci que sur un reseau domestique de confiance (HTTP, pas de HTTPS).")
    print(f"Comptabilite prete sur http://{args.host}:{args.port}  (Ctrl+C pour arreter)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArret. Vos donnees sont dans :", db_path)


if __name__ == "__main__":
    main()
