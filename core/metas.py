"""
Metas anuales de venta por empresa: se guardan solas y se editan desde la app.

El usuario escribe la meta anual de cada empresa en un formulario del dashboard
y queda grabada en `dashboard/config/metas.json` para todas las sesiones
siguientes. No hay que subir ni descargar ningun archivo.

Las metas se guardan por AÑO, de modo que al cambiar de ejercicio se conserva
el historico de lo que se habia propuesto en años anteriores.

Ademas del guardado, este modulo reparte la meta anual entre los 12 meses
siguiendo la estacionalidad real del negocio (no en doceavos iguales) y calcula
cuanto se "deberia" llevar vendido a una fecha de corte, que es el numero que
alimenta el semaforo principal del dashboard.
"""

from __future__ import annotations

import calendar
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from .loader import EMPRESAS, ORDEN_EMPRESAS

# ---------------------------------------------------------------------------
# Ubicacion del archivo de metas
# ---------------------------------------------------------------------------

CARPETA_CONFIG = Path(__file__).resolve().parent.parent / "config"
ARCHIVO_METAS = CARPETA_CONFIG / "metas.json"

# Cuantos años anteriores completos se usan para calcular la estacionalidad.
ANIOS_ESTACIONALIDAD = 3

MESES = list(range(1, 13))


# ---------------------------------------------------------------------------
# Lectura y escritura del JSON
# ---------------------------------------------------------------------------

def _metas_de_secretos() -> dict[int, dict[str, float]]:
    """
    Metas de respaldo declaradas en los secretos de la aplicacion.

    En un servidor en la nube el disco es efimero: el archivo de metas se pierde
    cada vez que la aplicacion se reinicia. Los secretos, en cambio, persisten.
    Se usan como valor de partida cuando todavia no hay nada guardado en disco.

    Formato esperado en los secretos:
        [metas.2026]
        QUIMAND = 36220000
    """
    try:
        import streamlit as st

        crudo = st.secrets.get("metas", {})
    except Exception:
        return {}

    salida: dict[int, dict[str, float]] = {}
    for anio, empresas in dict(crudo).items():
        try:
            clave = int(anio)
        except (TypeError, ValueError):
            continue
        montos = {}
        for empresa, monto in dict(empresas).items():
            try:
                valor = float(monto)
            except (TypeError, ValueError):
                continue
            if valor > 0:
                montos[str(empresa).upper()] = valor
        if montos:
            salida[clave] = montos
    return salida


def cargar_metas() -> dict[int, dict[str, float]]:
    """
    Devuelve todas las metas guardadas como {anio: {empresa: monto}}.

    Lo guardado en disco manda sobre lo declarado en los secretos. Si el archivo
    no existe, esta vacio o quedo corrupto, se cae a los secretos y, si tampoco
    hay, devuelve {} sin lanzar excepcion: el dashboard debe poder abrirse igual.
    """
    respaldo = _metas_de_secretos()
    try:
        with open(ARCHIVO_METAS, "r", encoding="utf-8") as f:
            crudo = json.load(f)
    except (OSError, ValueError):
        return respaldo

    if not isinstance(crudo, dict):
        return respaldo

    # Se parte del respaldo y encima se aplica lo guardado en disco, que es lo
    # ultimo que el usuario escribio en el formulario.
    metas: dict[int, dict[str, float]] = {a: dict(v) for a, v in respaldo.items()}
    for anio, por_empresa in crudo.items():
        try:
            anio_int = int(anio)
        except (TypeError, ValueError):
            continue
        if not isinstance(por_empresa, dict):
            continue

        limpio: dict[str, float] = {}
        for empresa, monto in por_empresa.items():
            try:
                valor = float(monto)
            except (TypeError, ValueError):
                continue
            if valor > 0:
                limpio[str(empresa).upper()] = valor

        if limpio:
            metas.setdefault(anio_int, {}).update(limpio)

    return metas


