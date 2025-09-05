import pandas as pd
from .bcr_locales import scrape as bcr_locales
from .bdec_bsas import scrape as bdec_bsas
from .bcp_bahia import scrape as bcp_bahia
from ..normalizer import normalize_df

SOURCES = {
    "bcr_locales": bcr_locales,
    "bdec_bsas": bdec_bsas,
    "bcp_bahia":  bcp_bahia,
}

def run_selected(sources, **kwargs) -> pd.DataFrame:
    outs = []
    for key in sources:
        fn = SOURCES.get(key)
        if not fn:
            continue
        try:
            df = fn(**kwargs)
            if df is not None and not df.empty:
                outs.append(df)
        except Exception as ex:
            # devolvemos el error al UI
            msg = f"{key}: {ex}"
            outs.append(pd.DataFrame([{"fecha": kwargs.get("fecha_iso",""),
                                       "producto":"", "precio":"", "fuente": msg}]))

    if not outs:
        return pd.DataFrame()

    df = pd.concat(outs, ignore_index=True)
    return normalize_df(df)