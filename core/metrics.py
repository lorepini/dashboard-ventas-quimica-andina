"""
Motor de indicadores del dashboard de ventas.

Todas las comparaciones contra el año anterior usan el MISMO periodo transcurrido
(hasta el mismo día del año que la fecha de corte). Comparar un año incompleto
contra uno completo era el defecto principal del reporte anterior: mostraba todo
en rojo sin que eso significara nada.

Convenciones:
- 'VENTA' es el valor de venta sin IGV. Las notas de credito ya llegan en
  negativo, de modo que sumar la columna netea las devoluciones.
- 'RUC' identifica al cliente. Nunca se agrupa por nombre, porque el mismo
  cliente aparece escrito de varias formas en la fuente.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Un cliente necesita al menos esta cantidad de compras para que su ritmo
# historico sea confiable y podamos decir que "dejo de comprar".
MIN_COMPRAS_PARA_RITMO = 3

# Nunca alertamos por un cliente que lleva menos de estos dias sin comprar,
# aunque su ritmo sea muy frecuente.
DIAS_MINIMOS_RIESGO = 30


# ---------------------------------------------------------------------------
# Utilidades de periodo
# ---------------------------------------------------------------------------

def fecha_corte(df: pd.DataFrame) -> pd.Timestamp:
    """Ultima fecha con movimiento en la data cargada."""
    return pd.Timestamp(df["FECHA"].max())


def anios_disponibles(df: pd.DataFrame) -> list[int]:
    """Años con movimiento, del mas reciente al mas antiguo."""
    return sorted(df["ANIO"].dropna().unique().astype(int), reverse=True)


def acumulado_a_la_fecha(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> pd.DataFrame:
    """Filas del año indicado hasta el mismo dia del año que la fecha de corte."""
    limite = corte.dayofyear
    return df[(df["ANIO"] == anio) & (df["DIA DEL ANIO"] <= limite)]


def _variacion(actual: float, anterior: float) -> float | None:
    """Variacion porcentual, o None cuando la base no permite calcularla."""
    if anterior is None or anterior == 0 or pd.isna(anterior):
        return None
    return (actual - anterior) / abs(anterior) * 100


# ---------------------------------------------------------------------------
# Indicadores principales
# ---------------------------------------------------------------------------

def kpis_periodo(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> dict:
    """
    Indicadores de cabecera del año, comparados contra el mismo periodo del año anterior.

    Devuelve venta, numero de clientes, comprobantes, ticket promedio, promedio
    mensual y notas de credito, cada uno con su variacion interanual.
    """
    act = acumulado_a_la_fecha(df, anio, corte)
    ant = acumulado_a_la_fecha(df, anio - 1, corte)

    def bloque(datos: pd.DataFrame) -> dict:
        venta = float(datos["VENTA"].sum())
        comprobantes = int(datos["COMPROBANTE"].nunique())
        nc = float(datos.loc[datos["ES NOTA CREDITO"], "VENTA"].sum())
        meses = max(datos["PERIODO"].nunique(), 1)
        return {
            "venta": venta,
            "clientes": int(datos["RUC"].nunique()),
            "comprobantes": comprobantes,
            "ticket_promedio": venta / comprobantes if comprobantes else 0.0,
            "promedio_mensual": venta / meses,
            "notas_credito": abs(nc),
            "pct_notas_credito": abs(nc) / venta * 100 if venta else 0.0,
        }

    actual, anterior = bloque(act), bloque(ant)
    return {
        "anio": anio,
        "corte": corte,
        "actual": actual,
        "anterior": anterior,
        "variaciones": {k: _variacion(actual[k], anterior[k]) for k in actual},
    }


def avance_vs_meta(
    venta_actual: float,
    meta_anual: float | None,
    meta_a_la_fecha: float | None,
) -> dict:
    """
    Compara lo vendido contra la meta anual y contra lo que se deberia llevar a la fecha.

    'cumplimiento_fecha' es el semaforo que importa: mide el ritmo, no el año completo.
    """
    if not meta_anual:
        return {"con_meta": False}

    resultado = {
        "con_meta": True,
        "meta_anual": meta_anual,
        "avance_anual_pct": venta_actual / meta_anual * 100,
        "falta_anual": meta_anual - venta_actual,
    }
    if meta_a_la_fecha:
        resultado["meta_a_la_fecha"] = meta_a_la_fecha
        resultado["cumplimiento_fecha"] = venta_actual / meta_a_la_fecha * 100
        resultado["brecha_fecha"] = venta_actual - meta_a_la_fecha
    return resultado


def proyeccion_cierre(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> dict:
    """
    Estima el cierre del año proyectando el ritmo actual sobre el patron
    estacional de los años anteriores.

    No es un pronostico: es la respuesta a "si seguimos a este ritmo, ¿dónde
    terminamos?". Cuando no hay historia suficiente, extrapola de forma lineal
    por dias transcurridos.
    """
    act = acumulado_a_la_fecha(df, anio, corte)
    venta = float(act["VENTA"].sum())
    dias_transcurridos = corte.dayofyear
    dias_anio = 366 if pd.Timestamp(year=anio, month=12, day=31).dayofyear == 366 else 365

    previos = [a for a in df["ANIO"].dropna().unique().astype(int) if a < anio]
    previos = sorted(previos)[-3:]

    fraccion = None
    if previos:
        base = df[df["ANIO"].isin(previos)]
        total_previo = float(base["VENTA"].sum())
        hasta_corte = float(base[base["DIA DEL ANIO"] <= dias_transcurridos]["VENTA"].sum())
        if total_previo > 0 and hasta_corte > 0:
            fraccion = hasta_corte / total_previo

    if not fraccion or not 0.05 < fraccion < 1.0:
        fraccion = dias_transcurridos / dias_anio
        metodo = "lineal"
    else:
        metodo = "estacional"

    return {
        "proyeccion": venta / fraccion if fraccion else venta,
        "venta_a_la_fecha": venta,
        "avance_del_anio_pct": fraccion * 100,
        "metodo": metodo,
        "anios_base": previos,
    }


# ---------------------------------------------------------------------------
# Series de tiempo
# ---------------------------------------------------------------------------

def ventas_mensuales(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """Venta mes a mes del año indicado junto al año anterior, para comparar en un mismo grafico."""
    filas = []
    for etiqueta, a in [("actual", anio), ("anterior", anio - 1)]:
        serie = (
            df[df["ANIO"] == a].groupby("MES")["VENTA"].sum().reindex(range(1, 13), fill_value=0.0)
        )
        for mes, valor in serie.items():
            filas.append({"MES": mes, "SERIE": etiqueta, "ANIO": a, "VENTA": float(valor)})
    out = pd.DataFrame(filas)
    out["MES NOMBRE"] = out["MES"].map(NOMBRE_MES)
    return out


def ventas_anuales(df: pd.DataFrame) -> pd.DataFrame:
    """Venta total por año, para el historico."""
    out = df.groupby("ANIO", as_index=False)["VENTA"].sum().sort_values("ANIO")
    out["ANIO"] = out["ANIO"].astype(int)
    return out


def estacionalidad(df: pd.DataFrame) -> pd.DataFrame:
    """Matriz año x mes de ventas, para ver el patron estacional de un vistazo."""
    tabla = df.pivot_table(index="ANIO", columns="MES", values="VENTA", aggfunc="sum", fill_value=0.0)
    tabla = tabla.reindex(columns=range(1, 13), fill_value=0.0)
    tabla.index = tabla.index.astype(int)
    return tabla.sort_index(ascending=False)


NOMBRE_MES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Oct", 11: "Nov", 12: "Dic",
}


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

def pareto_clientes(df: pd.DataFrame, anio: int, corte: pd.Timestamp, top: int = 15) -> pd.DataFrame:
    """
    Ranking de clientes del periodo con participacion y acumulado, para leer el 80/20.

    Agrupa por RUC: el mismo cliente venia partido en varias filas por errores
    de escritura del nombre en la fuente.
    """
    act = acumulado_a_la_fecha(df, anio, corte)
    ant = acumulado_a_la_fecha(df, anio - 1, corte)

    ranking = (
        act.groupby(["RUC", "CLIENTE"], as_index=False)
        .agg(VENTA=("VENTA", "sum"), COMPROBANTES=("COMPROBANTE", "nunique"))
        .sort_values("VENTA", ascending=False)
    )
    total = ranking["VENTA"].sum()
    ranking["PARTICIPACION"] = ranking["VENTA"] / total * 100 if total else 0.0
    ranking["ACUMULADO"] = ranking["PARTICIPACION"].cumsum()

    previo = ant.groupby("RUC")["VENTA"].sum()
    ranking["VENTA ANTERIOR"] = ranking["RUC"].map(previo).fillna(0.0)
    ranking["VARIACION"] = ranking["VENTA"] - ranking["VENTA ANTERIOR"]
    ranking["VARIACION PCT"] = ranking.apply(
        lambda r: _variacion(r["VENTA"], r["VENTA ANTERIOR"]), axis=1
    )
    return ranking.head(top).reset_index(drop=True) if top else ranking.reset_index(drop=True)


def concentracion(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> dict:
    """
    Cuanto de la venta depende de pocos clientes.

    Un grupo con 60% de su venta en 3 clientes tiene un riesgo comercial que
    ningun grafico de ventas totales muestra.
    """
    act = acumulado_a_la_fecha(df, anio, corte)
    ventas = act.groupby("RUC")["VENTA"].sum().sort_values(ascending=False)
    total = float(ventas.sum())
    if total <= 0 or ventas.empty:
        return {"total": 0.0, "top1": 0.0, "top5": 0.0, "top10": 0.0, "clientes_80": 0, "clientes": 0}

    acum = ventas.cumsum() / total * 100
    return {
        "total": total,
        "clientes": int(len(ventas)),
        "top1": float(ventas.iloc[:1].sum() / total * 100),
        "top5": float(ventas.iloc[:5].sum() / total * 100),
        "top10": float(ventas.iloc[:10].sum() / total * 100),
        "clientes_80": int((acum < 80).sum() + 1),
    }


def estado_cartera(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> dict:
    """
    Movimiento de la cartera: clientes nuevos, recuperados, retenidos y perdidos.

    - Nuevo: primera compra de su historia en este periodo.
    - Recuperado: ya habia comprado antes, no compro el año pasado, volvio.
    - Retenido: compro este periodo y el mismo periodo del año pasado.
    - Perdido: compro el mismo periodo del año pasado y no ha comprado este.
    """
    act = acumulado_a_la_fecha(df, anio, corte)
    ant = acumulado_a_la_fecha(df, anio - 1, corte)

    hoy = set(act["RUC"])
    ayer = set(ant["RUC"])
    historicos = set(df[df["ANIO"] < anio]["RUC"])

    nuevos = hoy - historicos
    recuperados = (hoy & historicos) - ayer
    retenidos = hoy & ayer
    perdidos = ayer - hoy

    venta_por_ruc_ant = ant.groupby("RUC")["VENTA"].sum()
    venta_por_ruc_act = act.groupby("RUC")["VENTA"].sum()

    return {
        "activos": len(hoy),
        "nuevos": len(nuevos),
        "recuperados": len(recuperados),
        "retenidos": len(retenidos),
        "perdidos": len(perdidos),
        "retencion_pct": len(retenidos) / len(ayer) * 100 if ayer else None,
        "venta_nuevos": float(venta_por_ruc_act.reindex(list(nuevos)).sum()),
        "venta_recuperados": float(venta_por_ruc_act.reindex(list(recuperados)).sum()),
        "venta_perdida": float(venta_por_ruc_ant.reindex(list(perdidos)).sum()),
        "rucs": {
            "nuevos": nuevos,
            "recuperados": recuperados,
            "perdidos": perdidos,
        },
    }


def detalle_clientes_perdidos(df: pd.DataFrame, anio: int, corte: pd.Timestamp, top: int = 15) -> pd.DataFrame:
    """Clientes que compraban el año pasado y este año no, ordenados por lo que dejaron de comprar."""
    estado = estado_cartera(df, anio, corte)
    perdidos = estado["rucs"]["perdidos"]
    if not perdidos:
        return pd.DataFrame(columns=["RUC", "CLIENTE", "VENTA ANTERIOR", "ULTIMA COMPRA", "DIAS SIN COMPRAR"])

    ant = acumulado_a_la_fecha(df, anio - 1, corte)
    resumen = (
        ant[ant["RUC"].isin(perdidos)]
        .groupby(["RUC", "CLIENTE"], as_index=False)
        .agg(**{"VENTA ANTERIOR": ("VENTA", "sum")})
    )
    ultima = df[df["RUC"].isin(perdidos)].groupby("RUC")["FECHA"].max()
    resumen["ULTIMA COMPRA"] = resumen["RUC"].map(ultima)
    resumen["DIAS SIN COMPRAR"] = (corte - resumen["ULTIMA COMPRA"]).dt.days
    return resumen.sort_values("VENTA ANTERIOR", ascending=False).head(top).reset_index(drop=True)


def clientes_en_riesgo(df: pd.DataFrame, corte: pd.Timestamp, top: int = 15) -> pd.DataFrame:
    """
    Clientes que compraban con regularidad y se estan enfriando.

    El umbral no es fijo: se compara contra el ritmo propio de cada cliente.
    Un cliente que compra cada semana y lleva un mes sin comprar es una alerta;
    uno que compra cada seis meses, no. Esta es la lista de llamadas del dia.
    """
    base = df[df["FECHA"] >= corte - pd.DateOffset(years=2)]
    if base.empty:
        return pd.DataFrame()

    compras = (
        base.groupby(["RUC", "CLIENTE", "FECHA"], as_index=False)["VENTA"].sum().sort_values("FECHA")
    )

    filas = []
    for (ruc, cliente), grupo in compras.groupby(["RUC", "CLIENTE"]):
        fechas = grupo["FECHA"]
        if len(fechas) < MIN_COMPRAS_PARA_RITMO:
            continue
        intervalo = fechas.diff().dt.days.dropna()
        ritmo = float(intervalo.median())
        if ritmo <= 0:
            continue
        dias = int((corte - fechas.max()).days)
        if dias < max(DIAS_MINIMOS_RIESGO, ritmo * 2):
            continue
        filas.append({
            "RUC": ruc,
            "CLIENTE": cliente,
            "ULTIMA COMPRA": fechas.max(),
            "DIAS SIN COMPRAR": dias,
            "RITMO HABITUAL (DIAS)": round(ritmo),
            "RETRASO (VECES)": round(dias / ritmo, 1),
            "VENTA 12M": float(grupo[grupo["FECHA"] >= corte - pd.DateOffset(years=1)]["VENTA"].sum()),
            "VENTA 24M": float(grupo["VENTA"].sum()),
        })

    if not filas:
        return pd.DataFrame()

    out = pd.DataFrame(filas)
    # Lo que esta en juego pesa mas que el simple retraso.
    return out.sort_values(["VENTA 12M", "RETRASO (VECES)"], ascending=False).head(top).reset_index(drop=True)


def variaciones_clientes(df: pd.DataFrame, anio: int, corte: pd.Timestamp, top: int = 10) -> dict:
    """Los clientes que mas crecieron y los que mas cayeron en soles, contra el mismo periodo anterior."""
    act = acumulado_a_la_fecha(df, anio, corte).groupby(["RUC", "CLIENTE"])["VENTA"].sum()
    ant = acumulado_a_la_fecha(df, anio - 1, corte).groupby(["RUC", "CLIENTE"])["VENTA"].sum()

    comparativo = pd.concat([act.rename("ACTUAL"), ant.rename("ANTERIOR")], axis=1).fillna(0.0)
    comparativo = comparativo.reset_index()
    comparativo["VARIACION"] = comparativo["ACTUAL"] - comparativo["ANTERIOR"]
    comparativo["VARIACION PCT"] = comparativo.apply(
        lambda r: _variacion(r["ACTUAL"], r["ANTERIOR"]), axis=1
    )

    suben = comparativo[comparativo["VARIACION"] > 0].nlargest(top, "VARIACION")
    bajan = comparativo[comparativo["VARIACION"] < 0].nsmallest(top, "VARIACION")
    return {"suben": suben.reset_index(drop=True), "bajan": bajan.reset_index(drop=True)}


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

def _resumir_articulos(datos: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa venta y cantidad por codigo de articulo.

    Se agrupa SOLO por codigo, nunca por codigo y descripcion: un mismo codigo
    puede venir con descripciones distintas entre empresas (por ejemplo SER005),
    y agrupar por ambas partiria el articulo en dos filas. Como descripcion se
    toma la mas usada.
    """
    resumen = datos.groupby("COD ARTICULO", as_index=False).agg(
        VENTA=("VENTA", "sum"), CANTIDAD=("CANTIDAD", "sum")
    )
    descripciones = (
        datos.groupby("COD ARTICULO")["PRODUCTO"]
        .agg(lambda s: s.value_counts().idxmax())
        .rename("PRODUCTO")
    )
    return resumen.merge(descripciones, on="COD ARTICULO", how="left")