def _escribir_metas(metas: dict[int, dict[str, float]]) -> None:
    """
    Graba el diccionario completo de metas de forma atomica.

    Escribe primero un archivo temporal en la misma carpeta y recien despues lo
    reemplaza, para que cerrar la app a media escritura no deje el JSON roto.
    """
    CARPETA_CONFIG.mkdir(parents=True, exist_ok=True)

    ordenado = {
        str(anio): {
            empresa: float(metas[anio][empresa])
            for empresa in sorted(
                metas[anio],
                key=lambda e: ORDEN_EMPRESAS.index(e) if e in ORDEN_EMPRESAS else 99,
            )
        }
        for anio in sorted(metas)
        if metas[anio]
    }

    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CARPETA_CONFIG,
            prefix="metas_",
            suffix=".tmp",
            delete=False,
        ) as f:
            temporal = f.name
            json.dump(ordenado, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ARCHIVO_METAS)
        temporal = None
    finally:
        if temporal and os.path.exists(temporal):
            os.remove(temporal)


def guardar_meta(anio: int, empresa: str, monto: float) -> None:
    """
    Guarda o actualiza la meta anual de una empresa.

    Un monto None, cero o negativo se interpreta como "esta empresa no tiene
    meta este año" y borra la meta guardada.
    """
    metas = cargar_metas()
    anio = int(anio)
    empresa = str(empresa).upper()

    try:
        valor = float(monto) if monto is not None else 0.0
    except (TypeError, ValueError):
        valor = 0.0

    if valor > 0:
        metas.setdefault(anio, {})[empresa] = valor
    else:
        metas.get(anio, {}).pop(empresa, None)
        if anio in metas and not metas[anio]:
            del metas[anio]

    _escribir_metas(metas)


def guardar_metas_anio(anio: int, metas: dict[str, float]) -> None:
    """
    Guarda de un solo golpe las metas de varias empresas de un mismo año.

    Es lo que usa el formulario del dashboard: el usuario escribe las tres
    metas y da guardar una sola vez. Las empresas con monto vacio, cero o
    negativo quedan sin meta.
    """
    guardadas = cargar_metas()
    anio = int(anio)
    del_anio = dict(guardadas.get(anio, {}))

    for empresa, monto in (metas or {}).items():
        clave = str(empresa).upper()
        try:
            valor = float(monto) if monto is not None else 0.0
        except (TypeError, ValueError):
            valor = 0.0
        if valor > 0:
            del_anio[clave] = valor
        else:
            del_anio.pop(clave, None)

    if del_anio:
        guardadas[anio] = del_anio
    else:
        guardadas.pop(anio, None)

    _escribir_metas(guardadas)


def obtener_meta(anio: int, empresa: str) -> float | None:
    """Devuelve la meta anual de una empresa, o None si todavia no se cargo."""
    return cargar_metas().get(int(anio), {}).get(str(empresa).upper())


def meta_grupo(anio: int) -> float | None:
    """
    Suma las metas cargadas del año para obtener la meta del grupo.

    Devuelve None si no hay ninguna meta cargada; si solo hay una o dos
    empresas con meta, suma las que haya (el dashboard avisara que la meta del
    grupo esta incompleta).
    """
    del_anio = cargar_metas().get(int(anio), {})
    if not del_anio:
        return None
    return float(sum(del_anio.values()))


def empresas_sin_meta(anio: int) -> list[str]:
    """Lista las empresas que todavia no tienen meta cargada para ese año."""
    del_anio = cargar_metas().get(int(anio), {})
    return [codigo for codigo in ORDEN_EMPRESAS if codigo not in del_anio]


# ---------------------------------------------------------------------------
# Reparto de la meta entre los meses
# ---------------------------------------------------------------------------

