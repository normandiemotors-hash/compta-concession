# Compta Concession — Normandie Motors (Dacula, Géorgie, USA)

Logiciel de comptabilité pour un **vendeur de voitures d'occasion** : suivi des **achats et reventes** de véhicules (avec tous les coûts associés), **dépenses** de la concession, **taxes estimées** (Géorgie), rapports de marge, et **sauvegardes/transferts faciles** pour travailler en famille.

- **100 % local et autonome** : aucune dépendance à installer, aucune connexion Internet requise. Fonctionne sur Windows, macOS et Linux avec Python 3.8+ (inclus sur la plupart des ordinateurs ; sinon à télécharger gratuitement sur python.org).
- **Multi-utilisateurs** : un compte par membre de la famille, avec rôles (`admin` / `membre`) et journal d'activité (qui a fait quoi, quand).
- **Transférable facilement** : les données tiennent dans **un seul fichier** (`data/garage.db`) — copiez-le sur une clé USB, un autre ordinateur ou le cloud. Export JSON/CSV intégré en plus.

> ⚠️ **Avertissement fiscal** : les calculs de taxes (TAVT Géorgie, sales tax État + comté de Gwinnett) sont des **estimations basées sur des taux configurables**. Les règles fiscales changent et dépendent de votre situation (licence de concessionnaire, inventaire, véhicules de démonstration, etc.). **Faites valider les taux et les règles par un comptable (CPA) en Géorgie avant toute déclaration.** Ce logiciel n'est pas un conseil fiscal ou juridique.

## Votre logo

Le logo **Normandie Motors LLC** fourni est déjà intégré : il s'affiche dans l'en-tête de chaque page et sert de favicon du navigateur (`garage/static/logo.png`, copie originale dans `assets/logo-original.png`).

Pour le remplacer : mettez votre image (PNG recommandé) à la place de **`garage/static/logo.png`** — aucune autre modification nécessaire. Si le fichier est absent, l'application revient à un en-tête texte seul.

## Installation et lancement

Prérequis : **Python 3.8 ou plus** (`python3 --version` pour vérifier).

- **Windows** : double-clic sur `lancer.bat` (ou `python app.py` dans un terminal).
- **macOS** : double-clic sur `lancer.command` (ou `./lancer.sh` dans le Terminal).
- **Linux** : `./lancer.sh` ou `python3 app.py`.

Puis ouvrez votre navigateur à l'adresse indiquée (par défaut **http://127.0.0.1:8000**).

Au premier lancement, créez le **compte administrateur** (page « Premier démarrage »), puis connectez-vous. Depuis « Comptes famille », l'admin crée un compte pour chaque membre de la famille.

Options utiles :

```bash
python3 app.py                 # cet ordinateur uniquement (sécurisé, par défaut)
python3 app.py --host 0.0.0.0  # visible depuis les autres appareils du réseau local
python3 app.py --port 8080     # changer le port
python3 app.py --demo          # données de démonstration (si la base est vide)
```

> 🔒 Si vous utilisez `--host 0.0.0.0` pour que la famille se connecte depuis d'autres appareils (téléphones, autres PC de la maison), **n'activez cette option que sur votre réseau domestique de confiance** : l'application fonctionne en HTTP (pas de HTTPS) et n'est pas conçue pour être exposée sur Internet. Utilisez des mots de passe forts (8 caractères minimum imposés). Pour un accès à distance, passez plutôt par un VPN domestique.

## Utilisation

