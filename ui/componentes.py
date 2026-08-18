"""
Librería visual del dashboard.

Paleta: verde, blanco, negro, amarillo y gris. No se usa rojo ni azul en
ningún elemento. El verde señala lo positivo, el amarillo lo que requiere
atención y el gris lo secundario (típicamente el año anterior).

Criterio de diseño: el dashboard se mira, no se lee. Las explicaciones van en
tooltips (`ayuda=`), nunca en párrafos sobre la pantalla.

Funciones públicas
------------------
Color      : PALETA, color_empresa(codigo)
Estilos    : aplicar_estilos()
Formato    : soles(v, decimales), soles_corto(v), numero(v, decimales),
             porcentaje(v, decimales), formato_valor(v, tipo, decimales)
Bloques    : titulo_seccion(titulo, descripcion), nota(texto),
             aviso(texto, tipo), tarjeta_kpi(titulo, valor, delta,
             delta_positivo, ayuda, destacado, mini_grafico),
             semaforo(pct), insignia_semaforo(pct, sufijo),
             barra_meta(venta, meta_fecha, meta_anual, etiqueta_corte),
             panel_alertas(alertas, titulo), fila_chips(alertas)
Gráficos   : sparkline(valores, altura, color), grafico_bala(...),
             grafico_barras_mensual(...), grafico_barras_horizontales(...),
             grafico_linea_anual(...), grafico_pareto(...),
             grafico_barras_variacion(...), grafico_cascada(...),
             grafico_treemap(...), grafico_dispersion(...),
             grafico_heatmap(...), grafico_barras_apiladas(...)
Tablas     : tabla(df, formatos, resaltar, alinear_izquierda),
             tabla_larga(df, formatos, altura)

Todos los gráficos aceptan `key` y lo propagan a `st.plotly_chart`: dos
figuras sin clave propia en la misma pasada rompen Streamlit.
"""

from __future__ import annotations

import html
import itertools

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Paleta
# ---------------------------------------------------------------------------

PALETA: dict[str, str] = {
    "fondo": "#FFFFFF",
    "fondo_suave": "#F4F5F2",
    "borde": "#E4E6E1",
    "texto": "#14150F",
    "texto_suave": "#6B6F66",
    "verde": "#2E6B32",
    "verde_oscuro": "#1C4620",
    "verde_claro": "#8FBF94",
    "verde_fondo": "#E8F1E9",
    "amarillo": "#E8A400",
    "amarillo_fuerte": "#F2C200",
    "amarillo_fondo": "#FFF4D6",
    "gris": "#9AA096",
    "gris_claro": "#C9CDC5",
}
PALETA["positivo"] = PALETA["verde"]
PALETA["negativo"] = PALETA["amarillo"]
PALETA["neutro"] = PALETA["gris"]
PALETA["serie_actual"] = PALETA["verde"]
PALETA["serie_anterior"] = PALETA["gris"]

# Escala de verdes para treemaps y mapas de calor.
ESCALA_VERDE = [[0.0, "#FFFFFF"], [0.35, PALETA["verde_fondo"]],
                [0.7, PALETA["verde_claro"]], [1.0, PALETA["verde_oscuro"]]]

TIPOGRAFIA = '"Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif'

_contador = itertools.count()


def _clave(prefijo: str, key: str | None) -> str:
    """Clave única para cada figura, para no chocar con otra igual en la misma pasada."""
    return key or f"{prefijo}_{next(_contador)}"


def color_empresa(codigo: str) -> str:
    """
    Color de una empresa.

    Las tres empresas ya no tienen color propio: la paleta es una sola y la
    diferencia se hace por posición y etiqueta, no por color.
    """
    return PALETA["verde"]


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------

