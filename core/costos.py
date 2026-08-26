"""
Cruce del costo de produccion mensual con las ventas, para calcular margen.

El archivo de costos ('BD 2025-2026.xlsx', hoja BD) llega mensualmente junto a
los reporteadores y es OPCIONAL: sin el, el dashboard funciona igual, solo que
sin la seccion de margen.

Tres cosas hay que entender antes de tocar este modulo:

1. UNIDADES. El reporteador entrega la CANTIDAD en la unidad de cada empresa:
   Quimand factura en KILOS y Dogaresa y Yeso en TONELADAS. Los costos siempre
   vienen en TM. Por eso todo pasa primero por FACTOR_A_TM; sin esa conversion
   el margen de Quimand saldria mil veces mayor.

2. MAPEO. El costeo agrupa la produccion en 19 "productos" con nombres cortos
   (PAC105, Tiza, Calmax...) que no coinciden con los codigos de articulo de la
   venta. MAPA_PRODUCTOS es esa tabla, escrita a mano y justificada con el
   volumen producido contra el volumen vendido del mismo año. No se adivina en
   tiempo de ejecucion: un cruce equivocado inventa margen.

3. HUECOS DECLARADOS. Hay articulos que se compran para revender (el cloro a
   granel, la cal hidratada, el cloruro ferrico) y no tienen costo de produccion.
   Quedan explicitamente SIN COSTO: es preferible un hueco visible a un margen
   inventado. Por eso toda la seccion de margen se acompaña del % de cobertura.

Ademas, el costo llega hasta un mes cerrado (hoy junio 2026) mientras la venta
llega hasta la fecha de corte. El margen NUNCA se extrapola: se calcula solo
hasta el ultimo mes con costo, y ese mes se expone para que la UI lo diga.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Empresas y unidades
# ---------------------------------------------------------------------------

# El archivo de costos identifica a las empresas con siglas propias.
EMPRESA_COSTOS: dict[str, str] = {
    "QA": "QUIMAND",    # Ind. y Comercial Quimica Andina
    "SMD": "DOGARESA",  # Sociedad Minera Dogaresa
    "YLL": "YESO",      # Yeso La Limeña
}

# Cuanto vale una unidad de CANTIDAD del reporteador expresada en toneladas.
#
# Comprobado contra la produccion real de 2025:
#   QUIMAND  PAC105       vendio 2,984,400 (kilos) vs produjo 2,998.55 TM -> factor 1/1000
#   DOGARESA Gallina      vendio       739.01      vs produjo   738.36 TM -> factor 1
#   YESO     Construccion vendio     1,109.39      vs produjo 1,102.65 TM -> factor 1
FACTOR_A_TM: dict[str, float] = {
    "QUIMAND": 0.001,
    "DOGARESA": 1.0,
    "YESO": 1.0,
}


# ---------------------------------------------------------------------------
# Mapeo producto de costeo -> codigos de articulo de venta
# ---------------------------------------------------------------------------
#
# Criterio: para cada producto de costeo se comparan las TM producidas contra
# las TM vendidas de los articulos candidatos en el mismo periodo. El comentario
# de cada linea deja escrito el par de cifras que justifica el emparejamiento.
# Las diferencias moderadas (+-20%) son normales: se produce contra stock.
#
# Los productos que solo existen en 2026 se justifican con enero-junio 2026.

MAPA_PRODUCTOS: dict[str, dict[str, list[str]]] = {
    "QUIMAND": {
        # 416.75 TM producidas vs 416.56 TM vendidas en 2025 (100.0%).
        # OJO: es el cloro EN CILINDROS, no el granel C003CLL00.
        "Cloro Líquido": ["C003CLL02"],
        # 47.53 TM producidas vs 45.25 TM vendidas en 2025 (95%).
        # El hipoclorito IMPORTADO (AQUIM10 / AQUIM11) es reventa: no entra.
        "Hipoclorito": ["E005HC001"],
        # 238.54 TM producidas vs 213.65 TM vendidas en 2025 (90%).
        # Sumando 2025 + ene-jun 2026: 330.20 producidas vs 337.24 vendidas (102%).
        "PAC10": ["E004PAC10"],
        # 2,998.55 TM producidas vs 2,984.40 TM vendidas en 2025 (99.5%).
        "PAC105": ["E004PACS105"],
    },
    "DOGARESA": {
        # 2,832.78 TM producidas vs 2,719.65 TM vendidas en 2025 (96%).
        "Avícola": ["I001AVI"],
        # Producto definido por su cliente: 'Etna' es el carbonato que compra
        # FABRICA NACIONAL DE ACUMULADORES ETNA S.A. bajo el codigo ITIZA
        # (CARBONATO PV 100), articulo que nace en 2026 igual que el costeo.
        # 40.82 TM producidas vs 30.80 TM vendidas en ene-jun 2026 (75%).
        "Etna": ["ITIZA"],
        # 738.36 TM producidas vs 739.01 TM vendidas en 2025 (100.1%).
        "Gallina": ["I001GAL"],
        # 238.28 TM producidas vs 189.00 TM vendidas en 2025 (79%).
        "JJGrueso": ["I001JJG"],
        # 109.20 TM producidas vs 60.00 TM vendidas en ene-jun 2026 (55%).
        # Coincidencia exacta de nombre (CARBONATO DE CALCIO M100) y ambos
        # aparecen recien en 2026; la diferencia es acumulacion de stock.
        "M100": ["I001M100"],
        # Igual que Etna: 'Soldexa' es el carbonato de SOLDEX S.A.
        # 355.51 TM producidas vs 400.00 TM vendidas en 2025 (112%).
        "Soldexa": ["I001SOL"],
        # 1,331.32 TM producidas vs 1,320.30 TM vendidas en 2025 (99.2%).
        "Tandol": ["I001TAN"],
        # 4,670.23 TM producidas vs 4,771.32 TM vendidas en 2025 (102%),
        # sumando CARBONATO DE CALCIO - F (4,771.20) y TIZA MANGA (0.12).
        # I002TIZ25A es el mismo CARBONATO DE CALCIO - F en presentacion chica
        # (0.25 TM en 2026, nada en 2025), va con el granel.
        # NO incluye I001PISO (CARBONATO DE CALCIO PISO, 1,425.60 TM en 2025):
        # sumarlo llevaria lo vendido a 6,197 TM contra 4,670 producidas.
        "Tiza": ["I002TIZ1000A", "I002TIZ25A", "I001TMA"],
    },
    "YESO": {
        # 663.00 TM producidas vs 692.80 TM vendidas en 2025 (104.5%).
        "Agrícola": ["I004YEF"],
        # 4.70 TM producidas vs 4.70 TM vendidas en ene-jun 2026 (100%).
        # Nombre identico en costeo y en catalogo (CALCIUM 325).
        "Calcium 325": ["I006YEM"],
        # 164.60 TM producidas vs 122.63 TM vendidas en 2025 (74.5%).
        # El catalogo lo nombra literalmente YESO MOLIDO (CALMAX).
        "Calmax": ["I005YEM"],
        # 1,002.26 TM producidas vs 1,215.10 TM vendidas en 2025 (121%).
        # Es el unico ceramico a granel del catalogo; el exceso vendido sale de
        # stock. No incluye TEREYESO ni YESO CERAMICO DP (ver SIN_COSTO_DECLARADO).
        "Cerámico": ["I002YE20"],
        # 5.78 TM producidas vs 5.62 TM vendidas en ene-jun 2026 (97%).
        "Cerámico 1 Kg": ["I002YE01"],
        # 1,102.65 TM producidas vs 1,109.39 TM vendidas en 2025 (100.6%).
        "Construcción": ["I001YE25"],
        # 66.26 TM producidas vs 40.00 TM vendidas en ene-jun 2026 (60%).
        # El costeo de DP 220 arranca en abril 2026; el articulo YESO DP 220 ya
        # existia antes, de modo que los años previos quedan sin costo.
        "DP 220": ["I001YE220"],
    },
}

# Articulos de peso que a proposito NO llevan costo de produccion, con el motivo.
# Se usa para explicar el hueco de cobertura en lugar de dejarlo mudo.
SIN_COSTO_DECLARADO: dict[str, str] = {
    "C003CLL00": "Cloro a granel: se compra para reventa, no se produce.",
    "AQUIM10": "Hipoclorito importado: reventa.",
    "AQUIM101": "Hipoclorito importado: reventa.",
    "AQUIM11": "Hipoclorito importado: reventa.",
    "VMDD004CLFE": "Cloruro ferrico: producto de terceros, reventa.",
    "VMDD004ISUP581": "Superfloc: producto de terceros, reventa.",
    "BSISUPN300": "Superfloc: producto de terceros, reventa.",
    "BSISUPA130": "Superfloc: producto de terceros, reventa.",
    "E001CAS3": "Cal hidratada: no se produce, se comercializa.",
    "E001CAS4": "Cal hidratada: no se produce, se comercializa.",
    "E001CAS8": "Cal hidratada: no se produce, se comercializa.",
    "E001LCAS3": "Cal hidratada: no se produce, se comercializa.",
    "E001CALI1": "Hidroxido de calcio: no se produce, se comercializa.",
    "ASULFADALU": "Sulfato de aluminio: reventa.",
    "E006SULFMAG01": "Sulfato de magnesio: reventa.",
    "I001PISO": "Carbonato PISO: no tiene linea de costeo propia (pendiente de confirmar).",
    "I003YEF": "Tereyeso: no tiene linea de costeo propia (pendiente de confirmar).",
    "I001YEDP": "Yeso ceramico DP: no tiene linea de costeo propia (pendiente de confirmar).",
}

# Indice plano (empresa, cod articulo) -> producto de costeo.
_MAPA_ARTICULOS: dict[tuple[str, str], str] = {
    (empresa, cod): producto
    for empresa, productos in MAPA_PRODUCTOS.items()
    for producto, codigos in productos.items()
    for cod in codigos
}


# ---------------------------------------------------------------------------
# Lectura del archivo de costos
# ---------------------------------------------------------------------------

# Nombre normalizado de columna -> nombre interno.
_COLUMNAS_COSTOS = {
    "ano": "ANIO",
    "mes": "MES",
    "empresa": "EMPRESA COSTOS",
    "producto": "PRODUCTO COSTO",
    "producciontm": "TM",
    "materiales": "MATERIALES",
    "manodeobra": "MANO DE OBRA",
    "cif": "CIF",
    "costototal": "COSTO TOTAL",
    "costounitariostm": "COSTO TM",
}

# Sin estas columnas el archivo no es el de costos.
_COLUMNAS_MINIMAS = ["ano", "mes", "empresa", "producto", "producciontm", "costototal"]

COLUMNAS_RESULTADO = [
    "EMPRESA", "ANIO", "MES", "PERIODO", "PRODUCTO COSTO", "TM",
    "COSTO TOTAL", "COSTO TM", "MATERIALES", "MANO DE OBRA", "CIF",
]


@dataclass
class ResultadoCostos:
    """Resultado de cargar el archivo de costos, con diagnostico para el usuario."""

    df: pd.DataFrame
    filas_leidas: int
    filas_validas: int
    ultimo_periodo: dict[str, pd.Timestamp] = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)


def _clave_columna(nombre) -> str:
    """Normaliza el nombre de una columna para compararlo sin tildes ni simbolos."""
    base = unicodedata.normalize("NFKD", str(nombre).upper())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", base).lower()


def _rebobinar(fuente) -> None:
    """Deja un archivo subido por Streamlit listo para volver a leerse."""
    if hasattr(fuente, "seek"):
        try:
            fuente.seek(0)
        except (OSError, ValueError):
            pass


def _hojas(fuente) -> dict[str, pd.DataFrame]:
    """Lee todas las hojas del libro, sin suponer como se llama la buena."""
    _rebobinar(fuente)
    hojas = pd.read_excel(fuente, sheet_name=None)
    _rebobinar(fuente)
    return hojas


def _hoja_de_costos(hojas: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """Elige la hoja que tiene la estructura de costos; None si ninguna la tiene."""
    for df in hojas.values():
        claves = {_clave_columna(c) for c in df.columns}
        if all(c in claves for c in _COLUMNAS_MINIMAS):
            return df
    return None


def es_archivo_costos(fuente) -> bool:
    """
    Dice si un archivo es el de costos de produccion, mirando su ESTRUCTURA.

    Se decide por las columnas y no por el nombre del archivo, porque el nombre
    cambia cada mes ('BD 2025-2026.xlsx' hoy, otro mañana).
    """
    try:
        return _hoja_de_costos(_hojas(fuente)) is not None
    except Exception:
        return False


def cargar_costos(fuente) -> ResultadoCostos:
    """
    Lee el archivo de costos de produccion y devuelve el detalle mensual limpio.

    `fuente` puede ser una ruta o un archivo subido por Streamlit.

    Descarta las filas de relleno (sin empresa) y deja el costo unitario en NaN
    en los meses sin produccion: un mes que no produjo NO tiene costo cero, tiene
    costo desconocido, y confundir ambas cosas regala margen.
    """
    advertencias: list[str] = []
    hojas = _hojas(fuente)
    crudo = _hoja_de_costos(hojas)
    if crudo is None:
        raise ValueError(
            "El archivo no tiene la estructura del reporte de costos. Se esperan "
            "las columnas Año, Mes, Empresa, Producto, Producción (TM) y Costo Total."
        )

    filas_leidas = len(crudo)
    df = crudo.rename(columns={c: _clave_columna(c) for c in crudo.columns})
    df = df.rename(columns=_COLUMNAS_COSTOS)
    df = df[[c for c in _COLUMNAS_COSTOS.values() if c in df.columns]].copy()

    for col in ["MATERIALES", "MANO DE OBRA", "CIF", "COSTO TM"]:
        if col not in df.columns:
            df[col] = np.nan

    # Las filas de relleno del final del libro no tienen empresa.
    df["EMPRESA COSTOS"] = df["EMPRESA COSTOS"].astype(str).str.strip().str.upper()
    sin_empresa = ~df["EMPRESA COSTOS"].isin(EMPRESA_COSTOS)
    descartadas = int(sin_empresa.sum())
    if descartadas:
        desconocidas = sorted(
            set(df.loc[sin_empresa, "EMPRESA COSTOS"]) - {"NAN", ""}
        )
        if desconocidas:
            advertencias.append(
                f"Siglas de empresa no reconocidas en el archivo de costos: "
                f"{', '.join(desconocidas)}."
            )
    df = df[~sin_empresa].copy()
    df["EMPRESA"] = df["EMPRESA COSTOS"].map(EMPRESA_COSTOS)

    for col in ["ANIO", "MES", "TM", "COSTO TOTAL", "COSTO TM", "MATERIALES", "MANO DE OBRA", "CIF"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[df["ANIO"].notna() & df["MES"].notna()].copy()
    df["ANIO"] = df["ANIO"].astype(int)
    df["MES"] = df["MES"].astype(int)
    df["PRODUCTO COSTO"] = df["PRODUCTO COSTO"].astype(str).str.strip()

    # El costo unitario se recalcula: el del archivo viene en blanco cuando la
    # produccion fue cero y no siempre acompaña a las columnas de detalle.
    calculado = np.where(df["TM"] > 0, df["COSTO TOTAL"] / df["TM"], np.nan)
    df["COSTO TM"] = np.where(df["TM"] > 0, calculado, np.nan)

    meses_sin_produccion = int((df["TM"].fillna(0) <= 0).sum())
    if meses_sin_produccion:
        advertencias.append(
            f"{meses_sin_produccion} filas son meses sin produccion: quedan sin "
            "costo unitario y las ventas de ese mes no reciben costo."
        )

    df["PERIODO"] = pd.to_datetime(
        dict(year=df["ANIO"], month=df["MES"], day=1), errors="coerce"
    )
    df = df[df["PERIODO"].notna()]

    # Un mismo producto no deberia repetirse en un mes; si pasa, se consolida.
    claves = ["EMPRESA", "ANIO", "MES", "PRODUCTO COSTO"]
    duplicados = int(df.duplicated(claves).sum())
    if duplicados:
        advertencias.append(
            f"{duplicados} filas repetidas (misma empresa, mes y producto) fueron "
            "sumadas en una sola."
        )
        agregado = df.groupby(claves, as_index=False).agg(
            {
                "TM": "sum", "COSTO TOTAL": "sum", "MATERIALES": "sum",
                "MANO DE OBRA": "sum", "CIF": "sum", "PERIODO": "first",
            }
        )
        agregado["COSTO TM"] = np.where(
            agregado["TM"] > 0, agregado["COSTO TOTAL"] / agregado["TM"], np.nan
        )
        df = agregado

    advertencias.extend(_revisar_mapeo(df))

    df = df[COLUMNAS_RESULTADO].reset_index(drop=True)

    ultimo_periodo = {}
    for empresa in df["EMPRESA"].unique():
        periodo = ultimo_mes_con_costo(df, empresa)
        if periodo is not None:
            ultimo_periodo[empresa] = periodo

    return ResultadoCostos(
        df=df,
        filas_leidas=filas_leidas,
        filas_validas=len(df),
        ultimo_periodo=ultimo_periodo,
        advertencias=advertencias,
    )


def _revisar_mapeo(df: pd.DataFrame) -> list[str]:
    """Avisa de productos de costeo que el mapeo no cubre, para que el hueco se vea."""
    avisos: list[str] = []
    for empresa, grupo in df.groupby("EMPRESA"):
        conocidos = MAPA_PRODUCTOS.get(empresa, {})
        for producto in sorted(grupo["PRODUCTO COSTO"].unique()):
            if producto not in conocidos:
                avisos.append(
                    f"{empresa}: el producto de costeo '{producto}' no esta en el "
                    "mapeo de articulos, su costo no se aplicara a ninguna venta."
                )
            elif not conocidos[producto]:
                avisos.append(
                    f"{empresa}: el producto de costeo '{producto}' esta declarado "
                    "sin articulo de venta equivalente."
                )
    return avisos


def ultimo_mes_con_costo(costos_df: pd.DataFrame, empresa: str | None = None) -> pd.Timestamp | None:
    """
    Ultimo mes que tiene costo unitario calculable, en general o de una empresa.

    Es el limite duro del analisis de margen: mas alla de esta fecha hay venta
    pero no hay costo, y estimarlo seria inventar el resultado.
    """
    if costos_df is None or costos_df.empty:
        return None
    base = costos_df[costos_df["COSTO TM"].notna() & (costos_df["COSTO TM"] > 0)]
    if empresa:
        base = base[base["EMPRESA"] == empresa]
    if base.empty:
        return None
    return pd.Timestamp(base["PERIODO"].max())


# ---------------------------------------------------------------------------
# Cruce con las ventas
# ---------------------------------------------------------------------------

COLUMNAS_MARGEN = ["TM VENDIDAS", "COSTO TM", "COSTO", "MARGEN", "TIENE COSTO"]


def _bandera(df: pd.DataFrame, columna: str) -> pd.Series:
    """Columna booleana del detalle, o todo False si el detalle no la trae."""
    if columna not in df.columns:
        return pd.Series(False, index=df.index)
    return df[columna].fillna(False).astype(bool)


def _sin_costo(ventas: pd.DataFrame) -> pd.DataFrame:
    """Copia de las ventas con las columnas de margen vacias (no hay archivo de costos)."""
    out = ventas.copy()
    out["PRODUCTO COSTO"] = None
    out["TM VENDIDAS"] = np.nan
    out["COSTO TM"] = np.nan
    out["COSTO"] = np.nan
    out["MARGEN"] = np.nan
    out["TIENE COSTO"] = False
    return out


def enriquecer_con_costo(ventas: pd.DataFrame, costos_df: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve una copia de las ventas con el costo de produccion aplicado linea a linea.

    Columnas agregadas:
        PRODUCTO COSTO  producto del costeo al que pertenece el articulo
        TM VENDIDAS     CANTIDAD convertida a toneladas segun la empresa
        COSTO TM        costo unitario DEL MES EN QUE SE VENDIO (no un promedio)
        COSTO           TM VENDIDAS x COSTO TM
        MARGEN          VENTA - COSTO
        TIENE COSTO     si la linea entra o no en el analisis de margen

    Queda con TIENE COSTO en False, y COSTO / MARGEN en NaN:
      - los servicios (fletes, pruebas hidrostaticas, alquileres),
      - las notas de credito,
      - los articulos que no tienen produccion propia (reventa),
      - las ventas de un mes para el que todavia no hay costo,
      - las ventas de un mes en que ese producto no se produjo.

    Nunca se rellena con ceros ni con promedios: una linea sin costo se queda
    sin margen y se cuenta en la cobertura.
    """
    if ventas is None or ventas.empty:
        return _sin_costo(ventas if ventas is not None else pd.DataFrame())
    if costos_df is None or costos_df.empty:
        return _sin_costo(ventas)

    out = ventas.copy()
    empresa = out["EMPRESA"].astype(str)

    es_servicio = _bandera(out, "ES SERVICIO")
    es_nc = _bandera(out, "ES NOTA CREDITO")

    # Conversion de unidades: sin esto Quimand daria un margen mil veces mayor.
    factor = empresa.map(FACTOR_A_TM)
    out["TM VENDIDAS"] = pd.to_numeric(out["CANTIDAD"], errors="coerce") * factor
    out.loc[es_servicio, "TM VENDIDAS"] = np.nan

    codigo = out["COD ARTICULO"].astype(str)
    out["PRODUCTO COSTO"] = [
        _MAPA_ARTICULOS.get(clave) for clave in zip(empresa, codigo)
    ]

    tabla = costos_df.set_index(["EMPRESA", "ANIO", "MES", "PRODUCTO COSTO"])["COSTO TM"]
    tabla = tabla[~tabla.index.duplicated()]
    buscado = pd.MultiIndex.from_arrays(
        [
            empresa,
            pd.to_numeric(out["ANIO"], errors="coerce").fillna(-1).astype(int),
            pd.to_numeric(out["MES"], errors="coerce").fillna(-1).astype(int),
            out["PRODUCTO COSTO"].fillna(""),
        ]
    )
    out["COSTO TM"] = tabla.reindex(buscado).to_numpy()

    aplicable = (
        out["COSTO TM"].notna()
        & (out["COSTO TM"] > 0)
        & out["TM VENDIDAS"].notna()
        & ~es_servicio
        & ~es_nc
    )
    out["TIENE COSTO"] = aplicable.to_numpy()
    out.loc[~out["TIENE COSTO"], "COSTO TM"] = np.nan
    out["COSTO"] = out["TM VENDIDAS"] * out["COSTO TM"]
    out["MARGEN"] = np.where(out["TIENE COSTO"], out["VENTA"] - out["COSTO"], np.nan)
    return out


