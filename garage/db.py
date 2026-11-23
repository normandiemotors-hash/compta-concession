"""Schema SQLite et helpers d'acces a la base."""
import os
import sqlite3

from .taxes import DEFAULT_PARAMS

SCHEMA = """
CREATE TABLE IF NOT EXISTS utilisateurs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nom_utilisateur TEXT NOT NULL UNIQUE,
  hash_mdp TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'membre' CHECK (role IN ('admin','membre')),
  cree_le TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sessions (
  hash_token TEXT PRIMARY KEY,
  utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
  csrf TEXT NOT NULL,
  cree_le TEXT NOT NULL DEFAULT (datetime('now')),
  expire_le TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vehicules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vin TEXT UNIQUE,
  annee INTEGER,
  marque TEXT NOT NULL,
  modele TEXT NOT NULL,
  kilometrage INTEGER,
  carburant TEXT,
  date_achat TEXT NOT NULL,
  prix_achat REAL NOT NULL DEFAULT 0,
  vendeur TEXT,
  statut TEXT NOT NULL DEFAULT 'en_stock' CHECK (statut IN ('en_stock','vendu')),
  date_vente TEXT,
  prix_vente REAL,
  acheteur TEXT,
  mode_paiement TEXT,
  accessoires_ht REAL NOT NULL DEFAULT 0,
  valeur_marche REAL,
  notes TEXT,
  cree_par INTEGER REFERENCES utilisateurs(id),
  cree_le TEXT NOT NULL DEFAULT (datetime('now')),
  modifie_par INTEGER REFERENCES utilisateurs(id),
  modifie_le TEXT
);
CREATE TABLE IF NOT EXISTS couts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vehicule_id INTEGER NOT NULL REFERENCES vehicules(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  categorie TEXT NOT NULL,
  description TEXT,
  montant REAL NOT NULL DEFAULT 0,
  cree_par INTEGER REFERENCES utilisateurs(id),
  cree_le TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS depenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  categorie TEXT NOT NULL,
  description TEXT,
  montant REAL NOT NULL DEFAULT 0,
  cree_par INTEGER REFERENCES utilisateurs(id),
  cree_le TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS parametres (
  cle TEXT PRIMARY KEY,
  valeur TEXT NOT NULL,
  description TEXT,
  modifie_le TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  utilisateur_id INTEGER REFERENCES utilisateurs(id),
  action TEXT NOT NULL,
  table_cible TEXT,
  id_cible INTEGER,
  detail TEXT,
  date TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_vehicules_statut ON vehicules(statut);
CREATE INDEX IF NOT EXISTS idx_vehicules_date_vente ON vehicules(date_vente);
CREATE INDEX IF NOT EXISTS idx_couts_vehicule ON couts(vehicule_id);
CREATE INDEX IF NOT EXISTS idx_depenses_date ON depenses(date);
CREATE INDEX IF NOT EXISTS idx_audit_id ON audit(id DESC);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        for cle, valeur, description in DEFAULT_PARAMS:
            conn.execute(
                "INSERT OR IGNORE INTO parametres(cle, valeur, description) VALUES (?,?,?)",
                (cle, valeur, description),
            )
        conn.commit()
    finally:
        conn.close()


def audit(conn, utilisateur_id, action, table_cible=None, id_cible=None, detail=None):
    conn.execute(
        "INSERT INTO audit(utilisateur_id, action, table_cible, id_cible, detail) VALUES (?,?,?,?,?)",
        (utilisateur_id, action, table_cible, id_cible, detail),
    )
    conn.commit()


def seed_demo(conn):
    if conn.execute("SELECT COUNT(*) n FROM vehicules").fetchone()["n"]:
        return
    vehicules = [
        ("1HGCM82633A004352", 2015, "Honda", "Accord", 98500, "Essence", "2025-01-10", 8500.0, "Encheres Manheim", "vendu",
         "2025-02-14", 12900.0, "J. Smith", "Comptant", 350.0, None, "RAS"),
        (None, 2018, "Toyota", "Camry", 76200, "Essence", "2025-02-02", 10900.0, "Particulier", "en_stock",
         None, None, None, None, 0.0, None, "Bon etat geral"),
        (None, 2016, "Ford", "F-150", 88400, "Essence", "2025-03-05", 15700.0, "Encheres", "en_stock",
         None, None, None, None, 0.0, None, "Prevoir pneus"),
    ]
    for v in vehicules:
        conn.execute(
            """INSERT INTO vehicules(vin, annee, marque, modele, kilometrage, carburant, date_achat, prix_achat,
               vendeur, statut, date_vente, prix_vente, acheteur, mode_paiement, accessoires_ht, valeur_marche, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            v,
        )
    couts = [
        (1, "2025-01-11", "Transport", "Transport depuis Manheim GA", 450.0),
        (1, "2025-01-20", "Reconditionnement", "Detailing complet", 800.0),
        (3, "2025-03-08", "Reparations", "Pneus neufs (estime)", 620.0),
    ]
    for c in couts:
        conn.execute(
            "INSERT INTO couts(vehicule_id, date, categorie, description, montant) VALUES (?,?,?,?,?)", c
        )
    depenses = [
        ("2025-03-01", "Loyer", "Loyer du local Dacula GA", 2500.0),
        ("2025-03-01", "Assurance", "Assurance garage (mensuelle)", 480.0),
        ("2025-03-05", "Publicite", "Facebook Marketplace / Craigslist", 300.0),
        ("2025-03-10", "Licence concessionnaire", "Renouvellement licence dealer Georgie", 350.0),
    ]
    for d in depenses:
        conn.execute(
            "INSERT INTO depenses(date, categorie, description, montant) VALUES (?,?,?,?)", d
        )
    conn.commit()
