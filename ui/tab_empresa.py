"""
Detalle de una empresa.

Mismo módulo para las tres pestañas. Mantiene toda la profundidad analítica,
pero expresada en gráficos: las tablas quedan solo donde el detalle fila por
fila es la información (clientes en riesgo, perdidos y el detalle descargable).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import metas as metas_mod
from core import metrics as m
from core.loader import EMPRESAS

from . import componentes as comp

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre"]
MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]


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


# ---------------------------------------------------------------------------
# Rentabilidad
#
# Todo este bloque es opcional: el archivo de costos puede no estar cargado.
# Cuando falta, `_hay_costos` devuelve False y la pantalla queda igual que
# siempre, sin avisos ni huecos.
# ---------------------------------------------------------------------------

def _modulo_costos():
    """El módulo de costos, o None si todavía no existe en esta instalación."""
    try:
        from core import costos
        return costos
    except Exception:
        return None


def _hay_costos(datos: pd.DataFrame) -> bool:
    """Hay margen que mostrar solo si las ventas vienen enriquecidas con costos."""
    if "MARGEN" not in datos.columns:
        return False
    if "TIENE COSTO" in datos.columns:
        return bool(datos["TIENE COSTO"].fillna(False).astype(bool).any())
    return bool(datos["MARGEN"].notna().any())


def _fin_margen(kpis: dict, datos: pd.DataFrame,
                corte: pd.Timestamp) -> pd.Timestamp | None:
    """
    Hasta dónde llega de verdad el margen: fin del último mes con costo.

    El margen se corta ahí, no en la fecha de corte de la venta. Los costos
    llegan con retraso, y leer un margen de enero a junio como si fuera de
    enero a agosto es el error más caro que puede cometer esta pantalla.
    """
    fin = (kpis or {}).get("corte_efectivo")
    if fin is not None and not pd.isna(fin):
        return pd.Timestamp(fin)
    if "TIENE COSTO" not in datos.columns:  # respaldo
        return None
    con_costo = datos[(datos["DIA DEL ANIO"] <= corte.dayofyear)
                      & datos["TIENE COSTO"].fillna(False).astype(bool)]
    if con_costo.empty:
        return None
    return pd.Timestamp(con_costo["FECHA"].max())


def _pct(valor, decimales: int = 1) -> str:
    if valor is None or pd.isna(valor):
        return "s/d"
    return f"{valor:.{decimales}f}%"


def _delta_vs(valor, anio: int) -> str | None:
    """Variación interanual lista para la tarjeta, o None si no hay base."""
    if valor is None or pd.isna(valor):
        return None
    return f"{comp.porcentaje(valor)} vs {anio - 1}"


def _nombre_mes(valor) -> str:
    try:
        i = int(valor)
    except (TypeError, ValueError):
        return str(valor)
    return MESES_CORTOS[i - 1] if 1 <= i <= 12 else str(valor)


def _grafico_margen_mensual(evolucion: pd.DataFrame, key: str, altura: int = 400) -> None:
    """Barras de margen en soles y línea de margen % en el eje derecho."""
    datos = evolucion.copy()
    if "COSTO" in datos.columns:
        # Los meses sin costo cargado no se dibujan: una barra en cero haría
        # creer que ese mes no dejó margen.
        datos = datos[datos["COSTO"].fillna(0) != 0]
    if datos.empty:
        st.caption("Sin costos cargados para este año.")
        return

    etiquetas = ([str(v) for v in datos["MES NOMBRE"]] if "MES NOMBRE" in datos.columns
                 else [_nombre_mes(v) for v in datos["MES"]])
    margen = datos["MARGEN"].astype(float)
    pct = datos["MARGEN PCT"].astype(float)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=etiquetas, y=margen, marker_color=comp.PALETA["verde"],
        text=[comp.soles_corto(v) for v in margen], textposition="outside",
        textfont=dict(size=11, color=comp.PALETA["texto_suave"]),
        hovertemplate="%{x}: S/ %{y:,.0f}<extra></extra>", name="Margen",
    ))
    fig.add_trace(go.Scatter(
        x=etiquetas, y=pct, yaxis="y2", mode="lines+markers",
        line=dict(color=comp.PALETA["texto"], width=2),
        marker=dict(size=6, color=comp.PALETA["texto"]),
        hovertemplate="%{x}: %{y:.1f}% de margen<extra></extra>", name="Margen %",
    ))
    fig = comp._tema(fig, altura, margen=dict(l=8, r=52, t=28, b=8))
    fig.update_yaxes(showticklabels=False)
    tope = float(pct.max()) if len(pct.dropna()) else 0.0
    piso = min(0.0, float(pct.min()) if len(pct.dropna()) else 0.0)
    fig.update_layout(yaxis2=dict(
        overlaying="y", side="right", showgrid=False, showticklabels=True,
        ticksuffix="%", range=[piso, max(tope * 1.45, 1)],
        tickfont=dict(color=comp.PALETA["texto_suave"], size=11),
    ))
    st.plotly_chart(fig, width="stretch", config=comp.CONFIG_GRAFICO, key=key)


def _grafico_margen_producto(datos: pd.DataFrame, referencia: float, key: str,
                             altura: int = 400) -> None:
    """
    Margen % por producto, el mejor arriba.

    El color dice si el producto está por encima o por debajo del margen de la
    empresa; el amarillo queda reservado para los que venden por debajo del costo.
    """
    if datos.empty:
        st.caption("Sin productos con costo en el periodo.")
        return

    valores = [float(v) if pd.notna(v) else 0.0 for v in datos["MARGEN PCT"]]
    colores = []
    for v in valores:
        if v < 0:
            colores.append(comp.PALETA["amarillo"])
        elif v < referencia:
            colores.append(comp.PALETA["verde_claro"])
        else:
            colores.append(comp.PALETA["verde"])

    fig = go.Figure(go.Bar(
        x=valores, y=[str(p)[:32] for p in datos["PRODUCTO"]], orientation="h",
        marker_color=colores, cliponaxis=False,
        text=[f"{v:.1f}%" for v in valores], textposition="outside",
        textfont=dict(size=11, color=comp.PALETA["texto_suave"]),
        customdata=datos["MARGEN"].astype(float),
        hovertemplate="%{y}<br>%{x:.1f}% de margen<br>S/ %{customdata:,.0f}<extra></extra>",
    ))
    fig = comp._tema(fig, altura, margen=dict(l=8, r=72, t=8, b=8))
    # Con pocos productos las barras salían como bloques enormes.
    fig.update_layout(bargap=0.4)
    fig.add_vline(x=0, line=dict(color=comp.PALETA["borde"], width=1))
    if referencia:
        fig.add_vline(x=referencia,
                      line=dict(color=comp.PALETA["texto_suave"], width=1.2, dash="dot"))
    fig.update_xaxes(showticklabels=False, showgrid=False)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    st.plotly_chart(fig, width="stretch", config=comp.CONFIG_GRAFICO, key=key)


def _clientes_flojos(clientes: pd.DataFrame, referencia: float) -> str | None:
    """Los que más facturan y menos margen dejan, en una línea."""
    if clientes.empty or "VENTA" not in clientes.columns or not referencia:
        return None
    grandes = clientes.sort_values("VENTA", ascending=False).head(5)
    # Cinco puntos por debajo del promedio: menos que eso es ruido y la frase
    # terminaría señalando clientes que en realidad están en línea.
    flojos = grandes[grandes["MARGEN PCT"].fillna(0) < referencia - 5]
    if flojos.empty:
        return None
    piezas = [f"{str(f['CLIENTE'])[:26]} ({_pct(f['MARGEN PCT'], 0)})"
              for _, f in flojos.head(2).iterrows()]
    return "Facturan alto y dejan poco: " + " · ".join(piezas)


def _seccion_rentabilidad(datos: pd.DataFrame, anio: int, corte: pd.Timestamp,
                          k: str) -> None:
    """Sección completa de margen. No dibuja nada si no hay costos cargados."""
    costos = _modulo_costos()
    if costos is None or not _hay_costos(datos):
        return

    try:
        kpis = costos.kpis_margen(datos, anio, corte)
        cobertura = costos.cobertura_costos(datos, anio, corte)
        evolucion = costos.evolucion_margen(datos, anio)
        productos = costos.margen_por_producto(datos, anio, corte, top=15)
        clientes = costos.margen_por_cliente(datos, anio, corte, top=15)
    except Exception:
        comp.nota("Rentabilidad no disponible para este periodo.")
        return

    margen_pct = kpis.get("margen_pct")
    anterior = kpis.get("anterior") or {}
    variaciones = kpis.get("variaciones") or {}
    cob_pct = cobertura.get("pct_cobertura")
    fin = _fin_margen(kpis, datos, corte)
    periodo = f"enero–{MESES[fin.month - 1]} {anio}" if fin is not None else f"{anio}"

    comp.titulo_seccion(
        "Rentabilidad",
        "Margen bruto de fabricación: venta menos costo de producción. No es utilidad.",
        ancla=f"margen_{k}",
    )

    fila = st.columns(4)
    with fila[0]:
        comp.tarjeta_kpi(
            "Margen bruto", comp.soles_corto(kpis.get("margen")),
            delta=_delta_vs(variaciones.get("margen"), anio),
            sub=periodo,
            ayuda="Venta menos el costo de producción de lo vendido (toneladas × costo "
                  "del mes). Es margen de fabricación, NO utilidad: no descuenta gastos "
                  "administrativos, comerciales ni fletes. Se compara contra el mismo "
                  f"tramo de {anio - 1}.",
        )
    with fila[1]:
        pp = None
        if anterior.get("margen_pct") is not None and margen_pct is not None:
            if not pd.isna(anterior["margen_pct"]) and not pd.isna(margen_pct):
                pp = float(margen_pct) - float(anterior["margen_pct"])
        comp.tarjeta_kpi(
            "Margen %", _pct(margen_pct),
            delta=(f"{pp:+.1f} pp vs {anio - 1}" if pp is not None else None),
            sub=(f"sobre el {cob_pct:.0f}% de la venta" if cob_pct is not None else None),
            ayuda="Margen sobre la venta que sí tiene costo conocido. No es el margen "
                  "de toda la empresa: la venta sin costo cargado queda fuera del cálculo.",
        )
    with fila[2]:
        # El costo va sin flecha: sube cuando se despacha más volumen, así que
        # pintarlo de verde o de amarillo diría algo que el dato no dice.
        var_costo = variaciones.get("costo")
        detalle = periodo
        if var_costo is not None and not pd.isna(var_costo):
            detalle += f" · {comp.porcentaje(var_costo)} vs {anio - 1}"
        comp.tarjeta_kpi(
            "Costo producción", comp.soles_corto(kpis.get("costo")),
            sub=detalle,
            ayuda="Costo de producción de las toneladas vendidas en el periodo. "
                  "Sube cuando se despacha más volumen o cuando encarece el costo unitario.",
        )
    with fila[3]:
        pp_cob = None
        try:
            previa = costos.cobertura_costos(datos, anio - 1, corte).get("pct_cobertura")
            if previa is not None and cob_pct is not None:
                pp_cob = float(cob_pct) - float(previa)
        except Exception:
            pp_cob = None
        comp.tarjeta_kpi(
            "Cobertura de costos", _pct(cob_pct, 0),
            delta=(f"{pp_cob:+.1f} pp vs {anio - 1}" if pp_cob is not None else None),
            sub=f"sin costo: {comp.soles_corto(cobertura.get('venta_sin_costo'))}",
            ayuda="Parte de la venta del periodo que tiene costo de producción conocido. "
                  "El resto son artículos comprados o sin costo cargado y no entran en "
                  "el margen. Un margen calculado sobre media empresa no es el margen "
                  "de la empresa.",
        )

    # Los dos periodos, uno al lado del otro: si no, alguien compara el margen
    # de medio año contra la venta de ocho meses.
    if fin is not None and fin < corte:
        comp.nota(f"El margen llega hasta {MESES[fin.month - 1]} {anio}; "
                  f"la venta, hasta el {corte.strftime('%d/%m')}.")

    izq, der = st.columns([1.1, 1], gap="large")
    with izq:
        st.caption("Margen mes a mes · barras en soles, línea en %")
        _grafico_margen_mensual(evolucion, key=f"{k}_margen_mensual")
    with der:
        st.caption("Margen % por producto · los 12 que más venden")
        base = (productos.head(12).sort_values("MARGEN PCT", ascending=False)
                if not productos.empty else productos)
        _grafico_margen_producto(base, float(margen_pct or 0), key=f"{k}_margen_prod")

    if not productos.empty:
        # La variación viene en PUNTOS de margen, no en porcentaje de cambio:
        # de 20% a 25% son +5 puntos. Por eso la columna no se rotula con "%".
        col_var = next((c for c in productos.columns
                        if "VAR" in c.upper() and "MARGEN" in c.upper()), None)
        puntos = f"PUNTOS VS {anio - 1}"
        columnas = [c for c in ["PRODUCTO", "VENTA", "COSTO", "MARGEN", "MARGEN PCT",
                                "TM VENDIDAS", col_var] if c and c in productos.columns]
        vista = productos[columnas].rename(columns={
            "MARGEN PCT": "MARGEN %", "TM VENDIDAS": "TM",
            **({col_var: puntos} if col_var else {}),
        })
        comp.tabla(
            vista,
            formatos={"VENTA": "soles", "COSTO": "soles", "MARGEN": "soles",
                      "MARGEN %": "pct", "TM": "numero", puntos: "numero"},
            resaltar=["MARGEN", puntos],
        )

    st.markdown("**Margen por cliente**")
    if clientes.empty:
        st.caption("Sin clientes con costo en el periodo.")
    else:
        # La tabla va por margen en soles, pero la venta queda al lado: el que
        # factura mucho y aparece con poco margen es justo lo que hay que ver.
        linea = _clientes_flojos(clientes, float(margen_pct or 0))
        if linea:
            st.caption(linea)
        columnas = [c for c in ["CLIENTE", "VENTA", "COSTO", "MARGEN", "MARGEN PCT",
                                "COBERTURA PCT"] if c in clientes.columns]
        vista = clientes[columnas].sort_values("MARGEN", ascending=False).rename(columns={
            "MARGEN PCT": "MARGEN %", "COBERTURA PCT": "COBERTURA %"})
        comp.tabla(
            vista,
            formatos={"VENTA": "soles", "COSTO": "soles", "MARGEN": "soles",
                      "MARGEN %": "pct", "COBERTURA %": "pct"},
            resaltar=["MARGEN"],
        )

    sin_costo = cobertura.get("articulos_sin_costo")
    with st.expander("Ventas sin costo asignado"):
        if sin_costo is None or len(sin_costo) == 0:
            st.caption("Toda la venta del periodo tiene costo cargado.")
        else:
            st.caption("Artículos vendidos sin costo de producción conocido: "
                       "su margen no se calcula.")
            # La columna EMPRESA sobra: esta pestaña ya es de una sola empresa.
            sin_costo = sin_costo.drop(columns=[c for c in ["EMPRESA", "EMPRESA NOMBRE"]
                                                if c in sin_costo.columns])
            comp.tabla_larga(
                sin_costo,
                formatos={c: "soles" for c in sin_costo.columns
                          if "VENTA" in str(c).upper() or "MARGEN" in str(c).upper()},
                altura=320,
            )


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

    alertas = m.generar_alertas(datos, anio, corte, avance, limite=4, sufijo_ancla=f"_{k}")
    if alertas:
        comp.fila_chips(alertas, maximo=4)

    # ---------------- Mes a mes + precio/volumen ----------------
    izq, der = st.columns([1, 1], gap="large")
    with izq:
        comp.titulo_seccion("Mes a mes")
        disponibles = [a for a in m.anios_disponibles(datos) if a != anio]
        comparar = st.multiselect(
            "Comparar contra", disponibles,
            default=[a for a in [anio - 1] if a in disponibles],
            key=f"{k}_comparar", label_visibility="collapsed",
            placeholder="Comparar contra otros años...",
        )
        comp.grafico_mes_a_mes(
            m.ventas_por_mes_anios(datos, [anio] + list(comparar)), anio,
            altura=330, key=f"{k}_mensual",
        )
    with der:
        pv = m.descomposicion_precio_volumen(datos, anio, corte)
        comp.titulo_seccion("¿Precio o volumen?", _frase_precio_volumen(pv),
                            ancla=f"preciovolumen_{k}")
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
    # Dos graficos arriba y uno ancho abajo: en tres columnas las etiquetas se
    # amontonaban y ninguno terminaba de leerse.
    productos = m.ranking_productos(datos, anio, corte, top=12)
    comp.titulo_seccion("Productos", ancla=f"productos_{k}")
    izq, der = st.columns([1.2, 1], gap="large")
    with izq:
        st.caption("Cuánto vende cada uno")
        comp.grafico_barras_horizontales(
            [p[:38] for p in productos["PRODUCTO"]], productos["VENTA"],
            altura=420, key=f"{k}_prod_barras",
        )
    with der:
        st.caption("Peso de cada uno en el total")
        comp.grafico_treemap(
            [p[:26] for p in productos["PRODUCTO"]], productos["VENTA"],
            altura=420, key=f"{k}_prod_treemap",
        )

    disp = productos.dropna(subset=["VAR CANTIDAD PCT", "VAR PRECIO PCT"])
    if len(disp) >= 2:
        st.markdown(f"**Qué le pasó a cada producto frente a {anio - 1}**")
        st.caption(
            "Cada burbuja es un producto y su tamaño es cuánto vende. "
            "Hacia la derecha se despacha más cantidad; hacia arriba se cobra mejor precio."
        )
        comp.grafico_dispersion(
            disp["VAR CANTIDAD PCT"].clip(-100, 200),
            disp["VAR PRECIO PCT"].clip(-100, 200),
            [p[:30] for p in disp["PRODUCTO"]], tamanos=disp["VENTA"],
            titulo_x=f"Cantidad vendida vs {anio - 1}",
            titulo_y=f"Precio promedio vs {anio - 1}",
            altura=430, key=f"{k}_dispersion",
        )
    else:
        st.caption("Sin productos comparables contra el año anterior.")

    # ---------------- Rentabilidad ----------------
    # Solo aparece cuando se cargó el archivo de costos de producción.
    _seccion_rentabilidad(datos, anio, corte, k)

    # ---------------- Clientes ----------------
    comp.titulo_seccion("Clientes", ancla=f"clientes_{k}")
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
        # Dos graficos con escala propia en vez de uno divergente: las subidas
        # son de otro orden de magnitud que las caidas y, juntas, estas ultimas
        # quedaban como lineas sin etiqueta legible.
        variaciones = m.variaciones_clientes(datos, anio, corte, top=6)
        suben, bajan = variaciones["suben"], variaciones["bajan"]
        if not suben.empty:
            st.caption(f"Los que más crecieron vs {anio - 1}")
            comp.grafico_barras_variacion(
                [c[:26] for c in suben["CLIENTE"]], suben["VARIACION"],
                altura=190, key=f"{k}_suben",
            )
        if not bajan.empty:
            st.caption(f"Los que más cayeron vs {anio - 1}")
            comp.grafico_barras_variacion(
                [c[:26] for c in bajan["CLIENTE"]], bajan["VARIACION"].abs() * -1,
                altura=190, key=f"{k}_bajan",
            )
        if suben.empty and bajan.empty:
            st.caption("Sin movimientos comparables contra el año anterior.")

    # ---------------- Listas accionables ----------------
    izq, der = st.columns(2, gap="large")
    with izq:
        comp.titulo_seccion("Se están enfriando", "Contra el ritmo propio de cada cliente",
                            ancla=f"riesgo_{k}")
        riesgo = m.clientes_en_riesgo(datos, corte, top=12)
        if riesgo.empty:
            st.caption("Ningún cliente habitual está retrasado.")
        else:
            # Encabezados cortos: los nombres largos obligaban a desplazar la
            # tabla en horizontal para ver las ultimas columnas.
            vista = riesgo[["CLIENTE", "ULTIMA COMPRA", "DIAS SIN COMPRAR",
                            "RITMO HABITUAL (DIAS)", "VENTA 12M"]].rename(columns={
                "ULTIMA COMPRA": "ÚLTIMA", "DIAS SIN COMPRAR": "DÍAS SIN",
                "RITMO HABITUAL (DIAS)": "SU RITMO", "VENTA 12M": "VENTA 12 MESES"})
            comp.tabla(
                vista,
                formatos={"ÚLTIMA": "fecha", "DÍAS SIN": "entero",
                          "SU RITMO": "entero", "VENTA 12 MESES": "soles"},
            )
    with der:
        comp.titulo_seccion("Dejaron de comprar", f"Compraban en {anio - 1}, este año no",
                            ancla=f"perdidos_{k}")
        perdidos = m.detalle_clientes_perdidos(datos, anio, corte, top=12)
        if perdidos.empty:
            st.caption("Ningún cliente del año pasado dejó de comprar.")
        else:
            vista = perdidos[["CLIENTE", "VENTA ANTERIOR", "ULTIMA COMPRA",
                              "DIAS SIN COMPRAR"]].rename(columns={
                "VENTA ANTERIOR": f"COMPRÓ EN {anio - 1}", "ULTIMA COMPRA": "ÚLTIMA",
                "DIAS SIN COMPRAR": "DÍAS SIN"})
            comp.tabla(
                vista,
                formatos={f"COMPRÓ EN {anio - 1}": "soles", "ÚLTIMA": "fecha",
                          "DÍAS SIN": "entero"},
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