# ---------------------------------------------------------------------------
# Utilidades de periodo
# ---------------------------------------------------------------------------

def _acumulado(df: pd.DataFrame, anio: int, corte: pd.Timestamp) -> pd.DataFrame:
    """Filas del año hasta el mismo dia del año que la fecha de corte."""
    return df[(df["ANIO"] == anio) & (df["DIA DEL ANIO"] <= corte.dayofyear)]


def corte_con_costo(ventas_enriquecidas: pd.DataFrame, corte: pd.Timestamp) -> pd.Timestamp:
    """
    Adelanta la fecha de corte hasta el fin del ultimo mes que tiene costo.

    Si la venta llega al 17/08 pero el costo llega a junio, el margen se calcula
    al 30/06. Comparar venta de agosto contra costo inexistente no da un margen
    optimista: da un margen falso.
    """
    corte = pd.Timestamp(corte)
    con_costo = ventas_enriquecidas[ventas_enriquecidas["TIENE COSTO"]]
    if con_costo.empty:
        return corte
    ultimo = pd.Timestamp(con_costo["FECHA"].max())
    fin_de_mes = ultimo + pd.offsets.MonthEnd(0)
    return min(corte, fin_de_mes)


def _variacion(actual: float, anterior: float) -> float | None:
    """Variacion porcentual, o None cuando la base no permite calcularla."""
    if anterior is None or anterior == 0 or pd.isna(anterior):
        return None
    return (actual - anterior) / abs(anterior) * 100


