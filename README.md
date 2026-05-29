# IoT Alert System — INNOV/CCNB 2026

**Stage INNOV / CCNB — Fabrication Avancée, Bathurst (N.-B.)**
**Période : 1er mai 2026 → 16 juin 2026**
**Stagiaire : Philip Daniel George Moumie Gouet**

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi)
![scikit-learn](https://img.shields.io/badge/scikit--learn-Isolation%20Forest-orange?logo=scikit-learn)
![SQLite](https://img.shields.io/badge/SQLite-Database-lightgrey?logo=sqlite)

Système d'alertes IoT temps réel avec **5 détecteurs d'anomalies** (règles métier, Z-Score, IQR, Isolation Forest univarié et multivarié), tableau de bord web, SSE temps réel, export PDF/Excel/CSV, audit complet et prédiction de dérive.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────────────┐
│  IoTSimulator   │────▶│          AnomalyDetectionEngine                  │
│  (seed, prob)   │     │  RulesBased │ ZScore │ IQR │ IF │ MV-IF          │
└─────────────────┘     └──────────────────────┬───────────────────────────┘
                                                ▼
                                     AlertService (SQLite)
                                      CRUD · Stats · MTTR
                                      Heatmap · Corrélation
                                      Audit · Archivage
                                                ▼
                            ┌───────────────────────────────┐
                            │   FastAPI REST API + Jinja2   │
                            │  /alerts /report /predict     │
                            │  /config /audit /archived     │
                            └───────────────┬───────────────┘
                                            ▼
                               Browser (Chart.js, SSE, jsPDF)
```

**Flux de données :**
1. `IoTSimulator` génère des lectures capteurs toutes les 5 secondes (APScheduler)
2. `AnomalyDetectionEngine` applique les 5 détecteurs en parallèle (stratégie worst-case)
3. `AlertService` persiste les alertes en SQLite et calcule les statistiques
4. Le frontend reçoit les mises à jour en temps réel via **Server-Sent Events (SSE)**

---

## Installation

```bash
# Cloner le projet
git clone <url-du-repo>
cd INNOV_Stage_Alertes_IoT

# Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# Installer les dépendances
pip install -r requirements.txt
```

## Lancement

```bash
uvicorn src.api.main:app --reload --port 8084
```

Accéder à : **http://localhost:8084**

Identifiants par défaut : `admin` / `admin` (authentification désactivée par défaut)

---

## Pages disponibles

| URL | Description |
|-----|-------------|
| `/` | Dashboard principal — KPIs, jauges, alertes récentes |
| `/alerts` | Historique des alertes avec filtres avancés et export |
| `/logs` | Lectures capteurs brutes + graphique time-series |
| `/logs/compare` | Comparaison données brutes vs nettoyées |
| `/report` | Rapport agrégé — MTTR, heatmap, corrélation |
| `/report/detection` | Évaluation quantitative des détecteurs (P/R/F1, bootstrap CI, sensibilité) |
| `/predict` | Prédiction de dérive par régression linéaire (projection 20 lectures) |
| `/config` | Seuils dynamiques par capteur et zone |
| `/params` | Paramètres unifiés — seuils, webhook, email, sécurité |
| `/audit` | Journal d'audit des actions opérateur |
| `/archived` | Alertes archivées (résolues > 30 jours) |
| `/map` | Carte géographique des capteurs (Leaflet.js) |
| `/presentation` | Mode présentation mural plein écran |
| `/docs` | Documentation interactive Swagger UI |

---

## Détecteurs d'anomalies

| Détecteur | Méthode | Hyperparamètres | Justification |
|-----------|---------|-----------------|---------------|
| **Règles métier** | Seuils fixes | `warning`/`critical` par capteur | Normes WHO/OMS eau potable — précision maximale sur violations connues |
| **Z-Score** | Écart-type sur fenêtre glissante | `window=30`, `z_warn=2`, `z_crit=3` | Fenêtre 30 : équilibre réactivité/stabilité · Seuils z=2/3 : règle 68-95-99.7 |
| **IQR** | Intervalle interquartile | `window=30`, `k_warn=1.5`, `k_crit=3.0` | Robuste aux valeurs extrêmes · k=1.5 = règle de Tukey standard |
| **Isolation Forest** | Arbres d'isolation (scikit-learn) | `window=100`, `contamination=0.05`, `retrain_every=20` | 100 estimateurs pour stabilité · contamination=5% = taux IoT observé · Persisté sur disque (`if_model.pkl`) |
| **MV-Isolation Forest** | IF multivarié (temp + turbidité + pH) | `window=100`, `min_samples=30`, `contamination=0.05` | Détecte les corrélations anormales entre capteurs que les détecteurs univariés manquent |

**Stratégie** : worst-case — le niveau le plus sévère parmi les 5 détecteurs est retenu, maximisant le rappel.

---

## Évaluation rigoureuse (`/report/detection`)

- **Train/test split** : 200 lectures warmup (calibration) + 400 lectures test (évaluation)
- **Bootstrap CI** : 10 seeds différents → métriques affichées sous forme `mean ± std`
- **Analyse de sensibilité** : F1 en fonction de `window_size` ∈ {10, 20, 30, 50, 100}

---

## Lancer les tests

```bash
pytest tests/ -v
```

Les tests couvrent : génération IoT, détecteurs statistiques (Z-Score, IQR, Isolation Forest, MV-IF), règles métier, moteur de détection, service d'alertes.

---

## Structure du projet

```
src/
├── api/
│   ├── main.py          # Point d'entrée FastAPI, lifespan, persistance IF
│   ├── dashboard.py     # Routes HTML (Jinja2)
│   ├── routers.py       # Endpoints REST
│   ├── auth.py          # Authentification cookie de session
│   └── stream.py        # SSE temps réel
├── alerts/
│   ├── models.py        # ORM SQLAlchemy (Alert, SensorLog, AuditLog, ArchivedAlert)
│   └── service.py       # AlertService — CRUD, stats, heatmap, corrélation, audit
├── detection/
│   ├── engine.py        # AnomalyDetectionEngine (5 détecteurs)
│   ├── rules.py         # RuleBasedDetector
│   ├── statistical.py   # ZScore, IQR, IsolationForest, MultivariateIsolationForest
│   └── levels.py        # AlertLevel, DetectionResult
├── simulator/
│   ├── generator.py     # IoTSimulator
│   ├── scheduler.py     # APScheduler background
│   └── config.py        # SENSOR_CONFIG (seuils, baseline, noise)
└── dashboard/
    ├── templates/       # Jinja2 HTML (16 pages)
    └── static/          # CSS, JS, images
```

---

## Fichiers de persistance

| Fichier | Contenu |
|---------|---------|
| `alerts.db` | Base SQLite principale |
| `if_model.pkl` | Modèle Isolation Forest sérialisé (joblib) — rechargé au démarrage |
| `thresholds_override.json` | Seuils personnalisés par capteur/zone |
| `email_config.json` | Configuration SMTP |
| `webhook_config.json` | Configuration webhook (Slack/Discord) |
| `auth_config.json` | Authentification (activée, hash mot de passe) |

---

## Avancement

| Semaine | Objectif | Statut |
|---------|----------|--------|
| S1 | Générateur de données simulées | ✅ |
| S2 | Algorithmes de détection d'anomalies | ✅ |
| S3 | Module d'alertes (niveaux, filtres, export) | ✅ |
| S4 | Dashboard + SSE + rapport + config | ✅ |
| S5 | ML avancé (IF, MV-IF, persistance, prédiction) | ✅ |
| S6 | Évaluation rigoureuse + documentation finale | ✅ |
