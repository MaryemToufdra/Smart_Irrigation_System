readme.md# 🌱 Smart Irrigation System

## Lancement rapide

## Lancement

pip install flask
python web/app/projet.py

Ouvrir : http://localhost:5000

## Fonctionnalités

- Dashboard temps réel (humidité, température, 4 zones)
- Graphiques historiques (1h, 6h, 24h, 7j)
- Statistiques journalières
- Alertes actives / résolues
- Journal des irrigations
- Déclenchement manuel d'irrigation
- Simulation IA (prédictions d'irrigation)
- Simulation capteurs en temps réel (toutes les 30s)
## API Endpoints

| Route                          | Description                      |
| ------------------------------ | -------------------------------- |
| GET /api/dashboard             | KPIs + état de tous les capteurs |
| GET /api/history/<id>?hours=24 | Historique d'un capteur          |
| GET /api/stats                 | Statistiques 7 jours             |
| GET /api/alerts?resolved=0     | Liste des alertes                |
| POST /api/alerts/resolve/<id>  | Résoudre une alerte              |
| GET /api/irrigations           | Journal irrigations              |
| POST /api/irrigate             | Démarrer une irrigation          |
| GET /api/live                  | Dernière lecture temps réel      |

# Smart Irrigation System

## Equipe

- Personne 1 : Systèmes Embarqués (branche `embarque`)
- Personne 2 : Développement Web (branche `web`)
- Personne 3 : Data & IA (branche `data-ia`)

## Données
Les données se trouvent dans Data/data.json