def aplicar_estilos() -> None:
    """CSS global: tipografía grande, sin cajas con borde, mucho aire."""
    st.markdown(
        f"""
        <style>
        .stApp {{ background: {PALETA['fondo']}; color: {PALETA['texto']};
                  font-family: {TIPOGRAFIA}; }}
        .block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1560px; }}

        html, body, .stApp, [data-testid="stMarkdownContainer"] {{
            font-family: {TIPOGRAFIA}; font-size: 16px; }}
        h1, h2, h3, h4 {{ color: {PALETA['texto']}; letter-spacing: -0.015em;
                          font-family: {TIPOGRAFIA}; }}
        h1 {{ font-size: 2.0rem !important; font-weight: 800 !important; margin-bottom: 0.2rem; }}
        h2 {{ font-size: 1.35rem !important; font-weight: 750 !important; }}
        h3 {{ font-size: 1.1rem !important; font-weight: 700 !important; }}

        /* Pestañas grandes, sin marco */
        .stTabs [data-baseweb="tab-list"] {{ gap: 0.2rem;
            border-bottom: 1px solid {PALETA['borde']}; }}
        .stTabs [data-baseweb="tab"] {{ font-size: 1.02rem; font-weight: 650;
            padding: 0.6rem 1.1rem; color: {PALETA['texto_suave']}; }}
        .stTabs [aria-selected="true"] {{ color: {PALETA['verde']}; }}
        .stTabs [data-baseweb="tab-highlight"] {{ background: {PALETA['verde']}; }}

        [data-testid="stSidebar"] {{ background: {PALETA['fondo_suave']};
            border-right: 1px solid {PALETA['borde']}; }}

        /* --- Indicadores: sin borde, solo aire y un fondo muy tenue --- */
        .kpi {{ padding: 0.15rem 0 0.35rem 0; }}
        .kpi-titulo {{ font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em;
            text-transform: uppercase; color: {PALETA['texto_suave']};
            margin-bottom: 0.15rem; min-height: 2.05em; line-height: 1.25;
            display: flex; align-items: flex-end; gap: 0.25rem; }}
        /* El valor se adapta al ancho de su columna: sin nowrap se pisaban
           entre si cuando el titulo ocupaba dos lineas. */
        .kpi-valor {{ font-size: clamp(1.0rem, 1.5vw, 1.7rem); font-weight: 800;
            line-height: 1.1; color: {PALETA['texto']}; overflow-wrap: anywhere; }}
        .kpi-destacado .kpi-valor {{ font-size: clamp(2.0rem, 3.3vw, 3.0rem);
            letter-spacing: -0.03em; }}
        .kpi-destacado .kpi-titulo {{ font-size: 0.78rem; }}
        .kpi-ayuda {{ display: inline-flex; align-items: center; justify-content: center;
            width: 1rem; height: 1rem; border-radius: 50%; background: {PALETA['borde']};
            color: {PALETA['texto_suave']}; font-size: 0.62rem; font-weight: 800;
            cursor: help; flex: 0 0 auto; }}
        .kpi-delta {{ margin-top: 0.15rem; font-size: 0.95rem; font-weight: 700; }}
        .kpi-delta span.sub {{ display: block; font-size: 0.78rem; font-weight: 500;
            color: {PALETA['texto_suave']}; }}

        /* --- Título de sección: regla fina arriba, sin caja --- */
        .seccion {{ margin: 1.5rem 0 0.5rem 0; padding-top: 0.7rem;
            border-top: 1px solid {PALETA['borde']}; }}
        .seccion h3 {{ margin: 0; }}
        .seccion .desc {{ font-size: 0.83rem; color: {PALETA['texto_suave']};
            margin-top: 0.1rem; }}

        /* --- Chips de alerta --- */
        .chip {{ display: inline-block; padding: 0.42rem 0.8rem; border-radius: 999px;
            font-size: 0.88rem; font-weight: 650; margin: 0 0.35rem 0.4rem 0; }}
        .chip-critico {{ background: {PALETA['amarillo_fondo']}; color: #7A5600;
            box-shadow: inset 0 0 0 1.5px {PALETA['amarillo']}; }}
        .chip-atencion {{ background: {PALETA['amarillo_fondo']}; color: #7A5600; }}
        .chip-bueno {{ background: {PALETA['verde_fondo']}; color: {PALETA['verde_oscuro']}; }}
        .chip .cifra {{ font-weight: 800; }}

        /* --- Tablas --- */
        table.t {{ border-collapse: collapse; width: 100%; font-size: 0.92rem; }}
        table.t th {{ text-align: right; font-size: 0.7rem; letter-spacing: 0.05em;
            text-transform: uppercase; color: {PALETA['texto_suave']}; font-weight: 700;
            padding: 0.45rem 0.6rem; border-bottom: 1.5px solid {PALETA['borde']}; }}
        table.t td {{ text-align: right; padding: 0.42rem 0.6rem;
            border-bottom: 1px solid {PALETA['fondo_suave']}; color: {PALETA['texto']}; }}
        table.t td.izq, table.t th.izq {{ text-align: left; }}
        table.t tr:hover td {{ background: {PALETA['fondo_suave']}; }}
        .pos {{ color: {PALETA['verde']}; font-weight: 700; }}
        .neg {{ color: {PALETA['amarillo']}; font-weight: 700; }}

        [data-testid="stMetricValue"] {{ font-size: 1.3rem; font-weight: 750; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------

def soles(valor: float, decimales: int = 0) -> str:
    """Monto completo: 'S/ 21,740,097'."""
    if valor is None or pd.isna(valor):
        return "s/d"
    return f"S/ {valor:,.{decimales}f}"


def soles_corto(valor: float) -> str:
    """Monto abreviado para tarjetas: 'S/ 21.7 M', 'S/ 320.3 mil'."""
    if valor is None or pd.isna(valor):
        return "s/d"
    signo = "-" if valor < 0 else ""
    v = abs(valor)
    if v >= 1_000_000:
        return f"{signo}S/ {v / 1_000_000:.1f} M"
    if v >= 1_000:
        return f"{signo}S/ {v / 1_000:.1f} mil"
    return f"{signo}S/ {v:,.0f}"


def numero(valor, decimales: int = 0) -> str:
    if valor is None or pd.isna(valor):
        return "s/d"
    return f"{valor:,.{decimales}f}"


def porcentaje(valor: float | None, decimales: int = 1) -> str:
    """Porcentaje con signo: '+12.4%'. Devuelve 's/d' cuando no hay base de comparación."""
    if valor is None or pd.isna(valor):
        return "s/d"
    return f"{valor:+.{decimales}f}%"


def formato_valor(valor, tipo: str = "texto", decimales: int | None = None) -> str:
    """Formatea según el tipo declarado en las tablas."""
    if tipo == "soles":
        return soles(valor, 0 if decimales is None else decimales)
    if tipo == "soles_corto":
        return soles_corto(valor)
    if tipo == "numero":
        return numero(valor, 1 if decimales is None else decimales)
    if tipo == "entero":
        return numero(valor, 0)
    if tipo == "porcentaje":
        return porcentaje(valor, 1 if decimales is None else decimales)
    if tipo == "pct":
        return "s/d" if valor is None or pd.isna(valor) else f"{valor:.{0 if decimales is None else decimales}f}%"
    if tipo == "fecha":
        return "" if valor is None or pd.isna(valor) else pd.Timestamp(valor).strftime("%d/%m/%Y")
    return "" if valor is None or (isinstance(valor, float) and pd.isna(valor)) else str(valor)


# ---------------------------------------------------------------------------
# Bloques
# ---------------------------------------------------------------------------

def titulo_seccion(titulo: str, descripcion: str | None = None) -> None:
    """Encabezado de sección: regla fina y, como mucho, una línea breve."""
    desc = f'<div class="desc">{html.escape(descripcion)}</div>' if descripcion else ""
    st.markdown(
        f'<div class="seccion"><h3>{html.escape(titulo)}</h3>{desc}</div>',
        unsafe_allow_html=True,
    )


def nota(texto: str) -> None:
    """Aclaración menor. Usar con cuentagotas."""
    st.caption(texto)


def aviso(texto: str, tipo: str = "info") -> None:
    """Mensaje breve. 'info' y 'atencion' en amarillo, 'bueno' en verde."""
    if tipo == "bueno":
        fondo, color = PALETA["verde_fondo"], PALETA["verde_oscuro"]
    else:
        fondo, color = PALETA["amarillo_fondo"], "#7A5600"
    st.markdown(
        f'<div style="background:{fondo};color:{color};padding:0.6rem 0.9rem;'
        f'border-radius:8px;font-size:0.9rem;font-weight:600;">{html.escape(texto)}</div>',
        unsafe_allow_html=True,
    )


def tarjeta_kpi(
    titulo: str,
    valor: str,
    delta: str | None = None,
    delta_positivo: bool | None = None,
    ayuda: str | None = None,
    destacado: bool = False,
    mini_grafico=None,
    sub: str | None = None,
) -> None:
    """
    Indicador. `destacado` lo agranda para marcar jerarquía.

    `delta_positivo` fuerza el color cuando el signo no basta (por ejemplo, en
    notas de crédito bajar es bueno). `mini_grafico` acepta una figura de
    plotly que se dibuja compacta debajo del número.
    """
    if delta_positivo is None and delta:
        delta_positivo = not delta.strip().startswith("-")
    color = PALETA["verde"] if delta_positivo else PALETA["amarillo"]
    flecha = "▲" if delta_positivo else "▼"

    bloque_delta = ""
    if delta:
        linea_sub = f'<span class="sub">{html.escape(sub)}</span>' if sub else ""
        bloque_delta = (
            f'<div class="kpi-delta" style="color:{color}">{flecha} {html.escape(delta)}'
            f"{linea_sub}</div>"
        )
    elif sub:
        bloque_delta = f'<div class="kpi-delta"><span class="sub">{html.escape(sub)}</span></div>'

    clase = "kpi kpi-destacado" if destacado else "kpi"
    # Se usa un "?" en un circulo dibujado por CSS: los simbolos tipograficos
    # tipo ⓘ no existen en todas las fuentes y salian como un cuadro vacio.
    etiqueta = f"<span>{html.escape(titulo)}</span>"
    if ayuda:
        etiqueta += f'<span class="kpi-ayuda" title="{html.escape(ayuda)}">?</span>'

    st.markdown(
        f'<div class="{clase}"><div class="kpi-titulo">{etiqueta}</div>'
        f'<div class="kpi-valor">{html.escape(valor)}</div>{bloque_delta}</div>',
        unsafe_allow_html=True,
    )
    if mini_grafico is not None:
        st.plotly_chart(mini_grafico, width='stretch',
                        config={"displayModeBar": False}, key=_clave("mini", None))


def semaforo(cumplimiento_pct: float | None) -> tuple[str, str]:
    """Color y etiqueta del cumplimiento a la fecha."""
    if cumplimiento_pct is None or pd.isna(cumplimiento_pct):
        return PALETA["gris"], "Sin meta"
    if cumplimiento_pct < 90:
        return PALETA["amarillo"], "Atrasado"
    if cumplimiento_pct < 100:
        return PALETA["amarillo_fuerte"], "En el límite"
    return PALETA["verde"], "En ritmo"


def insignia_semaforo(cumplimiento_pct: float | None, sufijo: str | None = None) -> None:
    """Píldora con el estado del cumplimiento."""
    color, etiqueta = semaforo(cumplimiento_pct)
    texto = etiqueta if not sufijo else f"{etiqueta} · {sufijo}"
    fondo = PALETA["verde_fondo"] if etiqueta == "En ritmo" else PALETA["amarillo_fondo"]
    tinta = PALETA["verde_oscuro"] if etiqueta == "En ritmo" else "#7A5600"
    st.markdown(
        f'<span class="chip" style="background:{fondo};color:{tinta};'
        f'box-shadow:inset 0 0 0 1.5px {color}">{html.escape(texto)}</span>',
        unsafe_allow_html=True,
    )


def fila_chips(alertas: list[dict], maximo: int = 4) -> None:
    """Alertas como píldoras cortas en una fila. El detalle largo va en el tooltip."""
    if not alertas:
        return
    piezas = []
    for a in alertas[:maximo]:
        clase = {"critico": "chip-critico", "atencion": "chip-atencion"}.get(a["nivel"], "chip-bueno")
        piezas.append(
            f'<span class="chip {clase}" title="{html.escape(a.get("detalle", ""))}">'
            f'{html.escape(a["titulo"])}</span>'
        )
    st.markdown("".join(piezas), unsafe_allow_html=True)


def panel_alertas(alertas: list[dict], titulo: str = "Qué revisar") -> None:
    """Alertas en formato compacto de chips."""
    if not alertas:
        return
    titulo_seccion(titulo)
    fila_chips(alertas, maximo=6)


def barra_meta(venta: float, meta_a_la_fecha: float | None,
               meta_anual: float | None, etiqueta_corte: str = "") -> None:
    """Compatibilidad: delega en el bullet chart, que es la forma correcta."""
    if not meta_anual:
        return
    st.plotly_chart(
        grafico_bala(venta, meta_a_la_fecha or 0, meta_anual, devolver=True),
        width='stretch', config={"displayModeBar": False},
        key=_clave("bala_compat", None),
    )


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------

def _tema(fig: go.Figure, altura: int | None = None, margen: dict | None = None) -> go.Figure:
    """Estética común: sin marco, grilla mínima, tipografía del sistema."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=TIPOGRAFIA, size=13, color=PALETA["texto"]),
        margin=margen or dict(l=8, r=8, t=28, b=8),
        showlegend=False,
        hoverlabel=dict(bgcolor=PALETA["texto"], font=dict(color="#FFFFFF", size=12)),
    )
    if altura:
        fig.update_layout(height=altura)
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=PALETA["borde"],
                     tickfont=dict(color=PALETA["texto_suave"], size=12))
    fig.update_yaxes(showgrid=True, gridcolor=PALETA["fondo_suave"], zeroline=False,
                     linecolor="rgba(0,0,0,0)",
                     tickfont=dict(color=PALETA["texto_suave"], size=12))
    return fig


