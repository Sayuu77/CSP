import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from influxdb_client import InfluxDBClient

# ─── Configuración ───────────────────────────────────────────
TOKEN  = 'Uj6JUIaa_2U-_EGXBEe1PmfBpwDBYhW0QfbIrPcRMjTntF-3rGLOiVGKedHdZHmFEI81SHDiJxAymYVZSJvjoA=='
ORG    = 'Sofi, Cami, Phio'
BUCKET = 'CSP'
URL    = 'https://us-east-1-1.aws.cloud2.influxdata.com'
CAMPOS = ['temperatura', 'humedad', 'nivel_agua', 'intensidad_solar', 'distancia']
META   = {
    'temperatura'     : ('#E74C3C', '°C'),
    'humedad'         : ('#2980B9', '%'),
    'nivel_agua'      : ('#1ABC9C', '%'),
    'intensidad_solar': ('#F39C12', '%'),
    'distancia'       : ('#8E44AD', 'cm'),
}

# ─── Título ──────────────────────────────────────────────────
st.title('📡 Dashboard IoT — Sensores CSP')
st.markdown('Visualización en tiempo real de los datos enviados desde el ESP32 a InfluxDB.')

# ─── Sidebar ─────────────────────────────────────────────────
horas = st.sidebar.slider('Ventana de tiempo (horas)', 1, 24, 2)
st.sidebar.markdown('---')
campos_sel = st.sidebar.multiselect('Variables a mostrar', CAMPOS, default=CAMPOS)