def ranking_productos(df: pd.DataFrame, anio: int, corte: pd.Timestamp, top: int = 15) -> pd.DataFrame:
    """
    Ranking de articulos con cantidad, precio promedio y variacion contra el año anterior.

    El precio promedio se calcula como venta / cantidad, no como promedio de los
    precios unitarios: asi refleja el precio realmente cobrado en el periodo.
    """
    act = acumulado_a_la_fecha(df, anio, corte)
    ant = acumulado_a_la_fecha(df, anio - 1, corte)

    resumir = _resumir_articulos
    ranking = resumir(act).sort_values("VENTA", ascending=False)
    total = ranking["VENTA"].sum()
    ranking["PARTICIPACION"] = ranking["VENTA"] / total * 100 if total else 0.0
    ranking["PRECIO PROMEDIO"] = np.where(
        ranking["CANTIDAD"] > 0, ranking["VENTA"] / ranking["CANTIDAD"], np.nan
    )

    previo = resumir(ant).set_index("COD ARTICULO")
    ranking["VENTA ANTERIOR"] = ranking["COD ARTICULO"].map(previo["VENTA"]).fillna(0.0)
    ranking["CANTIDAD ANTERIOR"] = ranking["COD ARTICULO"].map(previo["CANTIDAD"]).fillna(0.0)
    ranking["PRECIO ANTERIOR"] = np.where(
        ranking["CANTIDAD ANTERIOR"] > 0,
        ranking["VENTA ANTERIOR"] / ranking["CANTIDAD ANTERIOR"],
        np.nan,
    )
    ranking["VAR VENTA PCT"] = ranking.apply(lambda r: _variacion(r["VENTA"], r["VENTA ANTERIOR"]), axis=1)
    ranking["VAR CANTIDAD PCT"] = ranking.apply(
        lambda r: _variacion(r["CANTIDAD"], r["CANTIDAD ANTERIOR"]), axis=1
    )
    ranking["VAR PRECIO PCT"] = ranking.apply(
        lambda r: _variacion(r["PRECIO PROMEDIO"], r["PRECIO ANTERIOR"]), axis=1
    )
    return ranking.head(top).reset_index(drop=True) if top else ranking.reset_index(drop=True)