def _margen_pct(margen: float, venta: float) -> float | None:
    """Margen sobre venta; None cuando no hay venta que sirva de base."""
    if venta is None or venta == 0 or pd.isna(venta):
        return None
    return margen / venta * 100


# ---------------------------------------------------------------------------
# Indicadores
# ---------------------------------------------------------------------------

def cobertura_costos(ventas_enriquecidas: pd.DataFrame, anio: int, corte: pd.Timestamp) -> dict:
    """
    Que parte de la venta del periodo tiene costo conocido.

    Es el indicador que hay que mostrar ANTES que cualquier margen: con 60% de
    cobertura, un margen de 30% no es el margen del negocio, es el de un pedazo.
    A diferencia del resto de funciones, aqui SI se mira hasta la fecha de corte
    completa, justamente para que se vea el hueco de los meses sin costo.

    Devuelve venta total, venta con costo, % de cobertura, venta sin costo y el
    detalle de los articulos sin costo ordenado por venta, con el motivo.
    """
    act = _acumulado(ventas_enriquecidas, anio, pd.Timestamp(corte))
    venta_total = float(act["VENTA"].sum())
    con_costo = act[act["TIENE COSTO"]]
    venta_con_costo = float(con_costo["VENTA"].sum())

    sin_costo = act[~act["TIENE COSTO"]].copy()
    if sin_costo.empty:
        detalle = pd.DataFrame(
            columns=["EMPRESA", "COD ARTICULO", "PRODUCTO", "VENTA", "MOTIVO"]
        )
    else:
        sin_costo["MOTIVO"] = _motivos(sin_costo)
        detalle = (
            sin_costo.groupby(["EMPRESA", "COD ARTICULO"], as_index=False, observed=True)
            .agg(
                PRODUCTO=("PRODUCTO", lambda s: s.value_counts().idxmax()),
                VENTA=("VENTA", "sum"),
                MOTIVO=("MOTIVO", lambda s: s.value_counts().idxmax()),
            )
            .sort_values("VENTA", ascending=False)
            .reset_index(drop=True)
        )

    return {
        "venta_total": venta_total,
        "venta_con_costo": venta_con_costo,
        "pct_cobertura": venta_con_costo / venta_total * 100 if venta_total else 0.0,
        "venta_sin_costo": venta_total - venta_con_costo,
        "articulos_sin_costo": detalle,
    }


