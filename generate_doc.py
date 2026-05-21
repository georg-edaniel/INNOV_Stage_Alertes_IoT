"""
generate_doc.py
---------------
Genere explication_detection_aberrantes.docx
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime

doc = Document()

# ── Marges ──────────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin   = Cm(3)
    section.right_margin  = Cm(2.5)

# ── Styles helpers ───────────────────────────────────────────────────────────
def add_heading(doc, text, level=1, color=None):
    p = doc.add_heading(text, level=level)
    if color:
        for run in p.runs:
            run.font.color.rgb = RGBColor(*color)
    return p

def add_paragraph(doc, text, bold=False, italic=False, size=11, color=None, align=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold   = bold
    run.italic = italic
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor(*color)
    if align:
        p.alignment = align
    return p

def add_code_block(doc, code):
    """Paragraphe style code (Courier New, fond gris simulé via indentation)."""
    for line in code.strip().split("\n"):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent  = Cm(1.5)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        run = p.add_run(line if line else " ")
        run.font.name = "Courier New"
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x1e, 0x40, 0xaf)

def add_bullet(doc, text, bold_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    if bold_prefix:
        r = p.add_run(bold_prefix + " ")
        r.bold = True
        r.font.size = Pt(11)
    r2 = p.add_run(text)
    r2.font.size = Pt(11)
    return p

def shading_cell(cell, hex_color):
    """Applique un fond de couleur a une cellule de tableau."""
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color)
    tcPr.append(shd)

# ────────────────────────────────────────────────────────────────────────────
# PAGE DE GARDE
# ────────────────────────────────────────────────────────────────────────────
doc.add_paragraph()
doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("INNOV | CCNB")
run.bold = True
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x1d, 0x4e, 0xd8)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("Stage de fin d'etudes - Systeme d'alertes IoT")
run.font.size = Pt(11)
run.italic = True

doc.add_paragraph()
doc.add_paragraph()

p = doc.add_heading("Detection des valeurs aberrantes avec NumPy", 0)
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
for run in p.runs:
    run.font.color.rgb = RGBColor(0x1e, 0x40, 0xaf)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("Methodes statistiques Z-score et IQR, export et comparaison des donnees")
run.font.size = Pt(12)
run.italic = True

doc.add_paragraph()
doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("Date : " + datetime.date.today().strftime("%d/%m/%Y"))
run.font.size = Pt(11)

doc.add_page_break()

# ────────────────────────────────────────────────────────────────────────────
# SECTION 1 - CONTEXTE
# ────────────────────────────────────────────────────────────────────────────
add_heading(doc, "1. Contexte et objectif", 1, (0x1e, 0x40, 0xaf))

doc.add_paragraph(
    "Dans le cadre du systeme d'alertes IoT developpe lors de ce stage, les capteurs "
    "(temperature, turbidite, pH) transmettent des mesures en temps reel. "
    "Certaines de ces mesures peuvent etre aberrantes — dues a un bruit electronique, "
    "une panne passagere ou une transmission corrompue. "
    "Mon encadreur a demande d'utiliser NumPy pour implementer des methodes statistiques "
    "de detection de ces valeurs aberrantes."
)

doc.add_paragraph(
    "L'objectif etait double :"
)
add_bullet(doc, "Detecter automatiquement les valeurs hors-norme en temps reel lors de la reception des donnees capteur.", "1.")
add_bullet(doc, "Permettre l'export des donnees en deux versions : completes (avec aberrantes) et nettoyees (sans aberrantes), en CSV, Excel et PDF.", "2.")

# ────────────────────────────────────────────────────────────────────────────
# SECTION 2 - NUMPY
# ────────────────────────────────────────────────────────────────────────────
add_heading(doc, "2. Role de NumPy dans la detection", 1, (0x1e, 0x40, 0xaf))

doc.add_paragraph(
    "NumPy (Numerical Python) est une bibliotheque de calcul scientifique. "
    "Elle permet d'effectuer des operations mathematiques vectorisees (rapides) "
    "sur des tableaux de donnees. Dans ce projet, NumPy est utilise pour calculer "
    "en temps reel les statistiques d'une fenetre glissante de 30 lectures par capteur."
)

add_heading(doc, "2.1 Methode Z-score", 2, (0x16, 0x5a, 0xa0))

doc.add_paragraph(
    "Le Z-score mesure l'ecart d'une valeur par rapport a la moyenne de son groupe, "
    "exprime en nombre d'ecarts-types. Plus le Z-score est eleve (en valeur absolue), "
    "plus la valeur est eloignee de la normale."
)

add_code_block(doc, """\
import numpy as np
from collections import deque

