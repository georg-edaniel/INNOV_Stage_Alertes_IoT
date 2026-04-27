# Système d'Alertes Intelligentes — Données IoT Simulées
**Stage INNOV / CCNB — Fabrication Avancée, Bathurst (N.-B.)**
**Période : 1er mai 2026 → 16 juin 2026**
**Stagiaire : Philip Daniel George Moumie Gouet**

---

## Objectif

Développer un système d'alertes intelligent capable d'identifier automatiquement des situations anormales à partir de données IoT simulées (température, turbidité, pH).

---

## Stack technique

| Couche | Technologie |
|---|---|
| Backend API | FastAPI + Python 3.11 |
| Base de données | SQLite (dev) → PostgreSQL (prod) |
| ORM | SQLAlchemy |
| Simulateur IoT | Python + NumPy + APScheduler |
| Détection anomalies | NumPy / Pandas / scikit-learn |
| Dashboard | Jinja2 + Chart.js |
| MQTT (optionnel) | Mosquitto + Paho-MQTT |

---

## Structure du projet

```
INNOV_Stage_Alertes_IoT/
├── src/
│   ├── simulator/      # Générateur de données IoT simulées
│   ├── detection/      # Algorithmes de détection d'anomalies
│   ├── alerts/         # Module de gestion des alertes
│   ├── api/            # FastAPI — endpoints REST
│   └── dashboard/      # Interface de visualisation
├── tests/              # Tests unitaires et d'intégration
├── docs/               # Documentation technique
├── data/               # Données simulées exportées
├── journal_de_bord.docx  # Journal quotidien de progression
├── update_journal.py   # Script mise à jour journal + git push
└── requirements.txt
```

---

## Lancer le projet

```bash
pip install -r requirements.txt
uvicorn src.api.main:app --reload
```

---

## Journal de bord

Mis à jour chaque jour via :
```bash
python update_journal.py
```

→ Met à jour `journal_de_bord.docx` et pousse automatiquement sur GitHub.

---

## Avancement

| Semaine | Objectif |
|---|---|
| S1 | Générateur de données simulées |
| S2 | Algorithmes de détection d'anomalies |
| S3 | Module d'alertes (niveaux) |
| S4 | Dashboard + historique |
| S5 | Intégration complète + tests |
| S6 | Documentation + présentation finale |