def _mostrar(fig: go.Figure, prefijo: str, key: str | None, devolver: bool = False):
    if devolver:
        return fig
    st.plotly_chart(fig, width='stretch',
                    config={"displayModeBar": False}, key=_clave(prefijo, key))
    return None


def sparkline(valores, altura: int = 48, color: str | None = None, key: str | None = None,
              devolver: bool = True):
    """Mini tendencia sin ejes, para acompañar un número dentro de una tarjeta."""
    fig = go.Figure(go.Scatter(
        y=list(valores), mode="lines",
        line=dict(color=color or PALETA["verde"], width=2.2),
        fill="tozeroy", fillcolor=PALETA["verde_fondo"],
        hoverinfo="skip",
    ))
    fig.update_layout(
        height=altura, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return _mostrar(fig, "spark", key, devolver)


def grafico_bala(valor: float, referencia: float, maximo: float,
                 etiqueta: str | None = None, altura: int = 70,
                 key: str | None = None, devolver: bool = False):
    """
    Bullet chart: barra de lo vendido, marca negra en lo esperado a la fecha
    y escala hasta la meta anual. Es la lectura correcta de avance vs objetivo.
    """
    color, _ = semaforo((valor / referencia * 100) if referencia else None)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[maximo], y=[""], orientation="h", marker_color=PALETA["fondo_suave"],
        hoverinfo="skip", showlegend=False, width=0.62,
    ))
    fig.add_trace(go.Bar(
        x=[valor], y=[""], orientation="h", marker_color=color, width=0.34,
        hovertemplate="Vendido: S/ %{x:,.0f}<extra></extra>", showlegend=False,
    ))
    if referencia:
        fig.add_shape(type="line", x0=referencia, x1=referencia, y0=-0.34, y1=0.34,
                      line=dict(color=PALETA["texto"], width=3))
        fig.add_annotation(x=referencia, y=0.42, text="esperado", showarrow=False,
                           font=dict(size=11, color=PALETA["texto_suave"]), yanchor="bottom")
    fig.update_layout(barmode="overlay", height=altura,
                      margin=dict(l=0, r=8, t=18, b=0))
    fig = _tema(fig, altura, margen=dict(l=0, r=8, t=18, b=0))
    fig.update_xaxes(showticklabels=False, range=[0, max(maximo, valor, referencia) * 1.02])
    fig.update_yaxes(showticklabels=False, showgrid=False)
    return _mostrar(fig, "bala", key, devolver)


