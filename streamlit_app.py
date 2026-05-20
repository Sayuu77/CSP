import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from influxdb_client import InfluxDBClient

# ─── Configuración de página ─────────────────────────────────
st.set_page_config(
    page_title='Dashboard IoT — CSP',
    page_icon='📡',
    layout='wide',
    initial_sidebar_state='expanded'
)

# ─── CSS personalizado ───────────────────────────────────────
st.markdown("""
<style>
    /* Fondo general */
    .stApp { background-color: #0f1117; color: #ffffff; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1d2e 0%, #16213e 100%);
        border-right: 1px solid #2d3561;
    }

    /* Tarjetas de métricas */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e2140 0%, #252b4a 100%);
        border: 1px solid #2d3561;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    [data-testid="stMetricValue"] { color: #e0e6ff !important; font-size: 1.6rem !important; }
    [data-testid="stMetricLabel"] { color: #8892b0 !important; font-size: 0.85rem !important; }
    [data-testid="stMetricDelta"] { font-size: 0.8rem !important; }

    /* Títulos de sección */
    .section-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #a8b2d8;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        border-left: 3px solid #5c7cfa;
        padding-left: 10px;
        margin: 28px 0 14px 0;
    }

    /* Divisor */
    hr { border-color: #2d3561 !important; }

    /* Tabla */
    [data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #2d3561;
    }

    /* Spinner y success */
    .stSpinner > div { border-top-color: #5c7cfa !important; }
    .stAlert { border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)

# ─── Configuración de datos ──────────────────────────────────
TOKEN  = 'Uj6JUIaa_2U-_EGXBEe1PmfBpwDBYhW0QfbIrPcRMjTntF-3rGLOiVGKedHdZHmFEI81SHDiJxAymYVZSJvjoA=='
ORG    = 'Sofi, Cami, Phio'
BUCKET = 'CSP'
URL    = 'https://us-east-1-1.aws.cloud2.influxdata.com'
CAMPOS = ['temperatura', 'humedad', 'nivel_agua', 'intensidad_solar', 'distancia']
META   = {
    'temperatura'     : ('#FF6B6B', '°C',  '🌡️'),
    'humedad'         : ('#4ECDC4', '%',   '💧'),
    'nivel_agua'      : ('#45B7D1', '%',   '🪣'),
    'intensidad_solar': ('#FFE66D', '%',   '☀️'),
    'distancia'       : ('#C77DFF', 'cm',  '📏'),
}

# Estilo global de matplotlib oscuro
plt.rcParams.update({
    'figure.facecolor'  : '#1e2140',
    'axes.facecolor'    : '#252b4a',
    'axes.edgecolor'    : '#3d4475',
    'axes.labelcolor'   : '#a8b2d8',
    'xtick.color'       : '#8892b0',
    'ytick.color'       : '#8892b0',
    'grid.color'        : '#2d3561',
    'grid.alpha'        : 0.5,
    'text.color'        : '#ccd6f6',
    'legend.facecolor'  : '#1a1d2e',
    'legend.edgecolor'  : '#2d3561',
    'axes.grid'         : True,
})

# ─── Sidebar ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
        <div style='text-align:center; padding: 10px 0 20px 0;'>
            <div style='font-size:2.5rem;'>📡</div>
            <div style='font-size:1.1rem; font-weight:700; color:#ccd6f6;'>Sensores CSP</div>
            <div style='font-size:0.75rem; color:#8892b0;'>ESP32 · InfluxDB · Streamlit</div>
        </div>
    """, unsafe_allow_html=True)
    st.markdown('---')

    st.markdown('**⏱ Ventana de tiempo**')
    horas = st.slider('', 1, 24, 2, label_visibility='collapsed')
    st.caption(f'Mostrando las últimas **{horas} horas**')

    st.markdown('---')
    st.markdown('**📌 Variables**')
    campos_sel = st.multiselect('', CAMPOS, default=CAMPOS, label_visibility='collapsed')

    st.markdown('---')
    st.markdown('**⚠️ Umbral Z-score**')
    UMBRAL_Z = st.slider('', 1.5, 4.0, 2.5, step=0.1, label_visibility='collapsed')
    st.caption(f'Anomalías con |z| > **{UMBRAL_Z}**')

    st.markdown('---')
    st.markdown('<div style="color:#8892b0; font-size:0.75rem; text-align:center;">Refresco automático cada 60s</div>', unsafe_allow_html=True)

# ─── Header ──────────────────────────────────────────────────
st.markdown("""
    <div style='padding: 20px 0 10px 0;'>
        <h1 style='color:#ccd6f6; font-size:2rem; margin:0;'>📡 Dashboard IoT</h1>
        <p style='color:#8892b0; margin:4px 0 0 0;'>
            Visualización en tiempo real · ESP32 → InfluxDB → Streamlit
        </p>
    </div>
    <hr>
""", unsafe_allow_html=True)

