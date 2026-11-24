import math
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


def p_to_angle_deg(p_val: float) -> float:
    """
    Переводит давление 0..25 МПа в угол шкалы в стиле ТМ2:
    0 МПа -> нижний левый угол (225°),
    12.5 МПа -> верх (90°),
    25 МПа -> нижний правый угол (-45°).
    """
    clamped = max(0.0, min(P_MAX, float(p_val)))
    return 225.0 - (clamped / P_MAX) * 270.0


def make_tm2_gauge(p_cur: float, title_text: str, height: int = 310) -> go.Figure:
    fig = go.Figure()

    r_outer = 1.0
    r_tick_major = 0.82
    r_tick_minor = 0.89
    r_label = 0.66
    r_needle = 0.79
    r_tail = 0.17

    # Внешний жирный обод циферблата
    ring_angles = [math.radians(a) for a in range(0, 361, 3)]
    fig.add_trace(
        go.Scatter(
            x=[r_outer * math.cos(a) for a in ring_angles],
            y=[r_outer * math.sin(a) for a in ring_angles],
            mode="lines",
            fill="toself",
            fillcolor="#FFFFFF",
            line=dict(color="#4A90E2", width=6),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Внутреннее кольцо шкалы
    arc_deg = [225.0 - (i / 100.0) * 270.0 for i in range(101)]
    fig.add_trace(
        go.Scatter(
            x=[0.95 * math.cos(math.radians(a)) for a in arc_deg],
            y=[0.95 * math.sin(math.radians(a)) for a in arc_deg],
            mode="lines",
            line=dict(color="#1B3F66", width=2.5),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Деления через каждые 1 МПа (крупные каждые 5 МПа)
    for p_tick in range(0, int(P_MAX) + 1):
        ang = math.radians(p_to_angle_deg(p_tick))
        is_major = (p_tick % 5 == 0)
        r_start = r_tick_major if is_major else r_tick_minor
        tick_color = "#C00000" if p_tick == 16 else ("#16365C" if is_major else "#3B6FA8")
        tick_width = 4.5 if is_major else 2.2

        fig.add_trace(
            go.Scatter(
                x=[r_start * math.cos(ang), 0.95 * math.cos(ang)],
                y=[r_start * math.sin(ang), 0.95 * math.sin(ang)],
                mode="lines",
                line=dict(color=tick_color, width=tick_width),
                hoverinfo="skip",
                showlegend=False,
            )
        )

        if is_major:
            fig.add_trace(
                go.Scatter(
                    x=[r_label * math.cos(ang)],
                    y=[r_label * math.sin(ang)],
                    mode="text",
                    text=[f"<b>{p_tick}</b>"],
                    textfont=dict(size=16, color="#16365C", family="Arial"),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    # Подписи на циферблате
    fig.add_annotation(
        x=0.0, y=-0.36, text="<b>MPa</b>", showarrow=False,
        font=dict(size=16, color="#16365C")
    )
    fig.add_annotation(
        x=-0.48, y=-0.62, text="<b>ТМ2</b>", showarrow=False,
        font=dict(size=11, color="#333333")
    )
    fig.add_annotation(
        x=0.48, y=-0.62, text="<b>кл. 2,5</b>", showarrow=False,
        font=dict(size=11, color="#333333")
    )

    # Жирная стрелка от центра
    needle_ang = math.radians(p_to_angle_deg(p_cur))
    x_tip = r_needle * math.cos(needle_ang)
    y_tip = r_needle * math.sin(needle_ang)
    x_back = -r_tail * math.cos(needle_ang)
    y_back = -r_tail * math.sin(needle_ang)

    fig.add_trace(
        go.Scatter(
            x=[x_back, x_tip],
            y=[y_back, y_tip],
            mode="lines",
            line=dict(color="#111111", width=6.5),
            hovertemplate=f"Давление: {p_cur:.1f} МПа<extra></extra>",
            showlegend=False,
        )
    )

    # Наконечник стрелки
    fig.add_trace(
        go.Scatter(
            x=[x_tip],
            y=[y_tip],
            mode="markers",
            marker=dict(
                symbol="triangle-up",
                size=14,
                color="#111111",
                angle=-(p_to_angle_deg(p_cur) - 90.0),
            ),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Крупный центральный узел стрелки
    fig.add_trace(
        go.Scatter(
            x=[0.0],
            y=[0.0],
            mode="markers",
            marker=dict(size=16, color="#1A1A1A", line=dict(color="#D9D9D9", width=2.5)),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    fig.update_layout(
        title=dict(text=f"<b>{title_text}</b>", x=0.5, font=dict(size=15)),
        height=height,
        margin=dict(l=2, r=2, t=34, b=2),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            range=[-1.03, 1.03],
            visible=False,
            fixedrange=True,
        ),
        yaxis=dict(
            range=[-1.03, 1.03],
            visible=False,
            fixedrange=True,
            scaleanchor="x",
            scaleratio=1,
        ),
    )
    return fig


st.title("Мониторинг гелиевых баллонов — 6 приборов")

df_raw = init_data()
df_calc = compute_metrics(df_raw)

extra_devices = [
    d for d in df_calc["Прибор"].dropna().unique().tolist()
    if str(d).strip() and d not in DEFAULT_DEVICES
]
grid_devices = (DEFAULT_DEVICES + extra_devices)[:6]
while len(grid_devices) < 6:
    grid_devices.append(f"Прибор {len(grid_devices) + 1}")

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
                    make_tm2_gauge(p_val, f"{dev_name} (Баллон №{cyl_label})", height=310),
                    use_container_width=True,
                )
                rem_str = f"{r['Остаток_л']:,.0f}".replace(",", " ")
                st.caption(
                    f"P = {p_val:.1f} МПа | Дата: {r['Дата']} | Остаток: {rem_str} л "
                    f"({r['% Заполнения']:.1f}%) | Статус: {r['Статус']}"
                )
            else:
                st.plotly_chart(
                    make_tm2_gauge(0.0, f"{dev_name} (нет данных)", height=310),
                    use_container_width=True,
                )
                st.caption("P = 0.0 МПа | Замеров пока нет — добавьте запись ниже.")

st.divider()

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

st.subheader("Добавить новый замер")

if not df_raw.empty:
    next_num = int(pd.to_numeric(df_raw["№"], errors="coerce").max() or 0) + 1
    parsed_last_date = pd.to_datetime(df_raw["Дата"].iloc[-1], errors="coerce")
    default_date = (
        parsed_last_date + pd.DateOffset(months=1)
        if pd.notna(parsed_last_date)
        else pd.Timestamp.today()
    )
    default_dev = str(df_raw["Прибор"].iloc[-1] or DEFAULT_DEVICES[0])
    default_op = str(df_raw["Пост / Оператор"].iloc[-1] or "")
    default_cyl = str(df_raw["№ Баллона"].iloc[-1] or "")
    default_v = float(pd.to_numeric(df_raw["V_л"].iloc[-1], errors="coerce") or 40.0)
    default_p0 = float(pd.to_numeric(df_raw["P_нач"].iloc[-1], errors="coerce") or 15.0)
else:
    next_num = 1
    default_date = pd.Timestamp.today()
    default_dev = DEFAULT_DEVICES[0]
    default_op = ""
    default_cyl = ""
    default_v = 40.0
    default_p0 = 15.0

dev_options = grid_devices if default_dev in grid_devices else [default_dev] + grid_devices

with st.form("add_reading_form", clear_on_submit=True):
    row1_c1, row1_c2, row1_c3, row1_c4 = st.columns(4)
    f_date = row1_c1.date_input("Дата", value=default_date)
    f_dev = row1_c2.selectbox("Прибор", options=dev_options, index=dev_options.index(default_dev))
    f_op = row1_c3.text_input("Пост / Оператор", value=default_op)
    f_cyl = row1_c4.text_input("№ Баллона", value=default_cyl)

    row2_c1, row2_c2, row2_c3 = st.columns(3)
    f_v = row2_c1.number_input("V баллона, л", min_value=1.0, max_value=200.0, value=default_v, step=5.0)
    f_p0 = row2_c2.number_input("P нач., МПа", min_value=0.1, max_value=30.0, value=default_p0, step=0.5)
    f_p1 = row2_c3.number_input("P тек., МПа", min_value=0.0, max_value=30.0, value=10.0, step=0.5)

    submitted = st.form_submit_button("Добавить запись в журнал")
    if submitted:
        new_entry = pd.DataFrame([{
            "№": next_num,
            "Дата": f_date.strftime("%Y-%m-%d"),
            "Прибор": f_dev,
            "Пост / Оператор": f_op,
            "№ Баллона": f_cyl,
            "V_л": float(f_v),
            "P_нач": float(f_p0),
            "P_тек": float(f_p1),
        }])
        updated = pd.concat([df_raw, new_entry], ignore_index=True)
        updated.to_csv(DATA_FILE, index=False)
        st.rerun()

st.divider()

st.subheader("Журнал замеров")

filter_options = ["Все приборы"] + grid_devices
selected_filter = st.selectbox("Показать в журнале:", options=filter_options)

with st.expander("Управление журналом"):
    confirm_clear = st.checkbox("Подтверждаю очистку всех записей из журнала")
    if st.button("Очистить журнал", disabled=not confirm_clear):
        empty_df = pd.DataFrame(columns=COLUMNS)
        empty_df.to_csv(DATA_FILE, index=False)
        st.rerun()

if not df_calc.empty:
    table_src = (
        df_calc
        if selected_filter == "Все приборы"
        else df_calc[df_calc["Прибор"] == selected_filter]
    )
    display_df = table_src.copy()
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