- **Véhicules** : enregistrement de l'achat (VIN, année, marque, modèle, kilométrage, prix, vendeur, date), ajout de **coûts** (transport, reconditionnement, réparations, pièces...), puis **revente** (date, prix, acheteur, mode de paiement, accessoires vendus). La fiche calcule le **coût total** et la **marge**. Un véhicule vendu peut être remis en stock par un admin.
- **Dépenses** : loyer, assurance, publicité, salaires, licence de concessionnaire, etc., avec filtre par mois.
- **Rapports** : compte de résultat sur 12 mois (CA, coût des véhicules vendus, marge brute, dépenses, marge nette), marge par véhicule, **rapport fiscal mensuel** (sales tax collectée sur accessoires + TAVT estimé sur les ventes), stock vieillissant (≥ 60 jours) sur le tableau de bord.
- **Export & sauvegarde** : CSV (s'ouvre dans Excel) pour véhicules, coûts, dépenses, ventes+taxes, et **sauvegarde complète JSON** (restaurable via « Importer », admin uniquement).

## Transférer l'application (famille, nouvel ordinateur)

Trois méthodes, au choix :

1. **Copier tout le dossier** de l'application (clé USB, disque externe, cloud) sur le nouvel ordinateur, puis lancer `app.py`.
2. **Copier uniquement `data/garage.db`** (toutes les données : véhicules, dépenses, comptes, paramètres) dans le dossier `data/` du nouvel ordinateur.
3. **Export JSON** ici, puis **Import JSON** sur l'autre machine (remplace véhicules/coûts/dépenses/paramètres ; les comptes utilisateurs sont conservés).

## Taxes (Géorgie, USA) — ce que calcule le logiciel

| Élément | Règle implémentée (taux configurables dans « Paramètres ») |
|---|---|
| Prix du véhicule vendu | **TAVT** (Title Ad Valorem Tax) : taux × base = max(prix de vente, valeur marché si renseignée). En Géorgie, le TAVT **remplace** la sales tax sur le véhicule ; il est en général payé par l'acheteur à l'immatriculation. Taux par défaut 7 % (6,6 % jusqu'en 2024) — **à vérifier**. |
| Accessoires vendus séparément (pièces, garantie, réparations) | **Sales tax** État de Géorgie 4 % + taxe locale (Gwinnett/Dacula, 2 % par défaut) = montant collecté à reverser. |
| Achats par la concession, inventaire, licence dealer | Non calculés automatiquement — **à confirmer avec un CPA** (exemptions, taxe ad valorem sur l'inventaire, etc.). |

## Sécurité

- Mots de passe hachés (PBKDF2-SHA256, 600 000 itérations, sel aléatoire), jamais stockés en clair.
- Sessions à jeton aléatoire (cookie `HttpOnly`, `SameSite=Lax`), expiration 7 jours.
- Protection CSRF sur tous les formulaires, échappement HTML systématique (anti-XSS), requêtes SQL paramétrées (anti-injection), en-têtes de sécurité HTTP (CSP, `nosniff`, `X-Frame-Options`).
- Rôles : `membre` = ajout/modification ; `admin` = suppressions, paramètres, comptes, import. Journal d'audit de toutes les actions.

## Structure du projet

```
compta-concession/
├── app.py                  # point d'entrée (lancer l'application)
├── garage/
│   ├── server.py           # serveur HTTP (bibliothèque standard)
│   ├── web.py              # requêtes/réponses/routeur
│   ├── db.py               # schéma SQLite + données de démo
│   ├── security.py         # mots de passe, sessions, CSRF
│   ├── taxes.py            # moteur de taxes (taux configurables Géorgie)
│   ├── reports.py          # tableaux de bord, P&L, rapport fiscal
│   ├── pages_core.py       # connexion, tableau de bord, liste véhicules
│   ├── pages_vehicules.py  # fiche véhicule, coûts, vente
│   ├── pages_reports.py    # dépenses, rapports, exports/import
│   ├── pages_admin.py      # paramètres, comptes, journal
│   ├── util.py             # rendu HTML
│   └── static/             # CSS + JS
├── tests/smoke_test.py     # test de fumée automatisé
├── assets/logo-original.png  # logo fourni en pleine résolution
├── data/                   # créé au lancement : garage.db (VOS DONNÉES)
├── lancer.bat / .command / .sh
└── README.md
```

## Tests

```bash
python3 tests/smoke_test.py
```

Démarre le serveur sur `127.0.0.1` avec une base temporaire et enchaîne : création du compte admin, ajout de véhicule, coût, vente, dépense, rapports, exports CSV/JSON, import, création de compte famille, journal, déconnexion.

## Sauvegarde régulière recommandée

1. Fermez l'application (ou laissez-la tourner, le fichier WAL est cohérent).
2. Copiez `data/garage.db` (et éventuellement `garage.db-wal` / `garage.db-shm` s'ils existent) vers un emplacement sûr, ou utilisez **Export & sauvegarde → Sauvegarde complète JSON**.
