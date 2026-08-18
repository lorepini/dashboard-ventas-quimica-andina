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

    with der:
        a, b = st.columns(2)
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

    alertas = m.generar_alertas(df, anio, corte, avance, limite=4)
    if alertas:
        comp.fila_chips(alertas, maximo=4)

    # ---------------- Las tres empresas ----------------
    comp.titulo_seccion("Las tres empresas")
    resumen = m.resumen_por_empresa(df, anio, corte)
    columnas = st.columns(len(resumen), gap="large")
    for col, (_, fila) in zip(columnas, resumen.iterrows()):
        with col:
            sub = df[df["EMPRESA"] == fila["EMPRESA"]]
            comp.tarjeta_kpi(
                fila["EMPRESA NOMBRE"],
                comp.soles_corto(fila["VENTA"]),
                delta=comp.porcentaje(fila["VARIACION PCT"]),
                sub=f"{fila['PARTICIPACION']:.0f}% del grupo · {int(fila['CLIENTES'])} clientes",
                mini_grafico=comp.sparkline(_serie_ultimos_meses(sub, corte), altura=44),
            )

    # ---------------- Mes a mes y composición ----------------
    izq, der = st.columns([1.75, 1], gap="large")
    with izq:
        comp.titulo_seccion("Mes a mes", f"Barras {anio} · línea gris {anio - 1}")
        comp.grafico_barras_mensual(
            m.ventas_mensuales(df, anio), anio_actual=anio, anio_anterior=anio - 1,
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
        comp.titulo_seccion("Histórico", f"{anio} aún incompleto")
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
