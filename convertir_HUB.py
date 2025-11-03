#!/usr/bin/env python3
import json, sys, subprocess, re, argparse
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
NB_DIR = ROOT / "notebooks"
BUILD = ROOT / "build"
BUILD.mkdir(exist_ok=True)

def run(cmd, cwd=None):
    try:
        out = subprocess.run(
            cmd, cwd=cwd, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        ).stdout
        return out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        msg = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, (bytes, bytearray)) else str(e.stdout)
        print(msg)
        sys.exit(f"ERROR: {' '.join(cmd)}")

# ------------------ CLI ------------------
parser = argparse.ArgumentParser()
parser.add_argument("--only", nargs="*", help="Nombres sin .ipynb (ej: prefacio capitulo1 capitulo7)")

# >>> NUEVAS OPCIONES <<<
parser.add_argument("--no-exec", action="store_true",
                    help="No ejecutar celdas (ignora 'ejecutar' del config).")
parser.add_argument("--skip-exec", nargs="*", default=[],
                    help="Lista de capítulos (sin .ipynb) que NO se ejecutan, pero sí se convierten.")
parser.add_argument("--kernel", default=None,
                    help="Nombre del kernel para nbconvert (p.ej., 'python3', 'sagemath').")
parser.add_argument("--startup-timeout", type=int, default=240,
                    help="Tiempo (s) para que el kernel arranque (por defecto 240).")
parser.add_argument("--cell-timeout", type=int, default=0,
                    help="Tiempo (s) por celda; 0 = sin límite.")

args = parser.parse_args()

def norm_names(names):
    if not names: return []
    out = []
    for n in names:
        n = n.strip()
        if n.endswith(".ipynb"):
            n = n[:-6]
        out.append(n)
    return out

# normaliza lista de capítulos a saltar ejecución
skip_exec = set(norm_names(args.skip_exec))

# ---- Cargar configuración ----
cfg_all = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
cfg = cfg_all["libro"]

titulo     = cfg.get("titulo", "Libro")
autor      = cfg.get("autor", "Autor")
capitulos  = cfg["capitulos"]                    # lista con .ipynb
salida     = cfg.get("salida", "ebook_final.pdf")
tpl_dir    = cfg.get("plantilla_nbconvert")      # ej: "templates/bodyonly" o "templates/mylatex"
hide_tags  = cfg.get("ocultar_tags", [])         # ej: ["hide_input","hide_output"]
titulos    = cfg.get("titulos_capitulos", [])    # ej: ["Capítulo 1...", ...]
ejecutar   = bool(cfg.get("ejecutar", False))

# Mapa notebook -> título (si existe en la misma posición)
nb_to_title = {}
for i, nb in enumerate(capitulos):
    if i < len(titulos) and titulos[i]:
        nb_to_title[nb] = titulos[i]

# Selección de capítulos a compilar (respeta el orden del config.json)
only = norm_names(args.only)
if only:
    # filtrar capitulos del config conservando orden
    seleccion = [nb for nb in capitulos if Path(nb).stem in only]
    if not seleccion:
        sys.exit("⚠️ --only no coincidió con ningún capítulo del config.json")
    print("Compilando SOLO:", [Path(nb).stem for nb in seleccion])
else:
    seleccion = list(capitulos)
    print("Compilando TODOS:", [Path(nb).stem for nb in seleccion])

# ---- Helpers ----
def split_preamble_and_body(tex_path: Path):
    txt = tex_path.read_text(encoding="utf-8", errors="replace")
    b = txt.find(r"\begin{document}")
    e = txt.rfind(r"\end{document}")
    if b == -1 or e == -1:
        return "", txt.strip()
    preamble = txt[:b].strip()
    body = txt[b + len(r"\begin{document}"): e].strip()
    return preamble, body