# ─── Consulta ────────────────────────────────────────────────
@st.cache_data(ttl=60)  # Refresca cada 60 segundos
def cargar_datos(horas):
    def consultar_campo(client, campo):
        query = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -{horas}h)
          |> filter(fn: (r) => r._measurement == "Sensores_CSP")
          |> filter(fn: (r) => r._field == "{campo}")
        '''
        tablas = client.query_api().query(query, org=ORG)
        tiempos, valores = [], []
        for tabla in tablas:
            for record in tabla.records:
                tiempos.append(record.get_time())
                valores.append(record.get_value())
        if not tiempos:
            return pd.Series([], dtype=float, name=campo)
        idx = pd.DatetimeIndex(
            pd.to_datetime(pd.Series(tiempos), utc=True)
        ).tz_convert('America/Bogota')
        return pd.Series(valores, index=idx, name=campo, dtype=float).sort_index()

    client_db = InfluxDBClient(url=URL, token=TOKEN, org=ORG, verify_ssl=False)
    series = {c: consultar_campo(client_db, c) for c in CAMPOS}
    df = pd.concat(series.values(), axis=1)
    df.columns = CAMPOS
    df = df.resample('1min').mean().dropna()
    df.index.name = 'tiempo'
    return df

with st.spinner('Cargando datos desde InfluxDB...'):
    df = cargar_datos(horas)

st.success(f'✅ {len(df)} registros cargados — {df.index[0].strftime("%H:%M")} a {df.index[-1].strftime("%H:%M")}')

# ─── Métricas rápidas ────────────────────────────────────────
st.markdown('### 📊 Valores actuales')
cols = st.columns(len(campos_sel))
for col, campo in zip(cols, campos_sel):
    unidad = META[campo][1]
    col.metric(label=campo, value=f'{df[campo].iloc[-1]:.2f} {unidad}',
               delta=f'{df[campo].iloc[-1] - df[campo].mean():.2f} vs media')

# ─── Series de tiempo ────────────────────────────────────────
st.markdown('### 📈 Series de tiempo')
fig, axes = plt.subplots(len(campos_sel), 1, figsize=(14, 3.5 * len(campos_sel)), sharex=True)
if len(campos_sel) == 1:
    axes = [axes]
for ax, campo in zip(axes, campos_sel):
    color, unidad = META[campo]
    serie = df[campo]
    ax.plot(serie.index, serie, color=color, linewidth=1.8, alpha=0.9)
    ax.fill_between(serie.index, serie, serie.mean(), alpha=0.15, color=color)
    ax.axhline(serie.mean(), color=color, linestyle='--', linewidth=1,
               alpha=0.7, label=f'Media: {serie.mean():.2f}{unidad}')
    ax.set_ylabel(f'{campo} ({unidad})', fontsize=10)
    ax.legend(loc='upper right', fontsize=9)
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
axes[-1].xaxis.set_major_locator(mdates.MinuteLocator(interval=10))
plt.gcf().autofmt_xdate(rotation=45)
plt.tight_layout()
st.pyplot(fig)

# ─── Histogramas ────────────────────────────────────────────
st.markdown('### 📊 Histogramas y KDE')
fig, axes = plt.subplots(1, len(campos_sel), figsize=(5 * len(campos_sel), 5))
if len(campos_sel) == 1:
    axes = [axes]
for ax, campo in zip(axes, campos_sel):
    color, unidad = META[campo]
    datos = df[campo].dropna()
    sns.histplot(datos, bins=20, kde=True, ax=ax, color=color, alpha=0.5)
    ax.axvline(datos.mean(),   color='black',   linestyle='--', linewidth=1.5, label=f'Media: {datos.mean():.2f}')
    ax.axvline(datos.median(), color='#27AE60', linestyle='-.', linewidth=1.5, label=f'Mediana: {datos.median():.2f}')
    ax.set_title(f'{campo} ({unidad})', fontsize=11, fontweight='bold')
    ax.legend(fontsize=8)
plt.tight_layout()
st.pyplot(fig)

# ─── Boxplots ────────────────────────────────────────────────
st.markdown('### 📦 Boxplots')
fig, axes = plt.subplots(1, len(campos_sel), figsize=(4 * len(campos_sel), 5))
if len(campos_sel) == 1:
    axes = [axes]
for ax, campo in zip(axes, campos_sel):
    color, unidad = META[campo]
    datos = df[campo].dropna()
    bp = ax.boxplot(datos, patch_artist=True, widths=0.5,
                    medianprops=dict(color='white', linewidth=2.5))
    bp['boxes'][0].set_facecolor(color)
    bp['boxes'][0].set_alpha(0.7)
    q1, med, q3 = datos.quantile(0.25), datos.median(), datos.quantile(0.75)
    iqr = q3 - q1
    outliers = datos[(datos < q1 - 1.5*iqr) | (datos > q3 + 1.5*iqr)]
    ax.set_title(f'{campo}\n({len(outliers)} outliers)', fontsize=10, fontweight='bold')
    ax.set_xticks([])
plt.tight_layout()
st.pyplot(fig)

# ─── Correlación ────────────────────────────────────────────
st.markdown('### 🔗 Matriz de correlación')
fig, ax = plt.subplots(figsize=(8, 6))
sns.heatmap(df[campos_sel].corr(), annot=True, fmt='.3f', cmap='RdBu_r',
            center=0, vmin=-1, vmax=1, ax=ax,
            annot_kws={'size': 11, 'weight': 'bold'},
            linewidths=2, square=True)
plt.tight_layout()
st.pyplot(fig)

# ─── Anomalías ───────────────────────────────────────────────
st.markdown('### ⚠️ Detección de anomalías (Z-score)')
UMBRAL_Z = st.sidebar.slider('Umbral Z-score', 1.5, 4.0, 2.5, step=0.1)
fig, axes = plt.subplots(len(campos_sel), 1, figsize=(14, 3 * len(campos_sel)), sharex=True)
if len(campos_sel) == 1:
    axes = [axes]
for ax, campo in zip(axes, campos_sel):
    color, unidad = META[campo]
    serie = df[campo].dropna()
    z = (serie - serie.mean()) / serie.std()
    anomalias = serie[z.abs() > UMBRAL_Z]
    ax.plot(serie.index, serie, color=color, linewidth=1.5, alpha=0.8, label='Señal')
    ax.scatter(anomalias.index, anomalias, color='#F39C12', s=80, zorder=5,
               label=f'Anomalías: {len(anomalias)}')
    ax.fill_between(serie.index,
                    serie.mean() - UMBRAL_Z*serie.std(),
                    serie.mean() + UMBRAL_Z*serie.std(),
                    alpha=0.07, color=color, label='Zona normal')
    ax.set_ylabel(f'{campo} ({unidad})', fontsize=9)
    ax.legend(loc='upper right', fontsize=8)
plt.tight_layout()
st.pyplot(fig)

# ─── Reporte ─────────────────────────────────────────────────
st.markdown('### 📋 Reporte resumen')
resumen = []
for campo in campos_sel:
    s = df[campo].dropna()
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    resumen.append({
        'Variable'  : campo,
        'Mín'       : round(s.min(), 2),
        'Máx'       : round(s.max(), 2),
        'Media'     : round(s.mean(), 2),
        'Mediana'   : round(s.median(), 2),
        'Desv. std' : round(s.std(), 2),
        'IQR'       : round(iqr, 2),
        'Outliers'  : int(((s < q1 - 1.5*iqr) | (s > q3 + 1.5*iqr)).sum()),
    })
st.dataframe(pd.DataFrame(resumen).set_index('Variable'), use_container_width=True)
