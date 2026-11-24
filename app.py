import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Учёт гелиевых баллонов", layout="wide")

DATA_FILE = "helium_log.csv"
P_MAX = 25.0


def calc_volume_liters(v_water_l: float, p_mpa: float) -> float:
    """Расчёт объёма газа (л) при н.у. с учётом поправки сжимаемости гелия."""
    if p_mpa <= 0 or v_water_l <= 0:
        return 0.0
    return (v_water_l * p_mpa * 10.0) / (1.0 + 0.0047 * p_mpa)


def get_status(p_cur: float) -> str:
    if p_cur <= 1.0:
        return "ЗАМЕНИТЬ"
    elif p_cur <= 3.0:
        return "КРИТИЧНЫЙ"
    return "В НОРМЕ"


def init_data() -> pd.DataFrame:
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        df["Дата"] = pd.to_datetime(df["Дата"]).dt.strftime("%Y-%m-%d")
        return df

    raw = [
        {"№": 1, "Дата": "2026-12-19", "Пост / Оператор": "Заноха", "№ Баллона": "213", "V_л": 40.0, "P_нач": 15.0, "P_тек": 5.0},
        {"№": 2, "Дата": "2027-01-19", "Пост / Оператор": "Заноха", "№ Баллона": "213", "V_л": 40.0, "P_нач": 15.0, "P_тек": 2.0},
        {"№": 3, "Дата": "2027-02-19", "Пост / Оператор": "Заноха", "№ Баллона": "213", "V_л": 40.0, "P_нач": 15.0, "P_тек": 5.0},
    ]
    df = pd.DataFrame(raw)
    df.to_csv(DATA_FILE, index=False)
    return df


def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    out["V_л"] = pd.to_numeric(out["V_л"], errors="coerce").fillna(40.0)
    out["P_нач"] = pd.to_numeric(out["P_нач"], errors="coerce").fillna(15.0)
    out["P_тек"] = pd.to_numeric(out["P_тек"], errors="coerce").fillna(0.0)

    out["Остаток_л"] = out.apply(lambda r: calc_volume_liters(r["V_л"], r["P_тек"]), axis=1)
    out["Остаток_м3"] = out["Остаток_л"] / 1000.0

    # Расход: в первой строке — от начального давления заправки;
    # в последующих — разница с предыдущим остатком, а при росте давления (заправка/замена) — от P_нач
    consumptions = []
    for i, row in out.iterrows():
        v0 = calc_volume_liters(row["V_л"], row["P_нач"])
        if i == 0:
            consumptions.append(v0 - row["Остаток_л"])
        else:
            prev_p = out.loc[i - 1, "P_тек"]
            prev_rem = out.loc[i - 1, "Остаток_л"]
            if row["P_тек"] > prev_p:
                consumptions.append(v0 - row["Остаток_л"])
            else:
                consumptions.append(prev_rem - row["Остаток_л"])

    out["Расход_л"] = consumptions
    out["% Заполнения"] = out.apply(
        lambda r: (r["P_тек"] / r["P_нач"] * 100.0) if r["P_нач"] > 0 else 0.0, axis=1
    )
    out["Статус"] = out["P_тек"].apply(get_status)
    return out


def make_gauge(p_cur: float, title_text: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=p_cur,
            number={"suffix": " МПа", "valueformat": ".1f"},
            title={"text": title_text, "font": {"size": 18}},
            gauge={
                "axis": {"range": [0, P_MAX], "tickwidth": 1, "dtick": 5},
                "bar": {"color": "#1F497D", "thickness": 0.25},
                "bgcolor": "white",
                "steps": [
                    {"range": [0, 3], "color": "#F8D7DA"},      # Критично / замена
                    {"range": [3, 10], "color": "#FFF3CD"},     # Ниже нормы / контроль
                    {"range": [10, 25], "color": "#D4EDDA"},    # Норма
                ],
                "threshold": {
                    "line": {"color": "red", "width": 4},
                    "thickness": 0.8,
                    "value": p_cur,
                },
            },
        )
    )
    fig.update_layout(height=320, margin=dict(l=20, r=20, t=50, b=20))
    return fig


st.title("Журнал учёта гелиевых баллонов и визуальный манометр")

df_raw = init_data()
df_calc = compute_metrics(df_raw)

