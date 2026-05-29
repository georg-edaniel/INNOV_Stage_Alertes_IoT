"""
dashboard.py
------------
Routes HTML du dashboard (pages rendues côté serveur avec Jinja2).
"""

from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..alerts.database import get_db
from ..alerts.service import AlertService
from ..i18n import make_jinja_context

TEMPLATES_DIR = Path(__file__).parent.parent / "dashboard" / "templates"
templates     = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Ajouter la traduction comme filtre et global Jinja2
from ..i18n import translate as _translate

def _jinja_translate(key: str, lang: str = "fr") -> str:
    return _translate(key, lang)

templates.env.globals["_"]         = _jinja_translate
templates.env.globals["translate"] = _jinja_translate

dashboard_router = APIRouter()

PER_PAGE      = 20   # alertes par page
LOGS_PER_PAGE = 15   # lectures par page


def _ctx(request: Request, **kwargs) -> dict:
    """Crée le contexte Jinja2 de base avec i18n."""
    ctx = make_jinja_context(request)
    ctx.update(kwargs)
    return ctx


@dashboard_router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Page principale du dashboard."""
    svc    = AlertService(db)
    stats  = svc.get_stats()
    open_c = svc.get_open_count()
    recent = svc.get_all(resolved=False, limit=10)
    mttr   = svc.get_mttr()
    health = svc.get_sensor_health()
    last_t = svc.get_last_alert_time()
    return templates.TemplateResponse(request, "dashboard.html", _ctx(request,
        stats=stats,
        open=open_c,
        recent_alerts=[a.to_dict() for a in recent],
        mttr=mttr,
        health=health,
        last_alert_at=last_t,
    ))


@dashboard_router.get("/alerts", response_class=HTMLResponse)
def alerts_page(
    request:   Request,
    sensor:    str | None = None,
    level:     str | None = None,
    resolved:  str | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
    q:         str | None = None,
    page:      int = 1,
    db: Session = Depends(get_db),
):
    """Page historique des alertes avec filtres et pagination."""
    from datetime import datetime, timezone, timedelta
    sensor_f   = sensor or None
    level_f    = level  or None
    resolved_f: bool | None = None
    if resolved == "true":
        resolved_f = True
    elif resolved == "false":
        resolved_f = False

    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None

    page   = max(1, page)
    offset = (page - 1) * PER_PAGE

    svc    = AlertService(db)
    alerts = svc.get_all(
        sensor=sensor_f, level=level_f, resolved=resolved_f,
        date_from=df, date_to=dt, search=q,
        limit=PER_PAGE, offset=offset,
    )
    total = svc.count_all(sensor=sensor_f, level=level_f, resolved=resolved_f, date_from=df, date_to=dt, search=q)
    stats  = svc.get_stats()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    return templates.TemplateResponse(request, "alerts.html", {
        "alerts":      [a.to_dict() for a in alerts],
        "stats":       stats,
        "filters":     {
            "sensor": sensor_f, "level": level_f, "resolved": resolved_f,
            "date_from": date_from, "date_to": date_to, "q": q,
        },
        "page":        page,
        "total_pages": total_pages,
        "total":       total,
        "per_page":    PER_PAGE,
        "has_prev":    page > 1,
        "has_next":    page < total_pages,
    })


@dashboard_router.get("/alerts/{alert_id}", response_class=HTMLResponse)
def alert_detail(alert_id: int, request: Request, db: Session = Depends(get_db)):
    """Page de détail d'une alerte."""
    svc   = AlertService(db)
    alert = svc.get_by_id(alert_id)
    if not alert:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    logs = svc.get_logs(sensor=alert.sensor, limit=50)
    return templates.TemplateResponse(request, "alert_detail.html", {
        "alert": alert.to_dict(),
        "logs":  [l.to_dict() for l in logs],
    })