def _motivos(sin_costo: pd.DataFrame) -> pd.Series:
    """Explica, linea a linea, por que esa venta no lleva costo."""
    motivo = pd.Series("Sin costo de produccion registrado", index=sin_costo.index, dtype=object)

    es_servicio = _bandera(sin_costo, "ES SERVICIO")
    es_nc = _bandera(sin_costo, "ES NOTA CREDITO")
    mapeado = (
        sin_costo["PRODUCTO COSTO"].notna()
        if "PRODUCTO COSTO" in sin_costo.columns
        else pd.Series(False, index=sin_costo.index)
    )

    # Articulo que si tiene mapeo, pero cuyo mes todavia no trae costo (o no
    # produjo nada ese mes).
    motivo[mapeado & ~es_servicio & ~es_nc] = "Mes sin costo disponible todavia"

    # Los articulos de reventa declarados explican su propio hueco.
    declarado = sin_costo["COD ARTICULO"].map(SIN_COSTO_DECLARADO)
    motivo[declarado.notna()] = declarado[declarado.notna()]

    # Servicio y nota de credito mandan sobre cualquier otro motivo.
    motivo[es_servicio] = "Servicio: no lleva costo de produccion"
    motivo[es_nc] = "Nota de credito"
    return motivo


def kpis_margen(ventas_enriquecidas: pd.DataFrame, anio: int, corte: pd.Timestamp) -> dict:
    """
    Venta, costo y margen del periodo, contra el mismo periodo del año anterior.

    Dos restricciones que hay que tener presentes al leer estos numeros:

    1. Solo entran las lineas con TIENE COSTO = True. La 'venta' de este bloque
       NO es la venta total de la empresa, es la venta de lo que se produce.
       Para saber cuanto representa, usar cobertura_costos().
    2. El periodo se recorta hasta el ULTIMO MES CON COSTO. Si la venta llega al
       17/08 y el costo a junio, ambos años se comparan al 30/06. El campo
       'corte_efectivo' dice hasta donde se calculo y 'corte_recortado' avisa si
       hubo recorte, para que la UI lo muestre.
    """
    corte = pd.Timestamp(corte)
    efectivo = corte_con_costo(ventas_enriquecidas, corte)
    base = ventas_enriquecidas[ventas_enriquecidas["TIENE COSTO"]]

    def bloque(datos: pd.DataFrame) -> dict:
        venta = float(datos["VENTA"].sum())
        costo = float(datos["COSTO"].sum())
        margen = venta - costo
        tm = float(datos["TM VENDIDAS"].sum())
        return {
            "venta": venta,
            "costo": costo,
            "margen": margen,
            "margen_pct": _margen_pct(margen, venta) or 0.0,
            "tm": tm,
            "precio_promedio": venta / tm if tm else 0.0,
            "costo_promedio": costo / tm if tm else 0.0,
        }

    actual = bloque(_acumulado(base, anio, efectivo))
    anterior = bloque(_acumulado(base, anio - 1, efectivo))

    return {
        "anio": anio,
        "corte": corte,
        "corte_efectivo": efectivo,
        "corte_recortado": bool(efectivo < corte),
        "venta": actual["venta"],
        "costo": actual["costo"],
        "margen": actual["margen"],
        "margen_pct": actual["margen_pct"],
        "actual": actual,
        "anterior": anterior,
        "variaciones": {k: _variacion(actual[k], anterior[k]) for k in actual},
    }