# Выбор строки для отображения на манометре
selected_idx = st.selectbox(
    "Выберите запись для отображения на манометре:",
    options=range(len(df_calc)),
    index=len(df_calc) - 1,
    format_func=lambda idx: f"№{df_calc.loc[idx, '№']} | {df_calc.loc[idx, 'Дата']} | Баллон {df_calc.loc[idx, '№ Баллона']} | {df_calc.loc[idx, 'P_тек']:.1f} МПа",
)

cur_row = df_calc.loc[selected_idx]

col_gauge, col_kpi = st.columns([1.2, 1])

with col_gauge:
    st.plotly_chart(
        make_gauge(float(cur_row["P_тек"]), f"Манометр (Баллон №{cur_row['№ Баллона']})"),
        use_container_width=True,
    )

with col_kpi:
    st.subheader("Текущие показатели")
    k1, k2 = st.columns(2)
    k1.metric("Остаток газа, л", f"{cur_row['Остаток_л']:,.1f}".replace(",", " "))
    k2.metric("Остаток газа, м³", f"{cur_row['Остаток_м3']:.3f}")

    k3, k4 = st.columns(2)
    k3.metric("Расход за период, л", f"{cur_row['Расход_л']:,.1f}".replace(",", " "))
    k4.metric("Заполнение", f"{cur_row['% Заполнения']:.1f}%")

    status = cur_row["Статус"]
    if status == "В НОРМЕ":
        st.success(f"Статус баллона: {status}")
    elif status == "КРИТИЧНЫЙ":
        st.warning(f"Статус баллона: {status}")
    else:
        st.error(f"Статус баллона: {status}")

st.divider()

# Форма добавления нового ежемесячного замера
st.subheader("Добавить новый замер")
with st.form("add_reading_form", clear_on_submit=True):
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    next_num = int(df_raw["№"].max()) + 1 if not df_raw.empty else 1
    last_date = pd.to_datetime(df_raw["Дата"].iloc[-1]) + pd.DateOffset(months=1) if not df_raw.empty else pd.Timestamp.today()
    last_op = str(df_raw["Пост / Оператор"].iloc[-1]) if not df_raw.empty else "Заноха"
    last_cyl = str(df_raw["№ Баллона"].iloc[-1]) if not df_raw.empty else "213"
    last_v = float(df_raw["V_л"].iloc[-1]) if not df_raw.empty else 40.0
    last_p0 = float(df_raw["P_нач"].iloc[-1]) if not df_raw.empty else 15.0

    f_date = c1.date_input("Дата", value=last_date)
    f_op = c2.text_input("Пост / Оператор", value=last_op)
    f_cyl = c3.text_input("№ Баллона", value=last_cyl)
    f_v = c4.number_input("V баллона, л", min_value=1.0, max_value=200.0, value=last_v, step=5.0)
    f_p0 = c5.number_input("P нач., МПа", min_value=0.1, max_value=30.0, value=last_p0, step=0.5)
    f_p1 = c6.number_input("P тек., МПа", min_value=0.0, max_value=30.0, value=3.5, step=0.5)

    submitted = st.form_submit_button("Добавить запись в журнал")
    if submitted:
        new_entry = pd.DataFrame([{
            "№": next_num,
            "Дата": f_date.strftime("%Y-%m-%d"),
            "Пост / Оператор": f_op,
            "№ Баллона": f_cyl,
            "V_л": f_v,
            "P_нач": f_p0,
            "P_тек": f_p1,
        }])
        updated = pd.concat([df_raw, new_entry], ignore_index=True)
        updated.to_csv(DATA_FILE, index=False)
        st.rerun()

st.subheader("Журнал замеров")
display_df = df_calc.copy()
display_df["Остаток_л"] = display_df["Остаток_л"].map(lambda x: f"{x:,.3f}".replace(",", " "))
display_df["Остаток_м3"] = display_df["Остаток_м3"].map(lambda x: f"{x:.3f}")
display_df["Расход_л"] = display_df["Расход_л"].map(lambda x: f"{x:,.3f}".replace(",", " "))
display_df["% Заполнения"] = display_df["% Заполнения"].map(lambda x: f"{x:.1f}%")

st.dataframe(display_df, use_container_width=True, hide_index=True)

# Выгрузка в Excel при необходимости
excel_path = "helium_report.xlsx"
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    df_calc.to_excel(writer, index=False, sheet_name="Учёт гелия")

with open(excel_path, "rb") as f:
    st.download_button(
        label="Скачать таблицу в Excel (.xlsx)",
        data=f,
        file_name="helium_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
