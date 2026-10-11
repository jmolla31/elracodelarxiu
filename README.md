# El Racó de l'Arxiu

Blog de divulgació de l'arxiu de la Societat Unió Artística Musical d'Ontinyent: <https://elracodelarxiu.com>

Fet amb [Hugo](https://gohugo.io/) (extended, v0.156+) i el tema [PaperMod](https://github.com/adityatelange/hugo-PaperMod), afegit com a submòdul.

## Desenvolupament

```sh
git clone --recurse-submodules https://github.com/jmolla31/elracodelarxiu.git
hugo server        # http://localhost:1313
hugo --gc --minify # genera el lloc a public/
```

Si ja tens el repositori clonat sense el tema: `git submodule update --init`.

## Estructura

| Ruta | Contingut |
|------|-----------|
| `source_docs/` | Textos originals dels articles, abans d'editar |
| `content/posts/` | Articles publicats |
| `content/about.md`, `content/suggereix-canvis.md` | Pàgines fixes |
| `layouts/_default/index.html` | Portada (banner i últims articles) |
| `layouts/_default/list.html` | Còpia de la llista de PaperMod: mostra `description` com a resum. Mantín-la sincronitzada amb el tema quan l'actualitzes |
| `assets/css/extended/` | Colors de marca, tipografia, portada i ajustos de PaperMod |
| `static/` | Imatges, icones i tipografies servides tal qual |
| `.github/agents/BlogEditor.agent.md` | Instruccions de l'agent que converteix `source_docs/` en articles |

## Articles nous

Front matter mínim:

```yaml
---
title: "Títol"
date: 2026-01-12T12:00:00+01:00
draft: false
tags: ["música-festera", "ontinyent"]
categories: ["Història"]
author: "Nom Cognoms"
description: "Resum de 150-200 caràcters; s'usa a les llistes i als buscadors."
ShowToc: true
TocOpen: true
cover:
  image: "/images/slug-portada.jpg" # imatge en compartir a xarxes; no es mostra a la pàgina
  alt: "Descripció de la imatge"
---
```

Si un article no té `cover.image`, en compartir-lo s'usa `/images/mainbanner.jpg`.

## Marca

Només mode fosc (`defaultTheme: dark`, `disableThemeToggle: true`). Colors del manual corporatiu, definits a `assets/css/extended/brand-colors.css`:

| Token | Valor | Ús |
|-------|-------|----|
| `--brand-golden` | `#c6b300` | Daurat, color principal del Racó de l'Arxiu |
| `--brand-golden-dark` | `#a09200` | Variant fosca. Està assignat a `--entry`, però el tema fosc de PaperMod el sobreescriu i les targetes es veuen grises |
| `--brand-golden-light` | `#e6d000` | Estats *hover* i realçats |
| `--brand-light-gray` | `#dfdfdf` | Text |
| `--brand-dark-gray` | `#1d1d1b` | Fons |