def _pesos_mensuales(historico: pd.DataFrame, anio: int) -> pd.Series:
    """
    Calcula el peso de cada mes (suma 1) segun la estacionalidad historica.

    Usa hasta los ultimos 3 años ANTERIORES completos —los que tienen los 12
    meses con movimiento—. El año en curso se excluye siempre porque esta a
    medias y sesgaria los pesos hacia los primeros meses. Si ningun año
    anterior esta completo pero entre todos cubren los 12 meses, se usan todos
    juntos. Si aun asi no alcanza, devuelve 1/12 parejo.
    """
    parejo = pd.Series(1.0 / 12.0, index=MESES, name="PESO")

    columnas = {"ANIO", "MES", "VENTA"}
    if historico is None or len(historico) == 0 or not columnas.issubset(historico.columns):
        return parejo

    previo = historico[pd.to_numeric(historico["ANIO"], errors="coerce") < int(anio)]
    if previo.empty:
        return parejo

    por_anio_mes = (
        previo.groupby(["ANIO", "MES"])["VENTA"].sum().reset_index()
    )
    con_venta = por_anio_mes[por_anio_mes["VENTA"] > 0]
    completos = sorted(
        anio_previo
        for anio_previo, meses in con_venta.groupby("ANIO")["MES"].nunique().items()
        if meses == 12
    )

    if completos:
        elegidos = completos[-ANIOS_ESTACIONALIDAD:]
        base = por_anio_mes[por_anio_mes["ANIO"].isin(elegidos)]
    elif con_venta["MES"].nunique() == 12:
        base = por_anio_mes
    else:
        return parejo

    # Las notas de credito pueden dejar un mes en negativo; no tiene sentido
    # asignarle una meta negativa.
    ventas = base.groupby("MES")["VENTA"].sum().reindex(MESES).fillna(0.0).clip(lower=0.0)

    total = float(ventas.sum())
    if total <= 0:
        return parejo

    pesos = (ventas / total).astype(float)
    pesos.index = MESES
    pesos.name = "PESO"
    return pesos


def distribuir_meta_mensual(
    meta_anual: float, historico: pd.DataFrame, anio: int
) -> pd.Series:
    """
    Reparte la meta anual entre los 12 meses segun la estacionalidad historica.

    `historico` es el detalle de ventas de UNA empresa, con las columnas ANIO,
    MES y VENTA. El peso de cada mes sale de los ultimos 3 años anteriores
    completos; el año en curso se excluye porque esta incompleto.

    Si no hay historia suficiente, o los pesos salen degenerados (suma cero o
    todos los meses en negativo), cae a un reparto parejo de 1/12 por mes.

    Devuelve una Serie indexada de 1 a 12 que suma exactamente `meta_anual`.
    """
    try:
        objetivo = float(meta_anual)
    except (TypeError, ValueError):
        objetivo = 0.0

    pesos = _pesos_mensuales(historico, int(anio))
    reparto = (pesos * objetivo).astype(float)

    # El redondeo binario deja centimos sueltos: se ajustan en el ultimo mes
    # para que la suma cuadre exactamente con la meta.
    reparto.iloc[-1] += objetivo - float(reparto.sum())

    reparto.index = MESES
    reparto.index.name = "MES"
    reparto.name = "META"
    return reparto


def meta_acumulada_a_la_fecha(
    meta_anual: float,
    historico: pd.DataFrame,
    anio: int,
    fecha_corte: pd.Timestamp,
) -> float:
    """
    Meta que se deberia llevar acumulada a la fecha de corte.

    Suma los meses ya cerrados y prorratea el mes en curso segun los dias
    transcurridos: al 17 de agosto cuenta enero a julio completos mas 17/31 de
    la meta de agosto. Es el numero con el que el dashboard compara la venta
    real para pintar el semaforo.

    Si la fecha de corte es de un año posterior devuelve la meta anual completa;
    si es anterior, cero.
    """
    corte = pd.Timestamp(fecha_corte)
    anio = int(anio)

    if corte.year > anio:
        return float(meta_anual)
    if corte.year < anio:
        return 0.0

    mensual = distribuir_meta_mensual(meta_anual, historico, anio)

    cerrados = float(mensual.loc[mensual.index < corte.month].sum())
    dias_del_mes = calendar.monthrange(corte.year, corte.month)[1]
    en_curso = float(mensual.loc[corte.month]) * (corte.day / dias_del_mes)

    return cerrados + en_curso


def resumen_metas(anio: int) -> pd.DataFrame:
    """Tabla con la meta cargada de cada empresa del grupo, para mostrarla en la app."""
    del_anio = cargar_metas().get(int(anio), {})
    return pd.DataFrame(
        {
            "EMPRESA": ORDEN_EMPRESAS,
            "NOMBRE": [EMPRESAS[c]["nombre"] for c in ORDEN_EMPRESAS],
            "META": [del_anio.get(c) for c in ORDEN_EMPRESAS],
        }
    )