def grafico_barras_mensual(datos: pd.DataFrame, titulo: str | None = None,
                           anio_actual: int | None = None, anio_anterior: int | None = None,
                           altura: int = 340, key: str | None = None, devolver: bool = False):
    """
    Mes a mes: barras verdes del año en curso, línea gris del anterior.

    `datos` es lo que devuelve `metrics.ventas_mensuales`.
    """
    act = datos[datos["SERIE"] == "actual"].sort_values("MES")
    ant = datos[datos["SERIE"] == "anterior"].sort_values("MES")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=act["MES NOMBRE"], y=act["VENTA"], marker_color=PALETA["verde"],
        # Los meses que todavia no ocurrieron no llevan etiqueta: un "S/ 0"
        # repetido al final del grafico solo agrega ruido.
        text=[soles_corto(v) if v else "" for v in act["VENTA"]], textposition="outside",
        textfont=dict(size=11, color=PALETA["texto_suave"]),
        hovertemplate="%{x}: S/ %{y:,.0f}<extra></extra>", name=str(anio_actual or ""),
    ))
    if len(ant):
        fig.add_trace(go.Scatter(
            x=ant["MES NOMBRE"], y=ant["VENTA"], mode="lines+markers",
            line=dict(color=PALETA["gris"], width=2.2),
            marker=dict(size=6, color=PALETA["gris"]),
            hovertemplate="%{x} " + str(anio_anterior or "año anterior") +
                          ": S/ %{y:,.0f}<extra></extra>", name=str(anio_anterior or ""),
        ))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura)
    fig.update_yaxes(showticklabels=False)
    return _mostrar(fig, "mensual", key, devolver)