def margen_por_producto(
    ventas_enriquecidas: pd.DataFrame, anio: int, corte: pd.Timestamp, top: int = 15
) -> pd.DataFrame:
    """
    Margen por articulo, ordenado por margen en soles.

    Solo articulos con costo conocido y solo hasta el ultimo mes con costo.
    El precio y el costo promedio se calculan por tonelada vendida, de modo que
    se pueden leer uno al lado del otro. 'VAR MARGEN PCT' esta en PUNTOS
    porcentuales contra el mismo periodo del año anterior, no en variacion
    relativa: pasar de 20% a 25% son +5 puntos.
    """
    efectivo = corte_con_costo(ventas_enriquecidas, pd.Timestamp(corte))
    base = ventas_enriquecidas[ventas_enriquecidas["TIENE COSTO"]]

    def resumir(datos: pd.DataFrame) -> pd.DataFrame:
        if datos.empty:
            return pd.DataFrame(
                columns=["COD ARTICULO", "PRODUCTO", "VENTA", "COSTO", "TM VENDIDAS"]
            )
        resumen = datos.groupby("COD ARTICULO", as_index=False, observed=True).agg(
            VENTA=("VENTA", "sum"), COSTO=("COSTO", "sum"),
            **{"TM VENDIDAS": ("TM VENDIDAS", "sum")},
        )
        # Se agrupa solo por codigo: la descripcion puede variar entre filas.
        descripcion = (
            datos.groupby("COD ARTICULO", observed=True)["PRODUCTO"]
            .agg(lambda s: s.value_counts().idxmax())
            .rename("PRODUCTO")
        )
        return resumen.merge(descripcion, on="COD ARTICULO", how="left")

    act = resumir(_acumulado(base, anio, efectivo))
    ant = resumir(_acumulado(base, anio - 1, efectivo))
    if act.empty:
        return pd.DataFrame(
            columns=[
                "COD ARTICULO", "PRODUCTO", "VENTA", "COSTO", "MARGEN", "MARGEN PCT",
                "TM VENDIDAS", "PRECIO PROMEDIO", "COSTO PROMEDIO",
                "MARGEN PCT ANTERIOR", "VAR MARGEN PCT",
            ]
        )

    act["MARGEN"] = act["VENTA"] - act["COSTO"]
    act["MARGEN PCT"] = np.where(
        act["VENTA"] != 0, act["MARGEN"] / act["VENTA"] * 100, np.nan
    )
    act["PRECIO PROMEDIO"] = np.where(
        act["TM VENDIDAS"] > 0, act["VENTA"] / act["TM VENDIDAS"], np.nan
    )
    act["COSTO PROMEDIO"] = np.where(
        act["TM VENDIDAS"] > 0, act["COSTO"] / act["TM VENDIDAS"], np.nan
    )

    if ant.empty:
        act["MARGEN PCT ANTERIOR"] = np.nan
    else:
        previo = ant.set_index("COD ARTICULO")
        margen_ant = previo["VENTA"] - previo["COSTO"]
        pct_ant = np.where(previo["VENTA"] != 0, margen_ant / previo["VENTA"] * 100, np.nan)
        act["MARGEN PCT ANTERIOR"] = act["COD ARTICULO"].map(
            pd.Series(pct_ant, index=previo.index)
        )
    act["VAR MARGEN PCT"] = act["MARGEN PCT"] - act["MARGEN PCT ANTERIOR"]

    columnas = [
        "COD ARTICULO", "PRODUCTO", "VENTA", "COSTO", "MARGEN", "MARGEN PCT",
        "TM VENDIDAS", "PRECIO PROMEDIO", "COSTO PROMEDIO",
        "MARGEN PCT ANTERIOR", "VAR MARGEN PCT",
    ]
    salida = act[columnas].sort_values("MARGEN", ascending=False)
    return salida.head(top).reset_index(drop=True) if top else salida.reset_index(drop=True)


