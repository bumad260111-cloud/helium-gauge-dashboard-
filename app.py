import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Учёт гелиевых баллонов", layout="wide")

DATA_FILE = "helium_log.csv"
COLUMNS = ["№", "Дата", "Пост / Оператор", "№ Баллона", "V_л", "P_нач", "P_тек"]
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
        df = pd.read_csv(DATA_FILE, dtype={"№ Баллона": str, "Пост / Оператор": str})
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[COLUMNS]
        if not df.empty:
            df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce").dt.strftime("%Y-%m-%d")
        return df

    df = pd.DataFrame(columns=COLUMNS)
    df.to_csv(DATA_FILE, index=False)
    return df


def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=COLUMNS + ["Остаток_л", "Остаток_м3", "Расход_л", "% Заполнения", "Статус"]
        )

    out = df.copy().reset_index(drop=True)
    out["V_л"] = pd.to_numeric(out["V_л"], errors="coerce").fillna(40.0)
    out["P_нач"] = pd.to_numeric(out["P_нач"], errors="coerce").fillna(15.0)
    out["P_тек"] = pd.to_numeric(out["P_тек"], errors="coerce").fillna(0.0)

    out["Остаток_л"] = out.apply(lambda r: calc_volume_liters(r["V_л"], r["P_тек"]), axis=1)
    out["Остаток_м3"] = out["Остаток_л"] / 1000.0

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
                    {"range": [0, 3], "color": "#F8D7DA"},
                    {"range": [3, 10], "color": "#FFF3CD"},
                    {"range": [10, 25], "color": "#D4EDDA"},
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

col_gauge, col_kpi = st.columns([1.2, 1])

if not df_calc.empty:
    selected_idx = st.selectbox(
        "Выберите запись для отображения на манометре:",
        options=list(range(len(df_calc))),
        index=len(df_calc) - 1,
        format_func=lambda idx: (
            f"№{df_calc.loc[idx, '№']} | {df_calc.loc[idx, 'Дата']} | "
            f"Баллон {df_calc.loc[idx, '№ Баллона']} | {df_calc.loc[idx, 'P_тек']:.1f} МПа"
        ),
    )
    cur_row = df_calc.loc[selected_idx]
    p_val = float(cur_row["P_тек"])
    cyl_title = f"Манометр (Баллон №{cur_row['№ Баллона']})"
    rem_l_val = f"{cur_row['Остаток_л']:,.1f}".replace(",", " ")
    rem_m3_val = f"{cur_row['Остаток_м3']:.3f}"
    cons_l_val = f"{cur_row['Расход_л']:,.1f}".replace(",", " ")
    fill_pct_val = f"{cur_row['% Заполнения']:.1f}%"
    status = str(cur_row["Статус"])
else:
    st.info("Журнал пуст. Добавьте первый замер ниже.")
    p_val = 0.0
    cyl_title = "Манометр (нет записей)"
    rem_l_val = "0.0"
    rem_m3_val = "0.000"
    cons_l_val = "0.0"
    fill_pct_val = "0.0%"
    status = None

with col_gauge:
    st.plotly_chart(
        make_gauge(p_val, cyl_title),
        use_container_width=True,
    )

with col_kpi:
    st.subheader("Текущие показатели")
    k1, k2 = st.columns(2)
    k1.metric("Остаток газа, л", rem_l_val)
    k2.metric("Остаток газа, м³", rem_m3_val)

    k3, k4 = st.columns(2)
    k3.metric("Расход за период, л", cons_l_val)
    k4.metric("Заполнение", fill_pct_val)

    if status == "В НОРМЕ":
        st.success(f"Статус баллона: {status}")
    elif status == "КРИТИЧНЫЙ":
        st.warning(f"Статус баллона: {status}")
    elif status == "ЗАМЕНИТЬ":
        st.error(f"Статус баллона: {status}")

st.divider()

st.subheader("Добавить новый замер")
with st.form("add_reading_form", clear_on_submit=True):
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    if not df_raw.empty:
        next_num = int(pd.to_numeric(df_raw["№"], errors="coerce").max() or 0) + 1
        parsed_last_date = pd.to_datetime(df_raw["Дата"].iloc[-1], errors="coerce")
        last_date = (
            parsed_last_date + pd.DateOffset(months=1)
            if pd.notna(parsed_last_date)
            else pd.Timestamp.today()
        )
        last_op = str(df_raw["Пост / Оператор"].iloc[-1] or "Заноха")
        last_cyl = str(df_raw["№ Баллона"].iloc[-1] or "213")
        last_v = float(pd.to_numeric(df_raw["V_л"].iloc[-1], errors="coerce") or 40.0)
        last_p0 = float(pd.to_numeric(df_raw["P_нач"].iloc[-1], errors="coerce") or 15.0)
    else:
        next_num = 1
        last_date = pd.Timestamp.today()
        last_op = "Заноха"
        last_cyl = "213"
        last_v = 40.0
        last_p0 = 15.0

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

with st.expander("Управление журналом"):
    confirm_clear = st.checkbox("Подтверждаю очистку всех записей из журнала")
    if st.button("Очистить журнал", disabled=not confirm_clear):
        empty_df = pd.DataFrame(columns=COLUMNS)
        empty_df.to_csv(DATA_FILE, index=False)
        st.rerun()

if not df_calc.empty:
    display_df = df_calc.copy()
    display_df["Остаток_л"] = display_df["Остаток_л"].map(lambda x: f"{x:,.3f}".replace(",", " "))
    display_df["Остаток_м3"] = display_df["Остаток_м3"].map(lambda x: f"{x:.3f}")
    display_df["Расход_л"] = display_df["Расход_л"].map(lambda x: f"{x:,.3f}".replace(",", " "))
    display_df["% Заполнения"] = display_df["% Заполнения"].map(lambda x: f"{x:.1f}%")
    st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.dataframe(pd.DataFrame(columns=df_calc.columns), use_container_width=True, hide_index=True)

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