def grafico_barras_horizontales(etiquetas, valores, colores=None, titulo: str | None = None,
                                altura: int | None = None, key: str | None = None,
                                devolver: bool = False):
    """Ranking horizontal, el mayor arriba."""
    altura = altura or max(160, 34 * len(list(etiquetas)) + 60)
    fig = go.Figure(go.Bar(
        x=list(valores), y=list(etiquetas), orientation="h",
        marker_color=colores or PALETA["verde"],
        text=[soles_corto(v) for v in valores], textposition="outside",
        textfont=dict(size=11, color=PALETA["texto_suave"]),
        hovertemplate="%{y}: S/ %{x:,.0f}<extra></extra>",
    ))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura, margen=dict(l=8, r=60, t=28 if titulo else 8, b=8))
    fig.update_xaxes(showticklabels=False, showgrid=False)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _mostrar(fig, "barrash", key, devolver)


def grafico_linea_anual(datos: pd.DataFrame, titulo: str | None = None, altura: int = 260,
                        resaltar_anio: int | None = None, key: str | None = None,
                        devolver: bool = False):
    """Histórico por año. El año en curso se marca aparte por estar incompleto."""
    colores = [PALETA["amarillo"] if resaltar_anio and a == resaltar_anio else PALETA["verde"]
               for a in datos["ANIO"]]
    fig = go.Figure(go.Scatter(
        x=datos["ANIO"], y=datos["VENTA"], mode="lines+markers+text",
        line=dict(color=PALETA["verde"], width=2.6),
        marker=dict(size=9, color=colores),
        text=[soles_corto(v) for v in datos["VENTA"]], textposition="top center",
        textfont=dict(size=11, color=PALETA["texto_suave"]),
        hovertemplate="%{x}: S/ %{y:,.0f}<extra></extra>",
    ))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura)
    fig.update_yaxes(showticklabels=False)
    fig.update_xaxes(dtick=1)
    return _mostrar(fig, "anual", key, devolver)