def margen_por_cliente(
    ventas_enriquecidas: pd.DataFrame, anio: int, corte: pd.Timestamp, top: int = 15
) -> pd.DataFrame:
    """
    Margen por cliente, ordenado por margen en soles.

    VENTA, COSTO y MARGEN son solo de lo que tiene costo conocido; COBERTURA PCT
    dice que parte de la compra total de ese cliente esta cubierta. Sin ese dato
    el margen % engaña: un cliente que compra sobre todo mercaderia de reventa
    puede aparecer con un margen excelente calculado sobre una minima parte de lo
    que compra. Se agrupa por RUC, nunca por nombre.

    La cobertura se mide contra la venta del cliente SIN las notas de credito,
    a ambos lados de la division: si se netearan solo en el denominador, un
    cliente con devoluciones grandes daria una cobertura mayor al 100%.
    """
    efectivo = corte_con_costo(ventas_enriquecidas, pd.Timestamp(corte))
    act = _acumulado(ventas_enriquecidas, anio, efectivo)
    if act.empty:
        return pd.DataFrame(
            columns=["RUC", "CLIENTE", "VENTA", "COSTO", "MARGEN", "MARGEN PCT", "COBERTURA PCT"]
        )

    facturado = act[~_bandera(act, "ES NOTA CREDITO")]
    venta_total = facturado.groupby("RUC", observed=True)["VENTA"].sum()

    con_costo = act[act["TIENE COSTO"]]
    if con_costo.empty:
        return pd.DataFrame(
            columns=["RUC", "CLIENTE", "VENTA", "COSTO", "MARGEN", "MARGEN PCT", "COBERTURA PCT"]
        )

    resumen = con_costo.groupby(["RUC", "CLIENTE"], as_index=False, observed=True).agg(
        VENTA=("VENTA", "sum"), COSTO=("COSTO", "sum")
    )
    resumen["MARGEN"] = resumen["VENTA"] - resumen["COSTO"]
    resumen["MARGEN PCT"] = np.where(
        resumen["VENTA"] != 0, resumen["MARGEN"] / resumen["VENTA"] * 100, np.nan
    )
    total_cliente = resumen["RUC"].map(venta_total)
    resumen["COBERTURA PCT"] = np.where(
        total_cliente != 0, resumen["VENTA"] / total_cliente * 100, np.nan
    )

    salida = resumen.sort_values("MARGEN", ascending=False)
    return salida.head(top).reset_index(drop=True) if top else salida.reset_index(drop=True)


