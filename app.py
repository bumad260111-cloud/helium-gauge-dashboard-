import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Учёт гелиевых баллонов (6 приборов)", layout="wide")

DATA_FILE = "helium_log.csv"
COLUMNS = ["№", "Дата", "Прибор", "Пост / Оператор", "№ Баллона", "V_л", "P_нач", "P_тек"]
DEFAULT_DEVICES = [
    "Прибор 1",
    "Прибор 2",
    "Прибор 3",
    "Прибор 4",
    "Прибор 5",
    "Прибор 6",
]
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
        df = pd.read_csv(
            DATA_FILE,
            dtype={"Прибор": str, "№ Баллона": str, "Пост / Оператор": str},
        )
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = DEFAULT_DEVICES[0] if col == "Прибор" else None
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
    out["Прибор"] = out["Прибор"].fillna(DEFAULT_DEVICES[0]).astype(str)
    out["№ Баллона"] = out["№ Баллона"].fillna("").astype(str)
    out["V_л"] = pd.to_numeric(out["V_л"], errors="coerce").fillna(40.0)
    out["P_нач"] = pd.to_numeric(out["P_нач"], errors="coerce").fillna(15.0)
    out["P_тек"] = pd.to_numeric(out["P_тек"], errors="coerce").fillna(0.0)

    out["Остаток_л"] = out.apply(lambda r: calc_volume_liters(r["V_л"], r["P_тек"]), axis=1)
    out["Остаток_м3"] = out["Остаток_л"] / 1000.0

    # Расход считаем в разрезе пары (Прибор, № Баллона)
    consumptions = []
    last_by_key = {}

    for _, row in out.iterrows():
        key = (row["Прибор"].strip(), row["№ Баллона"].strip())
        v0 = calc_volume_liters(row["V_л"], row["P_нач"])
        rem_cur = row["Остаток_л"]
        p_cur = row["P_тек"]

        if key not in last_by_key:
            cons = v0 - rem_cur
        else:
            prev_p, prev_rem = last_by_key[key]
            if p_cur > prev_p:
                cons = v0 - rem_cur
            else:
                cons = prev_rem - rem_cur

        consumptions.append(cons)
        last_by_key[key] = (p_cur, rem_cur)

    out["Расход_л"] = consumptions
    out["% Заполнения"] = out.apply(
        lambda r: (r["P_тек"] / r["P_нач"] * 100.0) if r["P_нач"] > 0 else 0.0, axis=1
    )
    out["Статус"] = out["P_тек"].apply(get_status)
    return out


def make_mini_gauge(p_cur: float, title_text: str, height: int = 210) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=p_cur,
            number={"suffix": " МПа", "valueformat": ".1f", "font": {"size": 20}},
            title={"text": title_text, "font": {"size": 14}},
            gauge={
                "axis": {"range": [0, P_MAX], "tickwidth": 1, "dtick": 5, "tickfont": {"size": 10}},
                "bar": {"color": "#1F497D", "thickness": 0.25},
                "bgcolor": "white",
                "steps": [
                    {"range": [0, 3], "color": "#F8D7DA"},
                    {"range": [3, 10], "color": "#FFF3CD"},
                    {"range": [10, 25], "color": "#D4EDDA"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 3},
                    "thickness": 0.8,
                    "value": p_cur,
                },
            },
        )
    )
    fig.update_layout(height=height, margin=dict(l=15, r=15, t=42, b=10))
    return fig


st.title("Мониторинг гелиевых баллонов — 6 приборов")

df_raw = init_data()
df_calc = compute_metrics(df_raw)

# Формируем список из 6 приборов (берём из DEFAULT_DEVICES + любые добавленные вручную)
extra_devices = [
    d for d in df_calc["Прибор"].dropna().unique().tolist()
    if str(d).strip() and d not in DEFAULT_DEVICES
]
grid_devices = (DEFAULT_DEVICES + extra_devices)[:6]
while len(grid_devices) < 6:
    grid_devices.append(f"Прибор {len(grid_devices) + 1}")