class ZScoreDetector:
    def __init__(self, window=30, warn_th=2.0, crit_th=3.0):
        self._windows = {}           # une fenetre par capteur
        self.warn_th  = warn_th      # seuil WARNING  : |z| > 2
        self.crit_th  = crit_th      # seuil CRITICAL : |z| > 3

    def detect(self, sensor, value):
        win = self._windows.setdefault(sensor, deque(maxlen=self.window))
        win.append(value)
        if len(win) < 5:
            return "NORMAL"          # pas assez de donnees
        arr  = np.array(win)         # conversion en tableau NumPy
        mean = arr.mean()            # moyenne de la fenetre
        std  = arr.std()             # ecart-type
        if std == 0:
            return "NORMAL"
        z = abs((value - mean) / std)
        if z > self.crit_th:  return "CRITICAL"
        if z > self.warn_th:  return "WARNING"
        return "NORMAL"\
""")

doc.add_paragraph("")
add_bullet(doc, "arr.mean() : calcule la moyenne des 30 dernieres valeurs du capteur.", "np.array() :")
add_bullet(doc, "arr.std()  : calcule l'ecart-type (dispersion) de ces valeurs.", "arr.mean() :")
add_bullet(doc, "Si |z| > 3 : valeur CRITIQUE. Si |z| > 2 : WARNING. Sinon NORMAL.", "z-score :")

add_heading(doc, "2.2 Methode IQR (ecart interquartile)", 2, (0x16, 0x5a, 0xa0))

doc.add_paragraph(
    "L'IQR (Interquartile Range) est plus robuste que le Z-score car il est "
    "insensible aux valeurs extremes deja presentes dans la fenetre. "
    "Il definit des bornes basees sur les quartiles Q1 et Q3."
)

add_code_block(doc, """\
class IQRDetector:
    def detect(self, sensor, value):
        win = self._windows.setdefault(sensor, deque(maxlen=self.window))
        win.append(value)
        if len(win) < 5:
            return "NORMAL"
        arr = np.array(win)
        q1  = np.percentile(arr, 25)   # 1er quartile
        q3  = np.percentile(arr, 75)   # 3e quartile
        iqr = q3 - q1                  # ecart interquartile
        lo_warn = q1 - 1.5 * iqr      # borne basse WARNING
        hi_warn = q3 + 1.5 * iqr      # borne haute WARNING
        lo_crit = q1 - 3.0 * iqr      # borne basse CRITICAL
        hi_crit = q3 + 3.0 * iqr      # borne haute CRITICAL
        if value < lo_crit or value > hi_crit: return "CRITICAL"
        if value < lo_warn or value > hi_warn: return "WARNING"
        return "NORMAL"\
""")

doc.add_paragraph("")
add_bullet(doc, "np.percentile(arr, 25) calcule le 1er quartile (25% des valeurs sont en dessous).", "Q1 :")
add_bullet(doc, "np.percentile(arr, 75) calcule le 3e quartile.", "Q3 :")
add_bullet(doc, "IQR = Q3 - Q1. Les bornes WARNING sont Q1 - 1.5*IQR et Q3 + 1.5*IQR. Les bornes CRITICAL sont Q1 - 3*IQR et Q3 + 3*IQR.", "IQR :")

add_heading(doc, "2.3 Pourquoi NumPy plutot que Python pur ?", 2, (0x16, 0x5a, 0xa0))

# Tableau comparatif
table = doc.add_table(rows=1, cols=3)
table.style = "Table Grid"
hdr = table.rows[0].cells
hdr[0].text = "Critere"
hdr[1].text = "Python pur"
hdr[2].text = "NumPy"
for i, cell in enumerate(hdr):
    cell.paragraphs[0].runs[0].bold = True
    shading_cell(cell, "DBEAFE")

rows_data = [
    ("Vitesse de calcul",  "Boucle Python (lente)",              "Vectorise en C (tres rapide)"),
    ("Moyenne / Ecart-type", "sum()/len(), formule manuelle",    ".mean(), .std() integrees"),
    ("Percentiles (IQR)", "Tri + indexation manuelle",           "np.percentile() en 1 appel"),
    ("Lisibilite du code", "Verbeux, risque d'erreur",           "Concis et expressif"),
    ("Fiabilite numerique", "Accumulation d'erreurs float",      "Algorithmes stables"),
]
for r in rows_data:
    row = table.add_row().cells
    row[0].text = r[0]
    row[1].text = r[1]
    row[2].text = r[2]
    shading_cell(row[2], "EFF6FF")

doc.add_paragraph("")

# ────────────────────────────────────────────────────────────────────────────
# SECTION 3 - MOTEUR DE DETECTION
# ────────────────────────────────────────────────────────────────────────────
add_heading(doc, "3. Moteur de detection combine", 1, (0x1e, 0x40, 0xaf))

doc.add_paragraph(
    "Le moteur de detection (DetectionEngine) combine trois sources de detection : "
    "les regles metier fixes (seuils de temperature, pH, turbidite), "
    "le Z-score NumPy et l'IQR NumPy. "
    "Il retourne le niveau le plus severe parmi les trois."
)

add_code_block(doc, """\
class DetectionEngine:
    def detect(self, sensor, value, unit=""):
        levels = [
            RuleDetector().detect(sensor, value),
            ZScoreDetector().detect(sensor, value),
            IQRDetector().detect(sensor, value),
        ]
        # Priorite : CRITICAL > WARNING > NORMAL
        if "CRITICAL" in levels: return "CRITICAL"
        if "WARNING"  in levels: return "WARNING"
        return "NORMAL"\
