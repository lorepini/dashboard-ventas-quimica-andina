"""
Pantalla de apertura: la situación del grupo en cinco segundos.

Es la vista resumen, así que todo lo que no sea un número o un gráfico sobra.
El detalle vive en las pestañas de cada empresa.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import metas as metas_mod
from core import metrics as m
from core.loader import EMPRESAS, ORDEN_EMPRESAS

from . import componentes as comp
# El margen se lee igual en las dos pantallas: mismos criterios de periodo y de
# disponibilidad, definidos una sola vez en el detalle de empresa.
from .tab_empresa import MESES, _fin_margen, _hay_costos, _modulo_costos, _pct


def _margen_grupo(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> dict | None:
    """
    Margen del grupo y de cada empresa, o None si no hay costos cargados.

    Sin archivo de costos esta función no devuelve nada y la pantalla queda
    exactamente como estaba.
    """
    costos = _modulo_costos()
    if costos is None or not _hay_costos(df):
        return None
    try:
        kpis = costos.kpis_margen(df, anio, corte)
        cobertura = costos.cobertura_costos(df, anio, corte)
    except Exception:
        return None

    por_empresa: dict[str, float] = {}
    for empresa in df["EMPRESA"].dropna().unique():
        sub = df[df["EMPRESA"] == empresa]
        if not _hay_costos(sub):
            continue
        try:
            por_empresa[empresa] = costos.kpis_margen(sub, anio, corte).get("margen_pct")
        except Exception:
            continue

    fin = _fin_margen(kpis, df, corte)
    return {
        "pct": kpis.get("margen_pct"),
        "cobertura": cobertura.get("pct_cobertura"),
        "mes_fin": MESES[fin.month - 1] if fin is not None else None,
        "por_empresa": por_empresa,
    }


def _meta_grupo(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> tuple[float, float]:
    """
    Meta anual y meta esperada a la fecha, sumando las empresas que tengan meta.

    Cada empresa reparte su meta según su propia estacionalidad, por lo que el
    esperado del grupo es la suma de los esperados, no un prorrateo global.
    """
    anual = esperada = 0.0
    for empresa in ORDEN_EMPRESAS:
        try:
            meta = metas_mod.obtener_meta(anio, empresa)
        except Exception:
            meta = None
        if not meta:
            continue
        anual += meta
        historico = df[df["EMPRESA"] == empresa]
        try:
            esperada += metas_mod.meta_acumulada_a_la_fecha(meta, historico, anio, corte)
        except Exception:
            pass
    return anual, esperada


def _serie_ultimos_meses(df: pd.DataFrame, corte: pd.Timestamp, meses: int = 12) -> list[float]:
    """Venta de los últimos meses cerrados, para la mini tendencia."""
    desde = (corte - pd.DateOffset(months=meses - 1)).replace(day=1)
    serie = (
        df[df["FECHA"] >= desde]
        .groupby(df["FECHA"].dt.to_period("M"))["VENTA"]
        .sum()
        .sort_index()
    )
    return [float(v) for v in serie.values]


def render(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> None:
    """Vista consolidada de las tres empresas."""
    if df.empty:
        comp.aviso("No hay datos cargados.")
        return

    kpis = m.kpis_periodo(df, anio, corte)
    venta = kpis["actual"]["venta"]
    var = kpis["variaciones"]["venta"]
    meta_anual, meta_fecha = _meta_grupo(df, anio, corte)
    avance = m.avance_vs_meta(venta, meta_anual or None, meta_fecha or None)
    cumplimiento = avance.get("cumplimiento_fecha")

    # ---------------- Franja superior ----------------
    izq, centro, der = st.columns([1.05, 1.15, 1.35], gap="large")

    with izq:
        comp.tarjeta_kpi(
            f"Venta del grupo · {anio}",
            comp.soles_corto(venta),
            delta=f"{comp.porcentaje(var)} vs {anio - 1}",
            destacado=True,
            ayuda=f"Enero al {corte.strftime('%d/%m')} de {anio}, comparado contra "
                  f"el mismo tramo de {anio - 1}. Valor de venta sin IGV.",
            mini_grafico=comp.sparkline(_serie_ultimos_meses(df, corte), altura=54),
        )

    with centro:
        if meta_anual:
            comp.tarjeta_kpi(
                "Avance vs meta",
                f"{cumplimiento:.0f}%" if cumplimiento else "s/d",
                sub=f"esperado al {corte.strftime('%d/%m')}: {comp.soles_corto(meta_fecha)}",
                ayuda="Compara contra la parte de la meta anual que corresponde a "
                      "esta fecha, repartida según la estacionalidad histórica.",
            )
            comp.grafico_bala(venta, meta_fecha, meta_anual, altura=76, key="grupo_bala")
        else:
            comp.tarjeta_kpi("Avance vs meta", "Sin meta",
                             sub="cárgala en la barra lateral")

    margen = _margen_grupo(df, anio, corte)

    with der:
        columnas = st.columns(3 if margen else 2)
        a, b = columnas[0], columnas[1]
        with a:
            proy = m.proyeccion_cierre(df, anio, corte)
            comp.tarjeta_kpi(
                "Proyección cierre",
                comp.soles_corto(proy["proyeccion"]),
                delta=(comp.soles_corto(proy["proyeccion"] - meta_anual) if meta_anual else None),
                sub=(f"meta {comp.soles_corto(meta_anual)}" if meta_anual else None),
                ayuda="Si se mantiene el ritmo actual y el patrón estacional de los "
                      "últimos años, este sería el cierre del año.",
            )
        with b:
            comp.tarjeta_kpi(
                "Clientes",
                comp.numero(kpis["actual"]["clientes"]),
                delta=comp.porcentaje(kpis["variaciones"]["clientes"]),
                ayuda="Clientes distintos que compraron en el periodo, contados por RUC.",
            )
        if margen:
            with columnas[2]:
                periodo = (f"ene–{margen['mes_fin'][:3]}" if margen["mes_fin"]
                           else str(anio))
                cob = margen["cobertura"]
                comp.tarjeta_kpi(
                    "Margen del grupo", _pct(margen["pct"]),
                    sub=(f"{periodo} · sobre {cob:.0f}% de la venta"
                         if cob is not None else periodo),
                    ayuda="Margen bruto de fabricación: venta menos costo de producción. "
                          "NO es utilidad, no descuenta gastos ni fletes. Solo cubre la "
                          "venta con costo conocido y llega hasta el último mes con "
                          "costos cargados, antes que la venta. El detalle está en cada "
                          "empresa.",
                )

    alertas = m.generar_alertas(df, anio, corte, avance, limite=4, sufijo_ancla="_grupo")
    # El resumen no desarrolla todos los temas (el detalle de clientes en riesgo
    # o de productos vive en cada empresa), asi que se dejan enlazables solo las
    # alertas que aqui tienen a donde llevar.
    secciones = {"empresas_grupo", "clientes_grupo", "perdidos_grupo"}
    for a in alertas:
        if a.get("ancla") not in secciones:
            a.pop("ancla", None)
    if alertas:
        comp.fila_chips(alertas, maximo=4)

    # ---------------- Las tres empresas ----------------
    comp.titulo_seccion("Las tres empresas", ancla="empresas_grupo")
    resumen = m.resumen_por_empresa(df, anio, corte)
    columnas = st.columns(len(resumen), gap="large")
    for col, (_, fila) in zip(columnas, resumen.iterrows()):
        with col:
            sub = df[df["EMPRESA"] == fila["EMPRESA"]]
            detalle = (f"{fila['PARTICIPACION']:.0f}% del grupo · "
                       f"{int(fila['CLIENTES'])} clientes")
            # El margen va pegado a la venta: es la única forma de ver de un
            # vistazo quién vende mucho y gana poco.
            pct_margen = (margen or {}).get("por_empresa", {}).get(fila["EMPRESA"])
            ayuda = None
            if pct_margen is not None and not pd.isna(pct_margen):
                detalle += f" · margen {pct_margen:.0f}%"
                ayuda = ("Margen bruto de fabricación sobre la venta con costo conocido, "
                         "hasta el último mes con costos cargados. No es utilidad.")
            comp.tarjeta_kpi(
                fila["EMPRESA NOMBRE"],
                comp.soles_corto(fila["VENTA"]),
                delta=comp.porcentaje(fila["VARIACION PCT"]),
                sub=detalle,
                ayuda=ayuda,
                mini_grafico=comp.sparkline(_serie_ultimos_meses(sub, corte), altura=44),
            )

    # ---------------- Mes a mes y composición ----------------
    izq, der = st.columns([1.75, 1], gap="large")
    with izq:
        comp.titulo_seccion("Mes a mes")
        disponibles = [a for a in m.anios_disponibles(df) if a != anio]
        comparar = st.multiselect(
            "Comparar contra", disponibles,
            default=[a for a in [anio - 1] if a in disponibles],
            key="grupo_comparar", label_visibility="collapsed",
            placeholder="Comparar contra otros años...",
        )
        comp.grafico_mes_a_mes(
            m.ventas_por_mes_anios(df, [anio] + list(comparar)), anio,
            altura=330, key="grupo_mensual",
        )
    with der:
        comp.titulo_seccion("Composición")
        comp.grafico_treemap(
            resumen["EMPRESA NOMBRE"], resumen["VENTA"], altura=330, key="grupo_treemap",
        )

    # ---------------- Concentración e histórico ----------------
    izq, der = st.columns([1.35, 1], gap="large")
    with izq:
        conc = m.concentracion(df, anio, corte)
        comp.titulo_seccion(
            "Concentración de clientes",
            f"{conc['clientes_80']} de {conc['clientes']} clientes son el 80%",
            ancla="clientes_grupo",
        )
        top = m.pareto_clientes(df, anio, corte, top=10)
        if not top.empty:
            etiquetas = [c[:26] for c in top["CLIENTE"]]
            comp.grafico_pareto(
                pd.DataFrame({"CLIENTE": etiquetas, "VENTA": top["VENTA"].values,
                              "ACUMULADO": top["ACUMULADO"].values}),
                "CLIENTE", "VENTA", "ACUMULADO", altura=360, key="grupo_pareto",
            )
    with der:
        comp.titulo_seccion("Histórico y cartera", f"{anio} aún incompleto",
                            ancla="perdidos_grupo")
        comp.grafico_linea_anual(
            m.ventas_anuales(df), altura=250, resaltar_anio=anio, key="grupo_anual",
        )
        cartera = m.estado_cartera(df, anio, corte)
        a, b, c = st.columns(3)
        with a:
            comp.tarjeta_kpi("Nuevos", comp.numero(cartera["nuevos"]),
                             sub=comp.soles_corto(cartera["venta_nuevos"]))
        with b:
            comp.tarjeta_kpi("Recuperados", comp.numero(cartera["recuperados"]),
                             sub=comp.soles_corto(cartera["venta_recuperados"]))
        with c:
            comp.tarjeta_kpi("Perdidos", comp.numero(cartera["perdidos"]),
                             delta_positivo=False,
                             sub=comp.soles_corto(cartera["venta_perdida"]))
