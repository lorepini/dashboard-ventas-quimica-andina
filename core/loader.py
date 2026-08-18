"""
Carga y limpieza de los reporteadores de ventas (.xls) de las 3 empresas.

El reporteador entrega una sola hoja con 14 columnas y una fila final de total
que se descarta. La limpieza resuelve tres problemas reales de la fuente:

1. La Ñ llega corrupta ('¥') y hay otros caracteres de codificacion antigua,
   lo que parte a un mismo cliente en varios nombres.
2. Un mismo RUC aparece escrito de formas distintas, lo que rompe el Pareto
   de clientes. Se consolida por RUC.
3. Los codigos SER* (fletes, alquileres, servicios) vienen mezclados con los
   productos y distorsionan el ranking de articulos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pandas as pd

# ---------------------------------------------------------------------------
# Empresas
# ---------------------------------------------------------------------------

EMPRESAS = {
    "QUIMAND": {
        "nombre": "Quimand",
        "nombre_largo": "Ind. y Comercial Química Andina S.A.C.",
        "archivo_clave": "INDUSTRIAL",
        "color": "#2E6B32",
        "rucs": ["20100295891"],
    },
    "DOGARESA": {
        "nombre": "Dogaresa",
        "nombre_largo": "Sociedad Minera Dogaresa S.A.C.",
        "archivo_clave": "SOCIEDAD MINERA",
        "color": "#12518C",
        "rucs": [],
    },
    "YESO": {
        "nombre": "Yeso La Limeña",
        "nombre_largo": "Yeso La Limeña S.A.C.",
        "archivo_clave": "YESO",
        "color": "#A8181C",
        "rucs": ["20101733883"],
    },
}

ORDEN_EMPRESAS = ["QUIMAND", "DOGARESA", "YESO"]

# Nombres que identifican operaciones entre las empresas del grupo.
PATRON_INTERCOMPANY = re.compile(
    r"QUIMICA\s+ANDI|YESO\s+LA\s+LIME|DOGARESA|QUIMAND", re.IGNORECASE
)

COLUMNAS_ESPERADAS = [
    "ARTICULO", "AGENCIA", "FECHA", "TD", "SERIE", "DOCUMENTO",
    "VD", "COD CLIENTE", "CLIENTE", "VALOR VENTA", "I.V.G.",
    "PRECIO VENTA", "CANTIDAD", "P. UNITARIO",
]

# Caracteres que el reporteador entrega mal codificados.
REEMPLAZOS = {
    "¥": "Ñ",
    "\x90": "É",
    "\xa0": " ",
    "§": "Ñ",
    "´": "'",
}


@dataclass
class ResultadoCarga:
    """Resultado de cargar un archivo, con diagnostico para mostrar al usuario."""

    empresa: str
    df: pd.DataFrame
    filas_leidas: int
    filas_validas: int
    fecha_min: pd.Timestamp | None
    fecha_max: pd.Timestamp | None
    clientes_unificados: int
    advertencias: list[str]


# ---------------------------------------------------------------------------
# Limpieza de texto
# ---------------------------------------------------------------------------

def limpiar_texto(valor) -> str:
    """Normaliza un texto del reporteador: arregla la codificacion y el espaciado."""
    if pd.isna(valor):
        return ""
    texto = str(valor)
    for malo, bueno in REEMPLAZOS.items():
        texto = texto.replace(malo, bueno)
    texto = unicodedata.normalize("NFC", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _clave_comparacion(texto: str) -> str:
    """Version sin tildes ni puntuacion, para detectar nombres equivalentes."""
    base = unicodedata.normalize("NFKD", texto.upper())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", base)


def _nombre_canonico(nombres: pd.Series) -> str:
    """Elige el nombre representativo de un RUC: el mas frecuente y, a igualdad, el mas largo."""
    conteo = nombres.value_counts()
    tope = conteo.max()
    candidatos = [n for n in conteo[conteo == tope].index if n]
    if not candidatos:
        return ""
    return max(candidatos, key=len)


# ---------------------------------------------------------------------------
# Identificacion de la empresa a partir del nombre del archivo
# ---------------------------------------------------------------------------

def detectar_empresa(nombre_archivo: str) -> str | None:
    """Deduce a que empresa pertenece un archivo por su nombre."""
    base = _clave_comparacion(nombre_archivo)
    for codigo in ORDEN_EMPRESAS:
        clave = _clave_comparacion(EMPRESAS[codigo]["archivo_clave"])
        if clave in base:
            return codigo
    return None


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def cargar_reporteador(fuente, empresa: str) -> ResultadoCarga:
    """
    Lee un reporteador (.xls o .xlsx) y devuelve el detalle limpio.

    `fuente` puede ser una ruta o un archivo subido por Streamlit.
    """
    advertencias: list[str] = []
    df = pd.read_excel(fuente)
    filas_leidas = len(df)

    faltantes = [c for c in COLUMNAS_ESPERADAS if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"El archivo de {EMPRESAS[empresa]['nombre']} no tiene las columnas "
            f"esperadas. Faltan: {', '.join(faltantes)}"
        )

    df = df[COLUMNAS_ESPERADAS].copy()

    # La ultima fila del reporteador es un total sin articulo ni fecha.
    df["ARTICULO"] = df["ARTICULO"].map(limpiar_texto)
    df = df[df["ARTICULO"] != ""]

    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    sin_fecha = int(df["FECHA"].isna().sum())
    if sin_fecha:
        advertencias.append(f"{sin_fecha} filas sin fecha valida fueron descartadas.")
        df = df[df["FECHA"].notna()]

    for col in ["VALOR VENTA", "PRECIO VENTA", "CANTIDAD", "P. UNITARIO", "I.V.G."]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["CLIENTE"] = df["CLIENTE"].map(limpiar_texto)
    df["TD"] = df["TD"].map(limpiar_texto).str.upper()
    df["SERIE"] = df["SERIE"].map(limpiar_texto)
    df["DOCUMENTO"] = df["DOCUMENTO"].map(limpiar_texto)
    df["COD CLIENTE"] = df["COD CLIENTE"].map(limpiar_texto)

    # Un mismo RUC puede venir con el nombre escrito de varias formas.
    sin_ruc = df["COD CLIENTE"] == ""
    if sin_ruc.any():
        df.loc[sin_ruc, "COD CLIENTE"] = "SIN-RUC-" + df.loc[sin_ruc, "CLIENTE"].map(
            _clave_comparacion
        )

    variantes = df.groupby("COD CLIENTE")["CLIENTE"].nunique()
    clientes_unificados = int((variantes > 1).sum())
    canonicos = df.groupby("COD CLIENTE")["CLIENTE"].apply(_nombre_canonico)
    df["CLIENTE"] = df["COD CLIENTE"].map(canonicos)

    if clientes_unificados:
        advertencias.append(
            f"{clientes_unificados} clientes venian con el nombre escrito de varias "
            "formas y fueron unificados por RUC."
        )

    # El articulo llega como 'CODIGO - DESCRIPCION'.
    partes = df["ARTICULO"].str.split(" - ", n=1, expand=True)
    df["COD ARTICULO"] = partes[0].str.strip()
    df["PRODUCTO"] = (
        partes[1].fillna(partes[0]).str.strip() if partes.shape[1] > 1 else partes[0]
    )

    df["ES SERVICIO"] = df["COD ARTICULO"].str.upper().str.startswith("SER")
    df["ES INTERCOMPANY"] = df["CLIENTE"].str.contains(PATRON_INTERCOMPANY, na=False)

    otros_rucs = {
        ruc
        for codigo, info in EMPRESAS.items()
        if codigo != empresa
        for ruc in info["rucs"]
    }
    if otros_rucs:
        df["ES INTERCOMPANY"] |= df["COD CLIENTE"].isin(otros_rucs)

    df["ES NOTA CREDITO"] = df["TD"] == "NC"
    df["EMPRESA"] = empresa
    df["EMPRESA NOMBRE"] = EMPRESAS[empresa]["nombre"]

    df["ANIO"] = df["FECHA"].dt.year
    df["MES"] = df["FECHA"].dt.month
    df["PERIODO"] = df["FECHA"].dt.to_period("M").dt.to_timestamp()
    df["DIA DEL ANIO"] = df["FECHA"].dt.dayofyear

    # Identificador unico de comprobante, para ticket promedio y conteo de operaciones.
    df["COMPROBANTE"] = (
        df["EMPRESA"] + "|" + df["TD"] + "|" + df["SERIE"] + "|" + df["DOCUMENTO"]
    )

    df = df.rename(columns={"VALOR VENTA": "VENTA", "COD CLIENTE": "RUC"})
    df = df.reset_index(drop=True)

    return ResultadoCarga(
        empresa=empresa,
        df=df,
        filas_leidas=filas_leidas,
        filas_validas=len(df),
        fecha_min=df["FECHA"].min() if len(df) else None,
        fecha_max=df["FECHA"].max() if len(df) else None,
        clientes_unificados=clientes_unificados,
        advertencias=advertencias,
    )


def combinar(resultados: list[ResultadoCarga]) -> pd.DataFrame:
    """Une el detalle de las empresas cargadas en una sola tabla."""
    if not resultados:
        return pd.DataFrame()
    df = pd.concat([r.df for r in resultados], ignore_index=True)
    df["EMPRESA"] = pd.Categorical(
        df["EMPRESA"],
        categories=[c for c in ORDEN_EMPRESAS if c in set(df["EMPRESA"])],
        ordered=True,
    )
    return df


def aplicar_filtros(
    df: pd.DataFrame,
    empresa: str | None = None,
    incluir_intercompany: bool = True,
    incluir_servicios: bool = True,
) -> pd.DataFrame:
    """Aplica los interruptores globales del dashboard."""
    out = df
    if empresa:
        out = out[out["EMPRESA"] == empresa]
    if not incluir_intercompany:
        out = out[~out["ES INTERCOMPANY"]]
    if not incluir_servicios:
        out = out[~out["ES SERVICIO"]]
    return out