def evolucion_margen(ventas_enriquecidas: pd.DataFrame, anio: int) -> pd.DataFrame:
    """
    Venta, costo y margen mes a mes del año, para graficar.

    La serie termina en el ultimo mes con costo: no se dibujan meses en cero por
    falta de costo, porque en un grafico eso se lee como un derrumbe del margen.
    """
    base = ventas_enriquecidas[
        ventas_enriquecidas["TIENE COSTO"] & (ventas_enriquecidas["ANIO"] == anio)
    ]
    if base.empty:
        return pd.DataFrame(columns=["MES", "MES NOMBRE", "VENTA", "COSTO", "MARGEN", "MARGEN PCT"])

    out = base.groupby("MES", as_index=False, observed=True).agg(
        VENTA=("VENTA", "sum"), COSTO=("COSTO", "sum")
    )
    out["MARGEN"] = out["VENTA"] - out["COSTO"]
    out["MARGEN PCT"] = np.where(out["VENTA"] != 0, out["MARGEN"] / out["VENTA"] * 100, np.nan)
    out["MES"] = out["MES"].astype(int)
    out["MES NOMBRE"] = out["MES"].map(NOMBRE_MES)
    return out.sort_values("MES").reset_index(drop=True)


NOMBRE_MES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Oct", 11: "Nov", 12: "Dic",
}