# ─── Carga de datos ──────────────────────────────────────────
@st.cache_data(ttl=60)
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

with st.spinner('Conectando a InfluxDB y cargando datos...'):
    df = cargar_datos(horas)

st.success(f'✅ {len(df)} registros · {df.index[0].strftime("%d/%m %H:%M")} → {df.index[-1].strftime("%d/%m %H:%M")} (hora Colombia)')

# ─── Métricas ────────────────────────────────────────────────
st.markdown('<div class="section-title">Valores actuales</div>', unsafe_allow_html=True)
cols = st.columns(len(campos_sel))
for col, campo in zip(cols, campos_sel):
    color, unidad, emoji = META[campo]
    valor  = df[campo].iloc[-1]
    delta  = valor - df[campo].mean()
    col.metric(
        label=f'{emoji} {campo.replace("_", " ").title()}',
        value=f'{valor:.2f} {unidad}',
        delta=f'{delta:+.2f} vs media'
    )

st.markdown('<hr>', unsafe_allow_html=True)

# ─── Series de tiempo ────────────────────────────────────────
st.markdown('<div class="section-title">📈 Series de tiempo</div>', unsafe_allow_html=True)
fig, axes = plt.subplots(len(campos_sel), 1, figsize=(14, 3.2 * len(campos_sel)), sharex=True)
if len(campos_sel) == 1:
    axes = [axes]
fig.patch.set_facecolor('#1e2140')
for ax, campo in zip(axes, campos_sel):
    color, unidad, emoji = META[campo]
    serie = df[campo]
    ax.plot(serie.index, serie, color=color, linewidth=2, alpha=0.95)
    ax.fill_between(serie.index, serie, serie.mean(), alpha=0.12, color=color)
    ax.axhline(serie.mean(), color=color, linestyle='--', linewidth=1, alpha=0.6,
               label=f'Media: {serie.mean():.2f} {unidad}')
    ax.set_ylabel(f'{emoji} {campo}\n({unidad})', fontsize=9, color='#a8b2d8')
    ax.legend(loc='upper right', fontsize=8)
    ax.spines[['top','right']].set_visible(False)
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
axes[-1].xaxis.set_major_locator(mdates.MinuteLocator(interval=10))
plt.gcf().autofmt_xdate(rotation=45)
plt.tight_layout(pad=1.5)
st.pyplot(fig)
plt.close()

st.markdown('<hr>', unsafe_allow_html=True)

# ─── Histogramas ────────────────────────────────────────────
st.markdown('<div class="section-title">📊 Distribuciones (Histograma + KDE)</div>', unsafe_allow_html=True)
fig, axes = plt.subplots(1, len(campos_sel), figsize=(5 * len(campos_sel), 4.5))
if len(campos_sel) == 1:
    axes = [axes]
fig.patch.set_facecolor('#1e2140')
for ax, campo in zip(axes, campos_sel):
    color, unidad, emoji = META[campo]
    datos = df[campo].dropna()
    sns.histplot(datos, bins=20, kde=True, ax=ax, color=color, alpha=0.4,
                 line_kws={'linewidth': 2.5})
    ax.axvline(datos.mean(),   color='#ffffff', linestyle='--', linewidth=1.5,
               label=f'Media: {datos.mean():.2f}')
    ax.axvline(datos.median(), color='#FFE66D', linestyle='-.', linewidth=1.5,
               label=f'Mediana: {datos.median():.2f}')
    ax.set_title(f'{emoji} {campo}\n({unidad})', fontsize=10, fontweight='bold', color='#ccd6f6')
    ax.set_xlabel(unidad, fontsize=9)
    ax.legend(fontsize=8)
    ax.spines[['top','right']].set_visible(False)
plt.tight_layout(pad=1.5)
st.pyplot(fig)
plt.close()

st.markdown('<hr>', unsafe_allow_html=True)

# ─── Boxplots ────────────────────────────────────────────────
st.markdown('<div class="section-title">📦 Boxplots — Dispersión y Outliers</div>', unsafe_allow_html=True)
fig, axes = plt.subplots(1, len(campos_sel), figsize=(4 * len(campos_sel), 4.5))
if len(campos_sel) == 1:
    axes = [axes]