# Последняя запись по каждому прибору
latest_map = {}
if not df_calc.empty:
    latest_rows = (
        df_calc.sort_values(["Дата", "№"])
        .groupby("Прибор", as_index=False)
        .last()
    )
    for _, r in latest_rows.iterrows():
        latest_map[str(r["Прибор"]).strip()] = r

st.subheader("Обзор всех 6 приборов (сетка 3×2)")

for row_idx in range(2):
    cols = st.columns(3)
    for col_idx in range(3):
        dev_name = grid_devices[row_idx * 3 + col_idx]
        with cols[col_idx]:
            if dev_name in latest_map:
                r = latest_map[dev_name]
                p_val = float(r["P_тек"])
                cyl_label = r["№ Баллона"] if str(r["№ Баллона"]).strip() else "—"
                st.plotly_chart(
                    make_mini_gauge(p_val, f"{dev_name} (Баллон №{cyl_label})"),
                    use_container_width=True,
                )
                rem_str = f"{r['Остаток_л']:,.0f}".replace(",", " ")
                st.caption(
                    f"Дата: {r['Дата']} | Остаток: {rem_str} л ({r['% Заполнения']:.1f}%) | "
                    f"Статус: {r['Статус']}"
                )
            else:
                st.plotly_chart(
                    make_mini_gauge(0.0, f"{dev_name} (нет данных)"),
                    use_container_width=True,
                )
                st.caption("Замеров пока нет — добавьте запись в форме ниже.")

st.divider()

# Сводная таблица по последнему состоянию приборов
st.subheader("Сводка по приборам")
if not df_calc.empty:
    summary_view = (
        df_calc.sort_values(["Прибор", "Дата", "№"])
        .groupby("Прибор", as_index=False)
        .last()[["Прибор", "№ Баллона", "Дата", "P_тек", "Остаток_л", "Расход_л", "% Заполнения", "Статус"]]
        .copy()
    )
    summary_view["P_тек"] = summary_view["P_тек"].map(lambda x: f"{x:.1f} МПа")
    summary_view["Остаток_л"] = summary_view["Остаток_л"].map(lambda x: f"{x:,.1f}".replace(",", " "))
    summary_view["Расход_л"] = summary_view["Расход_л"].map(lambda x: f"{x:,.1f}".replace(",", " "))
    summary_view["% Заполнения"] = summary_view["% Заполнения"].map(lambda x: f"{x:.1f}%")
    st.dataframe(summary_view, use_container_width=True, hide_index=True)
else:
    st.info("Журнал пока пуст.")

st.divider()

# Форма добавления нового замера
st.subheader("Добавить новый замер")
with st.form("add_reading_form", clear_on_submit=True):
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)

    if not df_raw.empty:
        next_num = int(pd.to_numeric(df_raw["№"], errors="coerce").max() or 0) + 1
        parsed_last_date = pd.to_datetime(df_raw["Дата"].iloc[-1], errors="coerce")
        last_date = (
            parsed_last_date + pd.DateOffset(months=1)
            if pd.notna(parsed_last_date)
            else pd.Timestamp.today()
        )
        last_dev = str(df_raw["Прибор"].iloc[-1] or DEFAULT_DEVICES[0])
        last_op = str(df_raw["Пост / Оператор"].iloc[-1] or "")
        last_cyl = str(df_raw["№ Баллона"].iloc[-1] or "")
        last_v = float(pd.to_numeric(df_raw["V_л"].iloc[-1], errors="coerce") or 40.0)
        last_p0 = float(pd.to_numeric(df_raw["P_нач"].iloc[-1], errors="coerce") or 15.0)
    else:
        next_num = 1
        last_date = pd.Timestamp.today()
        last_dev = DEFAULT_DEVICES[0]
        last_op = ""
        last_cyl = ""
        last_v = 40.0
        last_p0 = 15.0

    dev_options = grid_devices if last_dev in grid_devices else [last_dev] + grid_devices
    f_date = c1.date_input("Дата", value=last_date)
    f_dev = c2.selectbox("Прибор", options=dev_options, index=dev_options.index(last_dev))
    f_op = c3.text_input("Пост / Оператор", value=last_op)
    f_cyl = c4.text_input("№ Баллона", value=last_cyl)
    f_v