@dashboard_router.get("/logs", response_class=HTMLResponse)
def logs_page(
    request:   Request,
    sensor:    str | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
    page:      int = 1,
    db: Session = Depends(get_db),
):
    """Page historique des lectures capteurs + graphiques (15 par page)."""
    from datetime import datetime, timezone, timedelta
    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None

    page   = max(1, page)
    offset = (page - 1) * LOGS_PER_PAGE

    svc   = AlertService(db)
    logs  = svc.get_logs(sensor=sensor or None, date_from=df, date_to=dt, limit=LOGS_PER_PAGE, offset=offset)
    total = svc.count_logs(sensor=sensor or None, date_from=df, date_to=dt)
    total_pages = max(1, (total + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE)

    # Données graphique : 60 dernières lectures pour le chart (indépendant de la page)
    chart_logs = svc.get_logs(sensor=sensor or None, date_from=df, date_to=dt, limit=60)

    return templates.TemplateResponse(request, "logs.html", {
        "logs":        [l.to_dict() for l in logs],
        "chart_logs":  [l.to_dict() for l in chart_logs],
        "sensor":      sensor,
        "date_from":   date_from,
        "date_to":     date_to,
        "page":        page,
        "total_pages": total_pages,
        "total":       total,
        "has_prev":    page > 1,
        "has_next":    page < total_pages,
        "per_page":    LOGS_PER_PAGE,
    })


@dashboard_router.get("/logs/compare", response_class=HTMLResponse)
def logs_compare_page(request: Request, db: Session = Depends(get_db)):
    """Page de comparaison données complètes vs nettoyées."""
    svc     = AlertService(db)
    sensors = ["temperature", "turbidity", "ph"]

    stats = []
    for s in sensors:
        total    = svc.count_logs(sensor=s, exclude_outliers=False)
        clean    = svc.count_logs(sensor=s, exclude_outliers=True)
        aberrant = total - clean
        pct      = round(aberrant / total * 100, 1) if total else 0
        stats.append({"sensor": s, "total": total, "clean": clean,
                      "aberrant": aberrant, "pct": pct})

    total_all    = sum(s["total"]    for s in stats)
    clean_all    = sum(s["clean"]    for s in stats)
    aberrant_all = sum(s["aberrant"] for s in stats)
    pct_all      = round(aberrant_all / total_all * 100, 1) if total_all else 0

    return templates.TemplateResponse(request, "logs_compare.html", {
        "stats":        stats,
        "total_all":    total_all,
        "clean_all":    clean_all,
        "aberrant_all": aberrant_all,
        "pct_all":      pct_all,
    })


@dashboard_router.get("/report", response_class=HTMLResponse)
def report_page(
    request: Request,
    days: int = 1,
    db: Session = Depends(get_db),
):
    """Page de rapport agrégé (dernières N journées)."""
    svc    = AlertService(db)
    report = svc.get_report_data(days=max(1, min(days, 30)))
    return templates.TemplateResponse(request, "report.html", {
        "report": report,
        "days":   days,
    })


@dashboard_router.get("/report/detection", response_class=HTMLResponse)
def detection_eval_page(request: Request):
    """Évaluation quantitative : Precision / Recall / F1, bootstrap CI (10 seeds), analyse sensibilité."""
    import numpy as np
    from ..simulator.generator import IoTSimulator
    from ..detection.rules import RuleBasedDetector
    from ..detection.statistical import ZScoreDetector, IQRDetector, IsolationForestDetector

    WARMUP      = 200
    TEST        = 400
    N_SEEDS     = 10
    WINDOW_SIZES = [10, 20, 30, 50, 100]

    LABELS = {
        "rules":            "Règles métier",
        "zscore":           "Z-Score",
        "iqr":              "IQR",
        "isolation_forest": "Isolation Forest",
    }

    def _make_detectors(ws: int):
        return {
            "rules":            RuleBasedDetector(),
            "zscore":           ZScoreDetector(window_size=ws),
            "iqr":              IQRDetector(window_size=ws),
            "isolation_forest": IsolationForestDetector(window_size=max(ws * 3, 100), min_samples=20),
        }

    def _run_one(seed: int, window_size: int = 30) -> dict:
        """200 warmup (calibration) + 400 test → métriques par détecteur."""
        sim = IoTSimulator(seed=seed)
        total_needed = WARMUP + TEST
        readings: list = []
        while len(readings) < total_needed:
            readings.extend(sim.read_all())
        readings = readings[:total_needed]

        dets = _make_detectors(window_size)

        # Phase warmup : calibrer sans évaluer
        for r in readings[:WARMUP]:
            for det in dets.values():
                det.analyze(r)

        # Phase test : évaluer
        results = {}
        for name, det in dets.items():
            tp = fp = fn = tn = 0
            for r in readings[WARMUP:]:
                true_anom = (r.scenario != "normal")
                pred_anom = det.analyze(r).is_anomaly()
                if   true_anom and pred_anom:     tp += 1
                elif not true_anom and pred_anom: fp += 1
                elif true_anom and not pred_anom: fn += 1
                else:                             tn += 1
            precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
            recall    = tp / (tp + fn) if (tp + fn) > 0 else 1.0
            f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            results[name] = {"precision": precision, "recall": recall, "f1": f1,
                              "tp": tp, "fp": fp, "fn": fn, "tn": tn}
        return results

    # ── Bootstrap : 10 seeds, window_size=30 ─────────────────────────────
    all_runs = [_run_one(seed=s, window_size=30) for s in range(N_SEEDS)]

    metrics = {}
    for name in LABELS:
        runs = [r[name] for r in all_runs]
        p_vals = [r["precision"] for r in runs]
        r_vals = [r["recall"]    for r in runs]
        f_vals = [r["f1"]        for r in runs]
        last   = runs[-1]
        metrics[name] = {
            "name":           LABELS[name],
            "key":            name,
            "precision_mean": round(float(np.mean(p_vals)), 3),
            "precision_std":  round(float(np.std(p_vals)),  3),
            "recall_mean":    round(float(np.mean(r_vals)), 3),
            "recall_std":     round(float(np.std(r_vals)),  3),
            "f1_mean":        round(float(np.mean(f_vals)), 3),
            "f1_std":         round(float(np.std(f_vals)),  3),
            "tp": last["tp"], "fp": last["fp"],
            "fn": last["fn"], "tn": last["tn"],
        }

    # ── Analyse de sensibilité : 5 tailles de fenêtre, seed=42 ───────────
    sensitivity = {"zscore": [], "iqr": []}
    for ws in WINDOW_SIZES:
        r = _run_one(seed=42, window_size=ws)
        sensitivity["zscore"].append(round(r["zscore"]["f1"],  3))
        sensitivity["iqr"].append(   round(r["iqr"]["f1"],     3))

    # Nombre de vraies anomalies dans la phase test (seed=42)
    sim42 = IoTSimulator(seed=42)
    readings42: list = []
    while len(readings42) < WARMUP + TEST:
        readings42.extend(sim42.read_all())
    true_anomalies = sum(1 for r in readings42[WARMUP:WARMUP + TEST] if r.scenario != "normal")

    return templates.TemplateResponse(request, "detection_eval.html", {
        "metrics":         metrics,
        "sensitivity":     sensitivity,
        "window_sizes":    WINDOW_SIZES,
        "total_readings":  TEST,
        "warmup_readings": WARMUP,
        "true_anomalies":  true_anomalies,
        "true_normals":    TEST - true_anomalies,
        "n_bootstrap":     N_SEEDS,
    })


@dashboard_router.get("/predict", response_class=HTMLResponse)
def predict_page(request: Request, db: Session = Depends(get_db)):
    """Prédiction de dérive — ARIMA si ≥15 valeurs, sinon régression linéaire."""
    import numpy as np
    from ..simulator.config import SENSOR_CONFIG

    svc = AlertService(db)
    predictions = {}
    for sensor in ["temperature", "turbidity", "ph"]:
        logs = svc.get_logs(sensor=sensor, limit=60)
        cfg  = SENSOR_CONFIG[sensor]
        if len(logs) < 5:
            predictions[sensor] = {"status": "insufficient", "unit": cfg["unit"]}
            continue

        values = [l.value for l in reversed(logs)]

        # Essai ARIMA si ≥15 valeurs
        forecast      = None
        conf_int_low  = None
        conf_int_high = None
        method_used   = "linear"

        if len(values) >= 15:
            try:
                from statsmodels.tsa.arima.model import ARIMA
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model     = ARIMA(values, order=(2, 1, 2)).fit()
                    fc_res    = model.get_forecast(20)
                    forecast  = fc_res.predicted_mean.tolist()
                    ci        = fc_res.conf_int(alpha=0.05)
                    conf_int_low  = ci.iloc[:, 0].tolist()
                    conf_int_high = ci.iloc[:, 1].tolist()
                    method_used = "arima"
                    # pente approximative basée sur les premiers/derniers points de la prévision
                    slope = (forecast[-1] - forecast[0]) / max(len(forecast) - 1, 1)
            except Exception:
                forecast = None

        if forecast is None:
            # Fallback régression linéaire
            x = np.arange(len(values), dtype=float)
            slope, intercept = np.polyfit(x, values, 1)
            future_x  = np.arange(len(values), len(values) + 20, dtype=float)
            forecast  = (slope * future_x + intercept).tolist()

        future_vals = [round(float(v), 3) for v in forecast]
        steps_warning = next(
            (i for i, v in enumerate(future_vals)
             if v > cfg["warning"]["max"] or v < cfg["warning"]["min"]),
            None,
        )
        steps_critical = next(
            (i for i, v in enumerate(future_vals)
             if v > cfg["critical"]["max"] or v < cfg["critical"]["min"]),
            None,
        )
        x2    = np.arange(len(values), dtype=float)
        slope_lin, _ = np.polyfit(x2, values, 1)
        actual_slope  = float(slope_lin)
        trend_icon = "↑" if actual_slope > 0.01 else ("↓" if actual_slope < -0.01 else "→")

        predictions[sensor] = {
            "status":         "ok",
            "values":         [round(float(v), 3) for v in values[-20:]],
            "future":         future_vals,
            "conf_int_low":   [round(float(v), 3) for v in conf_int_low]  if conf_int_low  else None,
            "conf_int_high":  [round(float(v), 3) for v in conf_int_high] if conf_int_high else None,
            "method":         method_used,
            "slope":          round(actual_slope, 4),
            "current":        round(float(values[-1]), 3),
            "trend_icon":     trend_icon,
            "steps_warning":  steps_warning,
            "steps_critical": steps_critical,
            "unit":           cfg["unit"],
            "thresholds":     cfg,
        }

        # Sauvegarder dans PredictionRecord
        try:
            import json as _json
            from ..alerts.models import PredictionRecord
            rec = PredictionRecord(
                sensor=sensor,
                method=method_used,
                horizon=20,
                values_json=_json.dumps(future_vals),
                conf_low_json=_json.dumps([round(float(v), 3) for v in conf_int_low]) if conf_int_low else None,
                conf_high_json=_json.dumps([round(float(v), 3) for v in conf_int_high]) if conf_int_high else None,
            )
            db.add(rec)
            db.commit()
        except Exception:
            pass

    # Récupérer l'historique des 10 dernières prédictions
    try:
        from ..alerts.models import PredictionRecord
        history = db.query(PredictionRecord).order_by(PredictionRecord.created_at.desc()).limit(10).all()
        history_data = [r.to_dict() for r in history]
    except Exception:
        history_data = []

    return templates.TemplateResponse(request, "predict.html", _ctx(request,
        predictions=predictions,
        history=history_data,
    ))


@dashboard_router.get("/spc", response_class=HTMLResponse)
def spc_page(request: Request, db: Session = Depends(get_db)):
    """Page SPC — graphiques de contrôle de Shewhart par capteur."""
    from ..detection.spc import ShewhartDetector
    from ..simulator.config import SENSOR_CONFIG

    svc      = AlertService(db)
    detector = ShewhartDetector(window_size=30)
    charts   = {}

    for sensor in ["temperature", "turbidity", "ph"]:
        logs = svc.get_logs(sensor=sensor, limit=60)
        if not logs:
            charts[sensor] = {"status": "no_data", "unit": SENSOR_CONFIG[sensor]["unit"]}
            continue
        from ..simulator.generator import SensorReading
        for log in reversed(logs):
            reading = SensorReading(sensor=log.sensor, value=log.value, scenario="spc_replay")
            detector.analyze(reading)
        data = detector.get_chart_data(sensor)
        data["unit"]   = SENSOR_CONFIG[sensor]["unit"]
        data["status"] = "ok"
        charts[sensor] = data

    return templates.TemplateResponse(request, "spc.html", {"charts": charts})


@dashboard_router.get("/timeline", response_class=HTMLResponse)
def timeline_page(
    request: Request,
    sensor:    str | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
    db: Session = Depends(get_db),
):
    """Page timeline chronologique des alertes (vue Gantt / scatter)."""
    from datetime import datetime, timezone, timedelta
    svc = AlertService(db)

    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None

    alerts = svc.get_all(
        sensor=sensor or None,
        date_from=df, date_to=dt,
        limit=200,
    )

    # Grouper par heure pour la vue densité
    from collections import defaultdict
    hourly: dict[str, dict] = defaultdict(lambda: {"CRITICAL": 0, "WARNING": 0, "NORMAL": 0})
    for a in alerts:
        ts = a.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hour_key = ts.strftime("%Y-%m-%dT%H:00")
        hourly[hour_key][a.level] = hourly[hour_key].get(a.level, 0) + 1

    hourly_list = sorted(
        [{"hour": k, **v} for k, v in hourly.items()],
        key=lambda x: x["hour"],
    )

    return templates.TemplateResponse(request, "timeline.html", {
        "alerts":      [a.to_dict() for a in alerts],
        "hourly":      hourly_list,
        "sensor":      sensor or "",
        "date_from":   date_from or "",
        "date_to":     date_to or "",
    })


@dashboard_router.get("/logs/overlay", response_class=HTMLResponse)
def logs_overlay_page(request: Request, db: Session = Depends(get_db)):
    """Page overlay — comparaison multi-capteurs normalisés (z-score) sur un même axe."""
    import numpy as np
    svc  = AlertService(db)
    data = {}
    for sensor in ["temperature", "turbidity", "ph"]:
        logs   = svc.get_logs(sensor=sensor, limit=60)
        values = [l.value for l in reversed(logs)]
        times  = [l.created_at.isoformat() for l in reversed(logs)]
        if len(values) >= 2:
            mean = float(np.mean(values))
            std  = float(np.std(values)) or 1.0
            zvals = [round((v - mean) / std, 3) for v in values]
        else:
            zvals = values
        data[sensor] = {"times": times, "values": zvals, "raw": [round(v, 3) for v in values]}
    return templates.TemplateResponse(request, "logs_overlay.html", {"data": data})


@dashboard_router.get("/cusum", response_class=HTMLResponse)
def cusum_page(request: Request, db: Session = Depends(get_db)):
    """Page CUSUM — visualisation des accumulateurs C+/C- par capteur."""
    from ..detection.cusum import CUSUMDetector
    cusum = CUSUMDetector(window_size=40, k_factor=0.5, h_factor=5.0)
    svc   = AlertService(db)

    chart_data = {}
    for sensor in ["temperature", "turbidity", "ph"]:
        logs = svc.get_logs(sensor=sensor, limit=200)
        for log in reversed(logs):
            from ..simulator.generator import SensorReading
            reading = SensorReading(sensor=log.sensor, value=log.value, scenario="cusum_replay")
            cusum.analyze(reading)
        chart_data[sensor] = cusum.get_chart_data(sensor)

    return templates.TemplateResponse(request, "cusum.html", {
        "data":   chart_data,
        "active": "cusum",
    })


@dashboard_router.get("/config", response_class=HTMLResponse)
def config_page(request: Request, db: Session = Depends(get_db)):
    """Page de configuration des seuils."""
    from ..alerts.threshold_config import get_all
    svc     = AlertService(db)
    windows = svc.get_maintenance_windows()
    return templates.TemplateResponse(request, "thresholds.html", {
        "thresholds": get_all(),
        "maintenance_windows": [w.to_dict() for w in windows],
    })


@dashboard_router.get("/audit", response_class=HTMLResponse)
def audit_page(
    request:   Request,
    action:    str | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
    page:      int = 1,
    db: Session = Depends(get_db),
):
    """Page journal d'audit des actions opérateur."""
    from datetime import datetime, timezone, timedelta
    PER = 30
    svc    = AlertService(db)
    page   = max(1, page)
    offset = (page - 1) * PER
    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None
    logs   = svc.get_audit_log(action=action or None, date_from=df, date_to=dt, limit=PER, offset=offset)
    total  = svc.count_audit_log(action=action or None, date_from=df, date_to=dt)
    total_pages = max(1, (total + PER - 1) // PER)
    return templates.TemplateResponse(request, "audit.html", {
        "logs":        [l.to_dict() for l in logs],
        "page":        page,
        "total_pages": total_pages,
        "total":       total,
        "has_prev":    page > 1,
        "has_next":    page < total_pages,
        "filter_action":    action or "",
        "filter_date_from": date_from or "",
        "filter_date_to":   date_to or "",
    })


@dashboard_router.get("/archived", response_class=HTMLResponse)
def archived_page(
    request:   Request,
    sensor:    str | None = None,
    level:     str | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
    page:      int = 1,
    db: Session = Depends(get_db),
):
    """Page des alertes archivées avec filtres."""
    from datetime import datetime, timezone, timedelta
    PER = 20
    svc    = AlertService(db)
    page   = max(1, page)
    offset = (page - 1) * PER
    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None
    alerts = svc.get_archived(sensor=sensor or None, level=level or None, date_from=df, date_to=dt, limit=PER, offset=offset)
    total  = svc.count_archived(sensor=sensor or None, level=level or None, date_from=df, date_to=dt)
    total_pages = max(1, (total + PER - 1) // PER)
    return templates.TemplateResponse(request, "archived.html", {
        "alerts":      [a.to_dict() for a in alerts],
        "page":        page,
        "total_pages": total_pages,
        "total":       total,
        "has_prev":    page > 1,
        "has_next":    page < total_pages,
        "filters":     {"sensor": sensor or "", "level": level or "", "date_from": date_from or "", "date_to": date_to or ""},
    })


@dashboard_router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    """Page profil de l'utilisateur connecté."""
    from .auth import get_current_user, get_user_profile
    username = get_current_user(request) or "guest"
    profile  = get_user_profile(username)
    return templates.TemplateResponse(request, "profile.html", {
        "profile": profile,
        "username": username,
    })


@dashboard_router.get("/params", response_class=HTMLResponse)
def params_page(request: Request, db: Session = Depends(get_db)):
    """Page paramètres unifiée — seuils, notifications, sécurité, capteurs."""
    from ..alerts.threshold_config import get_all
    svc     = AlertService(db)
    windows = svc.get_maintenance_windows()
    return templates.TemplateResponse(request, "params.html", {
        "thresholds":          get_all(),
        "maintenance_windows": [w.to_dict() for w in windows],
    })


@dashboard_router.get("/map", response_class=HTMLResponse)
def map_page(request: Request, db: Session = Depends(get_db)):
    """Carte géographique des capteurs avec état en temps réel."""
    from ..alerts.zones_config import load_zones
    svc    = AlertService(db)
    health = svc.get_sensor_health()
    zones  = load_zones()
    # Fusionner health + zones pour le template
    sensors = []
    for sensor, zone_info in zones.items():
        h = health.get(sensor, {})
        sensors.append({
            "sensor": sensor,
            "label":  zone_info.get("label", sensor),
            "zone":   zone_info.get("zone", ""),
            "lat":    zone_info.get("lat", 0.0),
            "lon":    zone_info.get("lon", 0.0),
            "level":  h.get("level", "unknown"),
            "value":  h.get("value"),
            "unit":   h.get("unit", ""),
        })
    return templates.TemplateResponse(request, "map.html", {
        "sensors": sensors,
    })


@dashboard_router.get("/presentation", response_class=HTMLResponse)
def presentation_page(request: Request, db: Session = Depends(get_db)):
    """Mode présentation — affichage mural sans navigation."""
    svc    = AlertService(db)
    stats  = svc.get_stats()
    open_c = svc.get_open_count()
    health = svc.get_sensor_health()
    mttr_d = svc.get_mttr()
    # Moyenne MTTR en minutes (mttr_d est un dict {sensor: secondes})
    mttr_vals = [v for v in (mttr_d or {}).values() if v]
    mttr_avg  = round(sum(mttr_vals) / len(mttr_vals) / 60, 1) if mttr_vals else None
    recent = svc.get_all(resolved=False, limit=6)
    return templates.TemplateResponse(request, "presentation.html", {
        "stats":  stats,
        "open":   open_c,
        "health": health,
        "mttr":   mttr_avg,
        "recent": [a.to_dict() for a in recent],
    })