""")

doc.add_paragraph("")
doc.add_paragraph(
    "Ainsi, une valeur peut etre marquee WARNING par les regles metier ET CRITICAL "
    "par le Z-score — le systeme retient CRITICAL. "
    "Ce mecanisme assure une couverture maximale des anomalies."
)

# ────────────────────────────────────────────────────────────────────────────
# SECTION 4 - EXPORT
# ────────────────────────────────────────────────────────────────────────────
add_heading(doc, "4. Export des donnees : complet vs nettoye", 1, (0x1e, 0x40, 0xaf))

doc.add_paragraph(
    "Chaque lecture capteur est stockee en base de donnees avec son niveau detecte "
    "(NORMAL, WARNING, CRITICAL). "
    "L'utilisateur peut exporter ces donnees en deux versions via la page /logs :"
)
add_bullet(doc, "Donnees completes : toutes les lectures, y compris les aberrantes (WARNING/CRITICAL).")
add_bullet(doc, "Donnees nettoyees : uniquement les lectures de niveau NORMAL.")

doc.add_paragraph(
    "Cote serveur (FastAPI), le filtrage est realise via SQLAlchemy :"
)

add_code_block(doc, """\
def get_logs(self, ..., exclude_outliers=False):
    q = self.db.query(SensorLog)
    if exclude_outliers:
        q = q.filter(SensorLog.level == "NORMAL")
    return q.order_by(desc(SensorLog.created_at)).limit(limit).all()\