def descomposicion_precio_volumen(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> dict:
    """
    Separa cuanto de la variacion de ventas vino del precio y cuanto del volumen.

    Es el indicador que le falta al reporte actual: en un negocio de commodities
    quimicos, vender mas soles con menos toneladas y vender mas toneladas con
    precios en caida son situaciones opuestas que hoy se ven identicas.

    Para cada articulo presente en ambos periodos:
        efecto volumen = (Q_actual - Q_anterior) x Precio_anterior
        efecto precio  = (Precio_actual - Precio_anterior) x Q_actual
    Ambos efectos suman exactamente la variacion del articulo. Los articulos que
    solo existen en un periodo se reportan aparte como altas y bajas de catalogo.
    """
    base = df[~df["ES SERVICIO"] & ~df["ES NOTA CREDITO"] & (df["CANTIDAD"] > 0)]
    act = acumulado_a_la_fecha(base, anio, corte)
    ant = acumulado_a_la_fecha(base, anio - 1, corte)

    def resumir(datos: pd.DataFrame) -> pd.DataFrame:
        g = _resumir_articulos(datos)
        g["PRECIO"] = g["VENTA"] / g["CANTIDAD"]
        return g

    a, b = resumir(act), resumir(ant)
    comp = a.merge(
        b.drop(columns="PRODUCTO"), on="COD ARTICULO", how="outer", suffixes=("_ACT", "_ANT")
    )
    comp["PRODUCTO"] = comp["PRODUCTO"].fillna("")

    ambos = comp["CANTIDAD_ACT"].notna() & comp["CANTIDAD_ANT"].notna()
    detalle = comp[ambos].copy()
    detalle["EFECTO VOLUMEN"] = (detalle["CANTIDAD_ACT"] - detalle["CANTIDAD_ANT"]) * detalle["PRECIO_ANT"]
    detalle["EFECTO PRECIO"] = (detalle["PRECIO_ACT"] - detalle["PRECIO_ANT"]) * detalle["CANTIDAD_ACT"]
    detalle["VARIACION"] = detalle["VENTA_ACT"] - detalle["VENTA_ANT"]

    nuevos = float(comp.loc[comp["CANTIDAD_ANT"].isna(), "VENTA_ACT"].sum())
    salieron = float(-comp.loc[comp["CANTIDAD_ACT"].isna(), "VENTA_ANT"].sum())

    return {
        "venta_actual": float(a["VENTA"].sum()),
        "venta_anterior": float(b["VENTA"].sum()),
        "variacion_total": float(a["VENTA"].sum() - b["VENTA"].sum()),
        "efecto_precio": float(detalle["EFECTO PRECIO"].sum()),
        "efecto_volumen": float(detalle["EFECTO VOLUMEN"].sum()),
        "efecto_nuevos": nuevos,
        "efecto_salidas": salieron,
        "detalle": detalle.sort_values("VARIACION").reset_index(drop=True),
    }


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------

def generar_alertas(
    df: pd.DataFrame,
    anio: int,
    corte: pd.Timestamp,
    avance: dict | None = None,
    limite: int = 6,
) -> list[dict]:
    """
    Traduce los indicadores a frases accionables, ordenadas por urgencia.

    Cada alerta tiene 'nivel' (critico / atencion / bueno), 'titulo' y 'detalle'.
    """
    alertas: list[dict] = []
    kpis = kpis_periodo(df, anio, corte)
    var_venta = kpis["variaciones"]["venta"]

    if avance and avance.get("con_meta") and "cumplimiento_fecha" in avance:
        cumpl = avance["cumplimiento_fecha"]
        brecha = avance["brecha_fecha"]
        if cumpl < 90:
            alertas.append({
                "nivel": "critico",
                "titulo": f"Ritmo por debajo de la meta ({cumpl:.0f}% de lo esperado a la fecha)",
                "detalle": f"Faltan S/ {abs(brecha):,.0f} para estar en línea con la meta anual.",
            })
        elif cumpl >= 100:
            alertas.append({
                "nivel": "bueno",
                "titulo": f"Ritmo por encima de la meta ({cumpl:.0f}% de lo esperado a la fecha)",
                "detalle": f"Van S/ {brecha:,.0f} por encima de lo proyectado para esta fecha.",
            })

    if var_venta is not None:
        if var_venta < -5:
            alertas.append({
                "nivel": "critico",
                "titulo": f"Venta {abs(var_venta):.1f}% por debajo del año pasado",
                "detalle": "Comparado contra el mismo periodo del año anterior.",
            })
        elif var_venta > 5:
            alertas.append({
                "nivel": "bueno",
                "titulo": f"Venta {var_venta:.1f}% por encima del año pasado",
                "detalle": "Comparado contra el mismo periodo del año anterior.",
            })

    pv = descomposicion_precio_volumen(df, anio, corte)
    if pv["venta_anterior"] > 0:
        if pv["efecto_precio"] < 0 and abs(pv["efecto_precio"]) > pv["venta_anterior"] * 0.02:
            alertas.append({
                "nivel": "atencion",
                "titulo": f"Caída de precios resta S/ {abs(pv['efecto_precio']):,.0f}",
                "detalle": "Los precios promedio bajaron respecto al año anterior en los mismos productos.",
            })
        if pv["efecto_volumen"] < 0 and abs(pv["efecto_volumen"]) > pv["venta_anterior"] * 0.02:
            alertas.append({
                "nivel": "atencion",
                "titulo": f"Caída de volumen resta S/ {abs(pv['efecto_volumen']):,.0f}",
                "detalle": "Se están despachando menos unidades que el año pasado.",
            })

    cartera = estado_cartera(df, anio, corte)
    if cartera["perdidos"]:
        alertas.append({
            "nivel": "critico" if cartera["venta_perdida"] > kpis["actual"]["venta"] * 0.05 else "atencion",
            "titulo": f"{cartera['perdidos']} clientes dejaron de comprar",
            "detalle": f"Compraron S/ {cartera['venta_perdida']:,.0f} en el mismo periodo del año pasado.",
        })
    if cartera["nuevos"]:
        alertas.append({
            "nivel": "bueno",
            "titulo": f"{cartera['nuevos']} clientes nuevos",
            "detalle": f"Aportaron S/ {cartera['venta_nuevos']:,.0f} este periodo.",
        })

    conc = concentracion(df, anio, corte)
    if conc["top5"] > 50:
        alertas.append({
            "nivel": "atencion",
            "titulo": f"Concentración alta: 5 clientes son el {conc['top5']:.0f}% de la venta",
            "detalle": f"Solo {conc['clientes_80']} clientes explican el 80% del total.",
        })

    riesgo = clientes_en_riesgo(df, corte, top=100)
    if not riesgo.empty:
        en_juego = float(riesgo["VENTA 12M"].sum())
        alertas.append({
            "nivel": "atencion",
            "titulo": f"{len(riesgo)} clientes habituales se están enfriando",
            "detalle": f"Representan S/ {en_juego:,.0f} en los ultimos 12 meses.",
        })

    if kpis["actual"]["pct_notas_credito"] > 3:
        alertas.append({
            "nivel": "atencion",
            "titulo": f"Notas de crédito en {kpis['actual']['pct_notas_credito']:.1f}% de la venta",
            "detalle": f"S/ {kpis['actual']['notas_credito']:,.0f} en devoluciones y ajustes.",
        })

    orden = {"critico": 0, "atencion": 1, "bueno": 2}
    alertas.sort(key=lambda a: orden[a["nivel"]])
    return alertas[:limite]


def resumen_por_empresa(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> pd.DataFrame:
    """Comparativo de las 3 empresas en una sola tabla, para la vista de grupo."""
    filas = []
    for empresa in df["EMPRESA"].dropna().unique():
        sub = df[df["EMPRESA"] == empresa]
        k = kpis_periodo(sub, anio, corte)
        filas.append({
            "EMPRESA": empresa,
            "EMPRESA NOMBRE": sub["EMPRESA NOMBRE"].iloc[0],
            "VENTA": k["actual"]["venta"],
            "VENTA ANTERIOR": k["anterior"]["venta"],
            "VARIACION PCT": k["variaciones"]["venta"],
            "CLIENTES": k["actual"]["clientes"],
            "COMPROBANTES": k["actual"]["comprobantes"],
            "TICKET PROMEDIO": k["actual"]["ticket_promedio"],
        })
    out = pd.DataFrame(filas)
    total = out["VENTA"].sum()
    out["PARTICIPACION"] = out["VENTA"] / total * 100 if total else 0.0
    return out.sort_values("VENTA", ascending=False).reset_index(drop=True)