def clean_preamble(preamble: str) -> str:
    lines = []
    for line in preamble.splitlines():
        if line.lstrip().startswith(r"\documentclass"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()

def default_title_from_filename(name: str) -> str:
    base = Path(name).stem.replace("_", " ").strip()
    return base[:1].upper() + base[1:] if base else "Capítulo"

# ---- 1) Convertir cada .ipynb a .tex (sólo selección) ----
body_tex_files = []      # lista paralela a 'seleccion'
nb_preamble_file = None  # primer preámbulo que encontremos (cuando reintentamos sin template)

for nb in seleccion:
    nb_path = NB_DIR / nb
    if not nb_path.exists():
        sys.exit(f"No existe notebook: {nb_path}")

    base = nb_path.stem
    out_tex = BUILD / f"{base}.tex"

    # Intento A: plantilla (si hay)
    cmd = ["jupyter", "nbconvert", "--to", "latex", "--output-dir", str(BUILD)]
    if tpl_dir:
        tpl_path = (ROOT / tpl_dir).resolve()
        tpl_name = tpl_path.name
        tpl_basedir = tpl_path.parent.as_posix()
        # Soporta tanto plantilla "clásica" como Jinja2 moderna con index.tex.j2
        cmd += [
            "--template", tpl_name,
            f"--TemplateExporter.extra_template_basedirs={tpl_basedir}",
            "--template-file", "index.tex.j2",
        ]
    if hide_tags:
        cmd += [
            "--TagRemovePreprocessor.enabled=True",
            "--TagRemovePreprocessor.remove_cell_tags=" + ",".join(hide_tags),
        ]

    # ¿Ejecutar celdas?
    do_exec = ejecutar and not args.no_exec and (Path(nb).stem not in skip_exec)
    if do_exec:
        cmd += [
            "--execute",
            f"--ExecutePreprocessor.timeout={args.cell_timeout}",
            f"--ExecutePreprocessor.startup_timeout={args.startup_timeout}",
        ]
        if args.kernel:
            cmd += [f"--ExecutePreprocessor.kernel_name={args.kernel}"]

    cmd.append(str(nb_path))
    print(run(cmd))

    # Heurística de salida sospechosa
    suspicious = False
    if out_tex.exists():
        size = out_tex.stat().st_size
        head = out_tex.read_text(encoding="utf-8", errors="replace")[:50]
        if size < 500 or head.lstrip().startswith("{#"):
            suspicious = True
    else:
        suspicious = True

    if not suspicious:
        # body-only ya correcto (plantilla generó cuerpo directo)
        body_tex_files.append(out_tex.name)
        continue

    # Intento B: sin plantilla, separar preámbulo y cuerpo
    print(f"⚠️ Plantilla no aplicada o salida sospechosa para {out_tex.name}. Reintentando sin template…")
    cmd = ["jupyter", "nbconvert", "--to", "latex", "--output-dir", str(BUILD)]
    if hide_tags:
        cmd += [
            "--TagRemovePreprocessor.enabled=True",
            "--TagRemovePreprocessor.remove_cell_tags=" + ",".join(hide_tags),
        ]

    # misma decisión de ejecución que arriba
    do_exec = ejecutar and not args.no_exec and (Path(nb).stem not in skip_exec)
    if do_exec:
        cmd += [
            "--execute",
            f"--ExecutePreprocessor.timeout={args.cell_timeout}",
            f"--ExecutePreprocessor.startup_timeout={args.startup_timeout}",
        ]
        if args.kernel:
            cmd += [f"--ExecutePreprocessor.kernel_name={args.kernel}"]

    cmd.append(str(nb_path))
    print(run(cmd))

    if not out_tex.exists():
        sys.exit(f"Fallo al generar {out_tex}")

    preamble, body_content = split_preamble_and_body(out_tex)

    if preamble and nb_preamble_file is None:
        nb_preamble_file = BUILD / "nb_preamble.tex"
        nb_preamble_file.write_text(clean_preamble(preamble) + "\n", encoding="utf-8")

    body_path = BUILD / f"{base}_body.tex"
    body_path.write_text(body_content, encoding="utf-8")
    body_tex_files.append(body_path.name)

# --- 1.1) Sanitizar cuerpos .tex (sólo los que realmente existen) ---
def sanitize_body_tex(path: Path):
    if not path.exists():
        return
    txt = path.read_text(encoding="utf-8")

    # (A) Quitar cosas globales que no deben ir en el cuerpo
    txt = re.sub(r'^\s*\\maketitle\s*$', '', txt, flags=re.MULTILINE)
    txt = re.sub(r'\\begin\{titlepage\}.*?\\end\{titlepage\}', '', txt, flags=re.DOTALL)
    txt = re.sub(r'^\s*\\tableofcontents\s*$', '', txt, flags=re.MULTILINE)
    txt = re.sub(r'^\s*\\title\{.*?\}\s*$', '', txt, flags=re.MULTILINE)
    txt = re.sub(r'^\s*\\author\{.*?\}\s*$', '', txt, flags=re.MULTILINE)

    # (B) Si al inicio del cuerpo quedó un encabezado tipo "Capítulo X ..." del notebook, eliminarlo
    patron_cap = r'(\\hypertarget\{.*?\}\{%[\s\r\n]*)?\\section\*?\{\s*Cap[íi]tulo\s+\d+[^}]*\}\s*'
    txt = re.sub(r'^\s*' + patron_cap, '', txt, flags=re.IGNORECASE | re.DOTALL)

    # (C) Forzar que TODAS las secciones sean numeradas (sin asterisco) -> así entran al TOC
    #     Si en algún capítulo querías deliberadamente una sección sin numerar, omite estas tres líneas:
    txt = re.sub(r'\\section\*\{', r'\\section{', txt)
    txt = re.sub(r'\\subsection\*\{', r'\\subsection{', txt)
    txt = re.sub(r'\\subsubsection\*\{', r'\\subsubsection{', txt)

    path.write_text(txt, encoding="utf-8")

for name in body_tex_files:
    sanitize_body_tex(BUILD / name)

# ---- 2) Construir master.tex (sólo selección) ----
estilo = ROOT / "estilo.tex"
master = BUILD / "master.tex"

lines = []
lines.append(r"\documentclass[12pt,openany]{book}")
lines.append(r"\usepackage[spanish,es-noshorthands]{babel}")

# Inyecta primero el preámbulo de nbconvert (si existe), luego el estilo del libro
if nb_preamble_file is not None and nb_preamble_file.exists():
    lines.append(rf"\input{{{nb_preamble_file.name}}}")

lines.append(rf"\input{{{estilo.as_posix()}}}")

lines.append(r"\begin{document}")
lines.append(rf"\title{{{titulo}}}")
lines.append(rf"\author{{{autor}}}")
lines.append(r"\date{\today}")
lines.append(r"\maketitle")
lines.append(r"\tableofcontents")
lines.append(r"\clearpage")

# OJO: usar body_tex_files en el MISMO orden que 'seleccion'
for i, nb in enumerate(seleccion):
    chap_title = nb_to_title.get(nb, default_title_from_filename(nb))
    lines.append(rf"\chapter{{{chap_title}}}")
    body_name = body_tex_files[i]
    lines.append(rf"\input{{{body_name}}}")
    if i != len(seleccion) - 1:
        lines.append(r"\clearpage")

lines.append(r"\end{document}")

master.write_text("\n".join(lines), encoding="utf-8")

# ---- 3) Compilar con latexmk ----
# Activar -shell-escape sólo si en estilo/nb_preamble/master aparece 'minted'
need_shell_escape = False
for p in [estilo, BUILD / "nb_preamble.tex", master]:
    if p.exists() and "minted" in p.read_text(encoding="utf-8", errors="ignore"):
        need_shell_escape = True
        break

cmd = [
    "latexmk",
    "-pdf",
    "-xelatex",
    "-interaction=nonstopmode",
    "-file-line-error",
    "-halt-on-error",
    "master.tex",
]
if need_shell_escape:
    cmd.insert(3, "-shell-escape")

print(run(cmd, cwd=BUILD))

# ---- 4) Copiar PDF final ----
final_pdf = BUILD / "master.pdf"
if not final_pdf.exists():
    sys.exit("No se generó master.pdf; revisa build/master.log")

dest = ROOT / salida
try:
    dest.write_bytes(final_pdf.read_bytes())
except PermissionError:
    print(f"⚠️ No pude escribir {dest} (¿abierto en otro programa?). Dejo copia en build/.")
print(f"✅ ¡eBook creado! -> {salida}")