""")

doc.add_paragraph("")
doc.add_paragraph(
    "Les fichiers telecharges contiennent un en-tete informatif :"
)
add_bullet(doc, "CSV  : lignes de commentaire # indiquant le nombre de lignes retirees.")
add_bullet(doc, "Excel: derniere ligne recapitulative avec le comptage.")
add_bullet(doc, "PDF  : sous-titre avec le bilan de nettoyage.")

# ────────────────────────────────────────────────────────────────────────────
# SECTION 5 - PAGE COMPARAISON
# ────────────────────────────────────────────────────────────────────────────
add_heading(doc, "5. Page de comparaison visuelle (/logs/compare)", 1, (0x1e, 0x40, 0xaf))

doc.add_paragraph(
    "Une page dediee permet de visualiser cote a cote les statistiques "
    "des donnees completes et nettoyees pour chaque capteur :"
)
add_bullet(doc, "Tableau : total, valeurs aberrantes, taux d'aberration par capteur.")
add_bullet(doc, "Graphique Chart.js : barres comparant complet vs nettoye.")
add_bullet(doc, "KPIs globaux : total toutes donnees, total aberrantes, taux global.")

doc.add_paragraph(
    "Cette page interroge directement la base de donnees sans export intermediaire, "
    "ce qui la rend instantanee et toujours a jour."
)

# ────────────────────────────────────────────────────────────────────────────
# SECTION 6 - COMPARAISON DEUX FICHIERS
# ────────────────────────────────────────────────────────────────────────────
add_heading(doc, "6. Comparaison de deux fichiers exportes", 1, (0x1e, 0x40, 0xaf))

doc.add_paragraph(
    "L'utilisateur peut egalement uploader deux fichiers (CSV ou Excel) "
    "prealablement exportes (par exemple : deux periodes differentes, "
    "ou avant/apres une intervention) pour les comparer."
)

doc.add_paragraph(
    "L'endpoint FastAPI /api/logs/compare-two :"
)
add_bullet(doc, "Accepte deux fichiers (UploadFile) en POST multipart.")
add_bullet(doc, "Parse CSV (pandas) ou Excel (openpyxl) selon l'extension.")
add_bullet(doc, "Calcule par capteur : total, aberrantes, taux pour chaque fichier.")
add_bullet(doc, "Retourne aussi le delta (difference) : moins d'aberrantes = amelioration (vert).")

doc.add_paragraph(
    "L'interface affiche les resultats dans un tableau interactif avec :"
)
add_bullet(doc, "Colonnes : Capteur, Fichier 1 (total, aberr., taux), Fichier 2 (total, aberr., taux), Delta.")
add_bullet(doc, "Couleurs : delta negatif en vert (moins d'aberrantes = mieux), positif en rouge.")
add_bullet(doc, "Export PDF de la comparaison en un clic (jsPDF + autoTable).")

# ────────────────────────────────────────────────────────────────────────────
# SECTION 7 - TABLEAU RECAPITULATIF
# ────────────────────────────────────────────────────────────────────────────
add_heading(doc, "7. Recapitulatif des fonctionnalites implementees", 1, (0x1e, 0x40, 0xaf))

table2 = doc.add_table(rows=1, cols=3)
table2.style = "Table Grid"
hdr2 = table2.rows[0].cells
hdr2[0].text = "Fonctionnalite"
hdr2[1].text = "Technologies"
hdr2[2].text = "Fichier principal"
for cell in hdr2:
    cell.paragraphs[0].runs[0].bold = True
    shading_cell(cell, "1E3A8A")
    cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)

rows2 = [
    ("Detection Z-score",        "NumPy (mean, std)",             "src/detection/statistical.py"),
    ("Detection IQR",            "NumPy (percentile)",            "src/detection/statistical.py"),
    ("Moteur combine",           "Python (worst-case)",           "src/detection/engine.py"),
    ("Stockage niveau detecte",  "SQLAlchemy + SQLite",           "src/alerts/models.py"),
    ("Export CSV nettoye",       "FastAPI StreamingResponse",     "src/api/routers.py"),
    ("Export Excel nettoye",     "ExcelJS (navigateur)",          "logs.html"),
    ("Export PDF nettoye",       "jsPDF + autoTable (nav.)",      "logs.html"),
    ("Page comparaison BD",      "FastAPI + Chart.js",            "dashboard.py / logs_compare.html"),
    ("Comparaison 2 fichiers",   "FastAPI + openpyxl + pandas",   "routers.py / logs_compare.html"),
]
for r in rows2:
    row = table2.add_row().cells
    row[0].text = r[0]
    row[1].text = r[1]
    row[2].text = r[2]

doc.add_paragraph("")

# ────────────────────────────────────────────────────────────────────────────
# CONCLUSION
# ────────────────────────────────────────────────────────────────────────────
add_heading(doc, "Conclusion", 1, (0x1e, 0x40, 0xaf))

doc.add_paragraph(
    "L'utilisation de NumPy pour la detection des valeurs aberrantes repond "
    "directement a la demande de l'encadreur. Les methodes Z-score et IQR, "
    "bien etablies en statistique, sont implementees de facon efficace "
    "grace aux fonctions vectorisees de NumPy."
)
doc.add_paragraph(
    "Le systeme complet permet :"
)
add_bullet(doc, "Une detection en temps reel multi-methodes (regles + Z-score + IQR).")
add_bullet(doc, "Un export des donnees dans trois formats avec bilan de nettoyage.")
add_bullet(doc, "Une comparaison visuelle instantanee via le dashboard.")
add_bullet(doc, "Une comparaison de deux fichiers pour evaluer l'evolution dans le temps.")

doc.add_paragraph("")
p = doc.add_paragraph()
run = p.add_run("Ces fonctionnalites constituent une reponse complete et professionnelle "
                "a la demande de traitement des donnees aberrantes dans un systeme IoT industriel.")
run.italic = True
run.font.color.rgb = RGBColor(0x1e, 0x40, 0xaf)

# ── Sauvegarde ───────────────────────────────────────────────────────────────
output_path = "explication_detection_aberrantes.docx"
doc.save(output_path)
print(f"Document genere : {output_path}")
