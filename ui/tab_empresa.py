"""
Detalle de una empresa.

Mismo módulo para las tres pestañas. Mantiene toda la profundidad analítica,
pero expresada en gráficos: las tablas quedan solo donde el detalle fila por
fila es la información (clientes en riesgo, perdidos y el detalle descargable).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import metas as metas_mod
from core import metrics as m
from core.loader import EMPRESAS

from . import componentes as comp


def _frase_precio_volumen(pv: dict) -> str:
    """Una línea que interpreta la cascada. El gráfico hace el resto."""
    precio, volumen = pv["efecto_precio"], pv["efecto_volumen"]
    if pv["variacion_total"] >= 0:
        if volumen >= abs(precio):
            return f"Creció por volumen: {comp.soles_corto(volumen)} en más cantidad."
        if precio > 0 and volumen < 0:
            return f"Creció solo por precio; se despachó menos ({comp.soles_corto(abs(volumen))})."
        return f"Creció por precio: {comp.soles_corto(precio)}."
    if volumen < 0 and abs(volumen) >= abs(precio):
        return f"Cayó por volumen: {comp.soles_corto(abs(volumen))} menos en cantidad."
    if precio < 0:
        return f"Cayó por precios más bajos: {comp.soles_corto(abs(precio))}."
    return "Cayó por salida de productos del catálogo."


def _meta(df_empresa: pd.DataFrame, empresa: str, anio: int,
          corte: pd.Timestamp) -> tuple[float | None, float | None]:
    """Meta anual y esperada a la fecha. Devuelve (None, None) si no hay meta cargada."""
    try:
        anual = metas_mod.obtener_meta(anio, empresa)
    except Exception:
        return None, None
    if not anual:
        return None, None
    try:
        esperada = metas_mod.meta_acumulada_a_la_fecha(anual, df_empresa, anio, corte)
    except Exception:
        esperada = None
    return anual, esperada


def _serie_ultimos_meses(df: pd.DataFrame, corte: pd.Timestamp, meses: int = 12) -> list[float]:
    desde = (corte - pd.DateOffset(months=meses - 1)).replace(day=1)
    serie = (df[df["FECHA"] >= desde]
             .groupby(df["FECHA"].dt.to_period("M"))["VENTA"].sum().sort_index())
    return [float(v) for v in serie.values]


def render(df: pd.DataFrame, empresa: str, anio: int, corte: pd.Timestamp) -> None:
    """Pantalla de detalle de una empresa."""
    datos = df[df["EMPRESA"] == empresa]
    ficha = EMPRESAS[empresa]
    k = f"{empresa}_{anio}"

    if datos.empty:
        comp.aviso(f"No hay datos cargados de {ficha['nombre']}.")
        return

    kpis = m.kpis_periodo(datos, anio, corte)
    venta = kpis["actual"]["venta"]
    meta_anual, meta_fecha = _meta(datos, empresa, anio, corte)
    avance = m.avance_vs_meta(venta, meta_anual, meta_fecha)
    cumplimiento = avance.get("cumplimiento_fecha")

    st.markdown(f"## {ficha['nombre_largo']}")
    st.caption(f"Enero al {corte.strftime('%d/%m/%Y')}")

    # ---------------- Indicadores ----------------
    izq, centro, der = st.columns([1.05, 1.1, 1.85], gap="large")

    with izq:
        comp.tarjeta_kpi(
            f"Venta {anio}", comp.soles_corto(venta),
            delta=f"{comp.porcentaje(kpis['variaciones']['venta'])} vs {anio - 1}",
            destacado=True,
            ayuda=f"Acumulado enero–{corte.strftime('%d/%m')}, contra el mismo tramo "
                  f"de {anio - 1}. Sin IGV, neto de notas de crédito.",
            mini_grafico=comp.sparkline(_serie_ultimos_meses(datos, corte), altura=54),
        )

    with centro:
        if meta_anual:
            comp.tarjeta_kpi(
                "Avance vs meta", f"{cumplimiento:.0f}%" if cumplimiento else "s/d",
                sub=f"esperado {comp.soles_corto(meta_fecha)} · meta {comp.soles_corto(meta_anual)}",
                ayuda="Contra la parte de la meta anual que toca a esta fecha, "
                      "repartida según la estacionalidad histórica de la empresa.",
            )
            comp.grafico_bala(venta, meta_fecha or 0, meta_anual, altura=76, key=f"{k}_bala")
        else:
            comp.tarjeta_kpi("Avance vs meta", "Sin meta", sub="cárgala en la barra lateral")

    with der:
        a, b, c = st.columns(3)
        proy = m.proyeccion_cierre(datos, anio, corte)
        with a:
            comp.tarjeta_kpi(
                "Proyección", comp.soles_corto(proy["proyeccion"]),
                delta=(comp.soles_corto(proy["proyeccion"] - meta_anual) if meta_anual else None),
                ayuda="Cierre estimado si se mantiene el ritmo y el patrón estacional.",
            )
        with b:
            comp.tarjeta_kpi(
                "Clientes", comp.numero(kpis["actual"]["clientes"]),
                delta=comp.porcentaje(kpis["variaciones"]["clientes"]),
                ayuda="Clientes distintos, contados por RUC.",
            )
        with c:
            comp.tarjeta_kpi(
                "Ticket promedio", comp.soles_corto(kpis["actual"]["ticket_promedio"]),
                delta=comp.porcentaje(kpis["variaciones"]["ticket_promedio"]),
                ayuda="Venta dividida entre el número de comprobantes emitidos.",
            )

    alertas = m.generar_alertas(datos, anio, corte, avance, limite=4)
    if alertas:
        comp.fila_chips(alertas, maximo=4)

    # ---------------- Mes a mes + precio/volumen ----------------
    izq, der = st.columns([1, 1], gap="large")
    with izq:
        comp.titulo_seccion("Mes a mes", f"Barras {anio} · línea gris {anio - 1}")
        comp.grafico_barras_mensual(
            m.ventas_mensuales(datos, anio), anio_actual=anio, anio_anterior=anio - 1,
            altura=330, key=f"{k}_mensual",
        )
    with der:
        pv = m.descomposicion_precio_volumen(datos, anio, corte)
        comp.titulo_seccion("¿Precio o volumen?", _frase_precio_volumen(pv))
        # Solo producto facturado: sin servicios y sin notas de credito, por eso
        # las barras extremas no coinciden con la venta total de la cabecera.
        comp.grafico_cascada(
            [f"Producto {anio - 1}", "Precio", "Volumen", "Nuevos", "Salidas",
             f"Producto {anio}"],
            [pv["venta_anterior"], pv["efecto_precio"], pv["efecto_volumen"],
             pv["efecto_nuevos"], pv["efecto_salidas"], pv["venta_actual"]],
            medidas=["absolute", "relative", "relative", "relative", "relative", "total"],
            altura=330, key=f"{k}_cascada",
        )
        comp.nota("Solo venta de producto: excluye servicios y notas de crédito.")

    # ---------------- Productos ----------------
    productos = m.ranking_productos(datos, anio, corte, top=12)
    comp.titulo_seccion("Productos")
    izq, centro, der = st.columns([1.15, 1, 1.15], gap="large")
    with izq:
        comp.grafico_barras_horizontales(
            [p[:30] for p in productos["PRODUCTO"]], productos["VENTA"],
            altura=380, key=f"{k}_prod_barras",
        )
    with centro:
        comp.grafico_treemap(
            [p[:24] for p in productos["PRODUCTO"]], productos["VENTA"],
            altura=380, key=f"{k}_prod_treemap",
        )
    with der:
        disp = productos.dropna(subset=["VAR CANTIDAD PCT", "VAR PRECIO PCT"])
        if len(disp) >= 2:
            comp.grafico_dispersion(
                disp["VAR CANTIDAD PCT"].clip(-100, 200),
                disp["VAR PRECIO PCT"].clip(-100, 200),
                [p[:26] for p in disp["PRODUCTO"]], tamanos=disp["VENTA"],
                titulo_x="Cantidad vs año anterior", titulo_y="Precio vs año anterior",
                altura=380, key=f"{k}_dispersion",
            )
            comp.nota("Abajo a la derecha: se vende más pero a menor precio.")
        else:
            st.caption("Sin productos comparables contra el año anterior.")

    # ---------------- Clientes ----------------
    comp.titulo_seccion("Clientes")
    cartera = m.estado_cartera(datos, anio, corte)
    conc = m.concentracion(datos, anio, corte)

    fila = st.columns(5)
    with fila[0]:
        comp.tarjeta_kpi("Nuevos", comp.numero(cartera["nuevos"]),
                         sub=comp.soles_corto(cartera["venta_nuevos"]))
    with fila[1]:
        comp.tarjeta_kpi("Recuperados", comp.numero(cartera["recuperados"]),
                         sub=comp.soles_corto(cartera["venta_recuperados"]))
    with fila[2]:
        comp.tarjeta_kpi("Perdidos", comp.numero(cartera["perdidos"]), delta_positivo=False,
                         sub=comp.soles_corto(cartera["venta_perdida"]))
    with fila[3]:
        comp.tarjeta_kpi(
            "Retención",
            f"{cartera['retencion_pct']:.0f}%" if cartera["retencion_pct"] else "s/d",
            ayuda="De los clientes que compraron en el mismo periodo del año pasado, "
                  "qué porcentaje volvió a comprar.",
        )
    with fila[4]:
        comp.tarjeta_kpi(
            "Top 5", f"{conc['top5']:.0f}%",
            delta_positivo=conc["top5"] < 50,
            sub=f"{conc['clientes_80']} clientes son el 80%",
            ayuda="Parte de la venta que depende de los 5 clientes más grandes. "
                  "Mientras más alto, mayor el riesgo si uno se va.",
        )

    izq, der = st.columns([1.3, 1], gap="large")
    with izq:
        top = m.pareto_clientes(datos, anio, corte, top=12)
        comp.grafico_pareto(
            pd.DataFrame({"CLIENTE": [c[:24] for c in top["CLIENTE"]],
                          "VENTA": top["VENTA"].values,
                          "ACUMULADO": top["ACUMULADO"].values}),
            "CLIENTE", "VENTA", "ACUMULADO", altura=380, key=f"{k}_pareto",
        )
    with der:
        variaciones = m.variaciones_clientes(datos, anio, corte, top=6)
        movimiento = pd.concat([variaciones["suben"], variaciones["bajan"]])
        if not movimiento.empty:
            movimiento = movimiento.sort_values("VARIACION", ascending=False)
            comp.grafico_barras_variacion(
                [c[:26] for c in movimiento["CLIENTE"]], movimiento["VARIACION"],
                altura=380, key=f"{k}_movimiento",
            )
            comp.nota(f"Quién subió y quién bajó en soles, vs {anio - 1}.")

    # ---------------- Listas accionables ----------------
    izq, der = st.columns(2, gap="large")
    with izq:
        comp.titulo_seccion("Se están enfriando", "Contra el ritmo propio de cada cliente")
        riesgo = m.clientes_en_riesgo(datos, corte, top=12)
        if riesgo.empty:
            st.caption("Ningún cliente habitual está retrasado.")
        else:
            comp.tabla(
                riesgo[["CLIENTE", "ULTIMA COMPRA", "DIAS SIN COMPRAR",
                        "RITMO HABITUAL (DIAS)", "VENTA 12M"]],
                formatos={"ULTIMA COMPRA": "fecha", "DIAS SIN COMPRAR": "entero",
                          "RITMO HABITUAL (DIAS)": "entero", "VENTA 12M": "soles"},
                alinear_izquierda=["CLIENTE"],
            )
    with der:
        comp.titulo_seccion("Dejaron de comprar", f"Compraban en {anio - 1}, este año no")
        perdidos = m.detalle_clientes_perdidos(datos, anio, corte, top=12)
        if perdidos.empty:
            st.caption("Ningún cliente del año pasado dejó de comprar.")
        else:
            comp.tabla(
                perdidos[["CLIENTE", "VENTA ANTERIOR", "ULTIMA COMPRA", "DIAS SIN COMPRAR"]],
                formatos={"VENTA ANTERIOR": "soles", "ULTIMA COMPRA": "fecha",
                          "DIAS SIN COMPRAR": "entero"},
                alinear_izquierda=["CLIENTE"],
            )

    # ---------------- Estacionalidad y detalle ----------------
    comp.titulo_seccion("Estacionalidad", "Meses fuertes y flojos por año")
    comp.grafico_heatmap(m.estacionalidad(datos), key=f"{k}_heatmap")

    with st.expander("Ver y descargar el detalle"):
        detalle = m.acumulado_a_la_fecha(datos, anio, corte)[
            ["FECHA", "TD", "SERIE", "DOCUMENTO", "RUC", "CLIENTE",
             "COD ARTICULO", "PRODUCTO", "CANTIDAD", "P. UNITARIO", "VENTA"]
        ].sort_values("FECHA", ascending=False)
        comp.tabla_larga(detalle.head(500))
        st.download_button(
            "Descargar en Excel (CSV)",
            detalle.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            file_name=f"detalle_{ficha['nombre']}_{anio}.csv",
            mime="text/csv",
            key=f"{k}_descarga",
        )