def grafico_pareto(datos: pd.DataFrame, columna_etiqueta: str, columna_valor: str,
                   columna_acumulado: str | None = None, titulo: str | None = None,
                   altura: int = 380, key: str | None = None, devolver: bool = False):
    """Pareto: barras de venta y línea de participación acumulada con la marca del 80%."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=datos[columna_etiqueta], y=datos[columna_valor], marker_color=PALETA["verde"],
        hovertemplate="%{x}<br>S/ %{y:,.0f}<extra></extra>",
    ))
    if columna_acumulado and columna_acumulado in datos:
        fig.add_trace(go.Scatter(
            x=datos[columna_etiqueta], y=datos[columna_acumulado], yaxis="y2",
            mode="lines+markers", line=dict(color=PALETA["texto"], width=2),
            marker=dict(size=5), hovertemplate="Acumulado: %{y:.0f}%<extra></extra>",
        ))
        fig.add_hline(y=80, yref="y2", line=dict(color=PALETA["amarillo"], width=1.5, dash="dot"))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 105],
                                      showgrid=False, ticksuffix="%",
                                      tickfont=dict(color=PALETA["texto_suave"], size=11)))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura, margen=dict(l=8, r=8, t=28 if titulo else 8, b=8))
    fig.update_yaxes(showticklabels=False)
    fig.update_xaxes(tickangle=-35, tickfont=dict(size=10, color=PALETA["texto_suave"]))
    return _mostrar(fig, "pareto", key, devolver)


def grafico_barras_variacion(etiquetas, valores, titulo: str | None = None,
                             altura: int | None = None, key: str | None = None,
                             devolver: bool = False):
    """Barras divergentes: verde lo que sube, amarillo lo que baja."""
    valores = list(valores)
    altura = altura or max(180, 32 * len(valores) + 60)
    colores = [PALETA["verde"] if v >= 0 else PALETA["amarillo"] for v in valores]
    fig = go.Figure(go.Bar(
        x=valores, y=list(etiquetas), orientation="h", marker_color=colores,
        text=[soles_corto(v) for v in valores],
        textposition="outside", textfont=dict(size=11, color=PALETA["texto_suave"]),
        hovertemplate="%{y}: S/ %{x:,.0f}<extra></extra>",
    ))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura, margen=dict(l=8, r=70, t=28 if titulo else 8, b=8))
    fig.add_vline(x=0, line=dict(color=PALETA["borde"], width=1))
    fig.update_xaxes(showticklabels=False, showgrid=False)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _mostrar(fig, "variacion", key, devolver)


def grafico_cascada(etiquetas, valores, titulo: str | None = None, altura: int = 340,
                    medidas=None, key: str | None = None, devolver: bool = False):
    """Cascada. `medidas` permite marcar barras 'absolute'/'total' para abrir y cerrar."""
    medidas = medidas or ["relative"] * len(list(valores))
    fig = go.Figure(go.Waterfall(
        x=list(etiquetas), y=list(valores), measure=list(medidas),
        text=[soles_corto(v) for v in valores], textposition="outside",
        textfont=dict(size=11, color=PALETA["texto"]),
        connector=dict(line=dict(color=PALETA["borde"], width=1)),
        increasing=dict(marker=dict(color=PALETA["verde"])),
        decreasing=dict(marker=dict(color=PALETA["amarillo"])),
        totals=dict(marker=dict(color=PALETA["texto"])),
        hovertemplate="%{x}: S/ %{y:,.0f}<extra></extra>",
    ))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura)
    fig.update_yaxes(showticklabels=False)
    return _mostrar(fig, "cascada", key, devolver)


def grafico_treemap(etiquetas, valores, titulo: str | None = None, altura: int = 340,
                    key: str | None = None, devolver: bool = False):
    """Mix de composición en escala de verdes: el área es la participación."""
    fig = go.Figure(go.Treemap(
        labels=list(etiquetas), parents=[""] * len(list(etiquetas)), values=list(valores),
        marker=dict(colors=list(valores), colorscale=ESCALA_VERDE, line=dict(color="#FFFFFF", width=2)),
        texttemplate="<b>%{label}</b><br>%{percentRoot:.1%}",
        textfont=dict(size=12), hovertemplate="%{label}<br>S/ %{value:,.0f}<extra></extra>",
        tiling=dict(pad=2),
    ))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura, margen=dict(l=0, r=0, t=28 if titulo else 0, b=0))
    return _mostrar(fig, "treemap", key, devolver)


def grafico_dispersion(x, y, etiquetas, tamanos=None, titulo: str | None = None,
                       titulo_x: str = "", titulo_y: str = "", altura: int = 380,
                       key: str | None = None, devolver: bool = False):
    """
    Dispersión con cuadrantes. Pensada para precio contra volumen: los puntos
    abajo a la derecha son los que crecen en cantidad perdiendo precio.
    """
    x, y = list(x), list(y)
    colores = [PALETA["verde"] if (a or 0) >= 0 and (b or 0) >= 0
               else (PALETA["amarillo"] if (b or 0) < 0 else PALETA["gris"])
               for a, b in zip(x, y)]
    if tamanos is not None:
        tamanos = list(tamanos)
        tope = max(tamanos) or 1
        tamanos = [12 + 34 * (t / tope) for t in tamanos]
    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="markers", text=list(etiquetas),
        marker=dict(size=tamanos or 14, color=colores, opacity=0.8,
                    line=dict(color="#FFFFFF", width=1.5)),
        hovertemplate="%{text}<br>Cantidad: %{x:+.1f}%<br>Precio: %{y:+.1f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=PALETA["borde"], width=1.5))
    fig.add_vline(x=0, line=dict(color=PALETA["borde"], width=1.5))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura, margen=dict(l=8, r=8, t=28 if titulo else 8, b=32))
    fig.update_xaxes(title=dict(text=titulo_x, font=dict(size=11, color=PALETA["texto_suave"])),
                     ticksuffix="%", showgrid=True, gridcolor=PALETA["fondo_suave"])
    fig.update_yaxes(title=dict(text=titulo_y, font=dict(size=11, color=PALETA["texto_suave"])),
                     ticksuffix="%")
    return _mostrar(fig, "dispersion", key, devolver)


def grafico_heatmap(matriz: pd.DataFrame, titulo: str | None = None, altura: int | None = None,
                    key: str | None = None, devolver: bool = False):
    """Mapa de calor blanco→verde. Filas = años, columnas = meses."""
    altura = altura or max(180, 38 * len(matriz) + 70)
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]
    fig = go.Figure(go.Heatmap(
        z=matriz.values, x=meses[:matriz.shape[1]], y=[str(i) for i in matriz.index],
        colorscale=ESCALA_VERDE, showscale=False, xgap=3, ygap=3,
        hovertemplate="%{y} · %{x}: S/ %{z:,.0f}<extra></extra>",
    ))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura, margen=dict(l=8, r=8, t=28 if titulo else 8, b=8))
    fig.update_yaxes(showgrid=False, autorange="reversed")
    fig.update_xaxes(side="top", showgrid=False)
    return _mostrar(fig, "heatmap", key, devolver)


def grafico_barras_apiladas(categorias, series: dict, titulo: str | None = None,
                            altura: int = 300, key: str | None = None, devolver: bool = False):
    """Composición apilada en tonos de verde y gris."""
    tonos = [PALETA["verde"], PALETA["verde_claro"], PALETA["gris"], PALETA["verde_oscuro"],
             PALETA["gris_claro"]]
    fig = go.Figure()
    for i, (nombre, valores) in enumerate(series.items()):
        fig.add_trace(go.Bar(
            x=list(categorias), y=list(valores), name=str(nombre),
            marker_color=tonos[i % len(tonos)],
            hovertemplate=f"{nombre}<br>%{{x}}: S/ %{{y:,.0f}}<extra></extra>",
        ))
    fig.update_layout(barmode="stack", showlegend=True,
                      legend=dict(orientation="h", y=-0.18, font=dict(size=11)))
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14)))
    fig = _tema(fig, altura, margen=dict(l=8, r=8, t=28 if titulo else 8, b=40))
    fig.update_layout(showlegend=True)
    fig.update_yaxes(showticklabels=False)
    return _mostrar(fig, "apiladas", key, devolver)


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------

def tabla(df: pd.DataFrame, formatos: dict | None = None, resaltar: list | None = None,
          alinear_izquierda: list | None = None) -> None:
    """
    Tabla estática y compacta. `formatos` mapea columna -> tipo de `formato_valor`.
    `resaltar` son las columnas con signo, que se pintan en verde o amarillo.
    """
    if df is None or df.empty:
        st.caption("Sin datos para este periodo.")
        return

    formatos = formatos or {}
    resaltar = set(resaltar or [])
    izquierda = set(alinear_izquierda or [])

    encabezado = "".join(
        f'<th class="{"izq" if c in izquierda else ""}">{html.escape(str(c))}</th>'
        for c in df.columns
    )
    filas = []
    for _, fila in df.iterrows():
        celdas = []
        for col in df.columns:
            texto = formato_valor(fila[col], formatos.get(col, "texto"))
            clase = "izq" if col in izquierda else ""
            if col in resaltar and pd.notna(fila[col]) and isinstance(fila[col], (int, float)):
                clase += " pos" if fila[col] >= 0 else " neg"
            celdas.append(f'<td class="{clase.strip()}">{html.escape(texto)}</td>')
        filas.append("<tr>" + "".join(celdas) + "</tr>")

    st.markdown(
        f'<table class="t"><thead><tr>{encabezado}</tr></thead>'
        f'<tbody>{"".join(filas)}</tbody></table>',
        unsafe_allow_html=True,
    )


def tabla_larga(df: pd.DataFrame, formatos: dict | None = None, altura: int = 420) -> None:
    """Tabla con scroll y ordenable, para el detalle."""
    if df is None or df.empty:
        st.caption("Sin datos para este periodo.")
        return
    st.dataframe(df, width='stretch', height=altura, hide_index=True)