fig.patch.set_facecolor('#1e2140')
for ax, campo in zip(axes, campos_sel):
    color, unidad, emoji = META[campo]
    datos = df[campo].dropna()
    bp = ax.boxplot(datos, patch_artist=True, widths=0.5,
                    medianprops=dict(color='#ffffff', linewidth=2.5),
                    flierprops=dict(marker='o', color='#FFE66D', markersize=5, alpha=0.7),
                    whiskerprops=dict(color=color, linewidth=1.5),
                    capprops=dict(color=color, linewidth=1.5))
    bp['boxes'][0].set_facecolor(color)
    bp['boxes'][0].set_alpha(0.5)
    q1, med, q3 = datos.quantile(0.25), datos.median(), datos.quantile(0.75)
    iqr = q3 - q1
    outliers = datos[(datos < q1 - 1.5*iqr) | (datos > q3 + 1.5*iqr)]
    ax.annotate(f'Q3 {q3:.1f}', xy=(1.32, q3), fontsize=8, color='#a8b2d8')
    ax.annotate(f'Md {med:.1f}', xy=(1.32, med), fontsize=8, color='#ffffff', fontweight='bold')
    ax.annotate(f'Q1 {q1:.1f}', xy=(1.32, q1), fontsize=8, color='#a8b2d8')
    ax.set_title(f'{emoji} {campo}\n{len(outliers)} outliers', fontsize=10,
                 fontweight='bold', color='#ccd6f6')
    ax.set_ylabel(unidad, fontsize=9)
    ax.set_xticks([])
    ax.spines[['top','right']].set_visible(False)
plt.tight_layout(pad=1.5)
st.pyplot(fig)
plt.close()

st.markdown('<hr>', unsafe_allow_html=True)

# ─── Correlación + Anomalías (lado a lado) ───────────────────
col_corr, col_anom = st.columns([1, 1.6])

with col_corr:
    st.markdown('<div class="section-title">🔗 Correlación</div>', unsafe_allow_html=True)
    fig, ax = plt.subplots(figsize=(6, 5))
    fig.patch.set_facecolor('#1e2140')
    sns.heatmap(df[campos_sel].corr(), annot=True, fmt='.2f', cmap='coolwarm',
                center=0, vmin=-1, vmax=1, ax=ax,
                annot_kws={'size': 10, 'weight': 'bold', 'color': 'white'},
                linewidths=2, linecolor='#1e2140', square=True,
                cbar_kws={'shrink': 0.8})
    ax.tick_params(colors='#a8b2d8', labelsize=8)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close()

with col_anom:
    st.markdown('<div class="section-title">⚠️ Anomalías por Z-score</div>', unsafe_allow_html=True)
    fig, axes = plt.subplots(len(campos_sel), 1, figsize=(9, 2.8 * len(campos_sel)), sharex=True)
    if len(campos_sel) == 1:
        axes = [axes]
    fig.patch.set_facecolor('#1e2140')
    for ax, campo in zip(axes, campos_sel):
        color, unidad, emoji = META[campo]
        serie = df[campo].dropna()
        z = (serie - serie.mean()) / serie.std()
        anomalias = serie[z.abs() > UMBRAL_Z]
        ax.plot(serie.index, serie, color=color, linewidth=1.5, alpha=0.85)
        ax.scatter(anomalias.index, anomalias, color='#FFE66D', s=60, zorder=5,
                   label=f'{len(anomalias)} anomalías', edgecolors='#ff9f43', linewidths=0.8)
        ax.fill_between(serie.index,
                        serie.mean() - UMBRAL_Z*serie.std(),
                        serie.mean() + UMBRAL_Z*serie.std(),
                        alpha=0.08, color=color)
        ax.set_ylabel(f'{emoji} ({unidad})', fontsize=8, color='#a8b2d8')
        ax.legend(loc='upper right', fontsize=7)
        ax.spines[['top','right']].set_visible(False)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.gcf().autofmt_xdate(rotation=45)
    plt.tight_layout(pad=1.2)
    st.pyplot(fig)
    plt.close()

st.markdown('<hr>', unsafe_allow_html=True)

# ─── Reporte resumen ─────────────────────────────────────────
st.markdown('<div class="section-title">📋 Reporte estadístico</div>', unsafe_allow_html=True)
resumen = []
for campo in campos_sel:
    color, unidad, emoji = META[campo]
    s = df[campo].dropna()
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    resumen.append({
        'Variable'  : f'{emoji} {campo}',
        f'Mín'      : f'{s.min():.2f} {unidad}',
        f'Máx'      : f'{s.max():.2f} {unidad}',
        f'Media'    : f'{s.mean():.2f} {unidad}',
        f'Mediana'  : f'{s.median():.2f} {unidad}',
        'Desv. std' : f'{s.std():.2f} {unidad}',
        'IQR'       : f'{iqr:.2f} {unidad}',
        'Outliers'  : int(((s < q1 - 1.5*iqr) | (s > q3 + 1.5*iqr)).sum()),
    })
st.dataframe(pd.DataFrame(resumen).set_index('Variable'), use_container_width=True)

st.markdown("""
    <div style='text-align:center; color:#4a5568; font-size:0.75rem; padding:20px 0 10px 0;'>
        Dashboard IoT · Sofi, Cami & Phio · ESP32 + InfluxDB + Streamlit
    </div>
""", unsafe_allow_html=True)
