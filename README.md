# Generación de Ebook desde notebooks
Este repositorio contiene la fuente del eBook (notebooks) y el “pegamento” para
convertirlos a LaTeX/PDF mediante `nbconvert` + XeLaTeX y una plantilla mínima.

# Estructura del Proyecto — Compilador de Ebooks en base a notebooks (HUB)
.
├─ .gitignore
├─ README.md
├─ LICENSE
├─ requirements.txt
│
├─ config.json                # Archivo de configuración (títulos, rutas, flags)
├─ convertir_HUB.py           # Script principal de conversión y compilación
├─ estilo.tex                 # Archivo de estilo con macros y formato del libro
│
├─ notebooks/                 # Notebooks fuente (.ipynb)
│   ├─ capitulo1.ipynb
│   └─ gracias.ipynb
│
├─ figuras/                   # Imágenes utilizadas en los capítulos
│   ├─ figura1.png
│   └─ ...
│
├─ templates/
│   └─ bodyonly/
│       └─ index.tex.j2        # Plantilla Jinja2 usada por nbconvert
│
├─ build/                     # Carpeta generada automáticamente (IGNORADA EN GIT)
│   ├─ capitulo1.tex
│   ├─ capitulo1_body.tex
│   ├─ capitulo1_files/
│   ├─ gracias.tex
│   ├─ gracias_body.tex
│   ├─ latexmkrc
│   ├─ master.tex
│   ├─ master.pdf              # PDF final generado
│   ├─ master.xdv
│   ├─ master.aux
│   ├─ master.log
│   ├─ nb_preamble.tex
│   ├─ .gitkeep
│   └─ (otros archivos temporales de LaTeX)
│
└─ .ipynb_checkpoints/         # Carpeta automática de Jupyter (IGNORADA EN GIT)
