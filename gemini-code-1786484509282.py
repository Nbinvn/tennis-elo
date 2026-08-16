import json
import os
import uuid
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_cookies_controller import CookieController
import requests

# --- CONFIGURATION ---
ADMIN_PWD = "Admin2026"

# --- GESTION DE LA BASE DE DONNÉES (CLOUD) ---
JSONBIN_ID = st.secrets["JSONBIN_ID"]
JSONBIN_KEY = st.secrets["JSONBIN_KEY"]
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}"
HEADERS = {
    "X-Master-Key": JSONBIN_KEY,
    "Content-Type": "application/json"
}

def init_db():
    return load_db()

def load_db():
    try:
        response = requests.get(JSONBIN_URL, headers=HEADERS)
        return response.json()["record"]
    except Exception as e:
        st.error(f"Erreur lors du chargement de la base de données : {e}")
        return {"players": {}, "matches": {}, "history": []} 

def save_db(db):
    try:
        requests.put(JSONBIN_URL, json=db, headers=HEADERS)
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")

# --- FONCTIONS MATHÉMATIQUES & ELO ---
def get_prob(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))

def get_probs_with_draw(elo_a, elo_b):
    p_a_raw = get_prob(elo_a, elo_b)
    p_b_raw = 1 - p_a_raw
    prob_draw = 0.15 * (1 - abs(p_a_raw - p_b_raw))
    prob_a = p_a_raw * (1 - prob_draw)
    prob_b = p_b_raw * (1 - prob_draw)
    return prob_a, prob_b, prob_draw

def get_odds(prob):
    return round(1 / prob, 2) if prob > 0 else 1.01

def get_match_odds_at_time(db, target_m_id):
    """Calcule les cotes d'un match telles qu'elles étaient AVANT qu'il ne soit joué."""
    temp_elos = {pid: 1000.0 for pid in db["players"]}
    completed_matches = [(mid, m) for mid, m in db["matches"].items() if m["status"] == "completed"]
    completed_matches.sort(key=lambda x: x[1]["datetime"])
    
    for mid, m in completed_matches:
        if mid == target_m_id:
            break # On s'arrête juste avant le match ciblé pour conserver les ELO d'avant-match
        
        match_type = m.get("type", "singles")
        winner = m["winner"]
        K = 32
        
        if match_type == "singles":
            p1, p2 = m["p1"], m["p2"]
            p_1_raw = get_prob(temp_elos[p1], temp_elos[p2])
            if winner == p1: s1, s2 = 1, 0
            elif winner == p2: s1, s2 = 0, 1
            else: s1, s2 = 0.5, 0.5
            temp_elos[p1] += K * (s1 - p_1_raw)
            temp_elos[p2] += K * (s2 - (1 - p_1_raw))
        else:
            t1, t2 = m["t1"], m["t2"]
            elo_t1 = (temp_elos[t1[0]] + temp_elos[t1[1]]) / 2
            elo_t2 = (temp_elos[t2[0]] + temp_elos[t2[1]]) / 2
            p_1_raw = get_prob(elo_t1, elo_t2)
            if winner == "t1": s1, s2 = 1, 0
            elif winner == "t2": s1, s2 = 0, 1
            else: s1, s2 = 0.5, 0.5
            for pid in t1: temp_elos[pid] += K * (s1 - p_1_raw)
            for pid in t2: temp_elos[pid] += K * (s2 - (1 - p_1_raw))

    m_target = db["matches"][target_m_id]
    if m_target.get("type", "singles") == "singles":
        elo_1, elo_2 = temp_elos[m_target["p1"]], temp_elos[m_target["p2"]]
    else:
        elo_1 = (temp_elos[m_target["t1"][0]] + temp_elos[m_target["t1"][1]]) / 2
        elo_2 = (temp_elos[m_target["t2"][0]] + temp_elos[m_target["t2"][1]]) / 2
        
    prob_p1, prob_p2, prob_draw = get_probs_with_draw(elo_1, elo_2)
    return get_odds(prob_p1), get_odds(prob_p2), get_odds(prob_draw)

def recalculate_all_stats(db):
    for pid in db["players"]:
        db["players"][pid]["elo"] = 1000.0
        db["players"][pid]["prono_points"] = 0
        db["players"][pid]["stats_played"] = 0
        db["players"][pid]["stats_won"] = 0

    completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
    completed_matches.sort(key=lambda x: x["datetime"])

    for m in completed_matches:
        match_type = m.get("type", "singles")
        winner = m["winner"]
        K = 32
        
        if match_type == "singles":
            p1, p2 = m["p1"], m["p2"]
            elo_1, elo_2 = db["players"][p1]["elo"], db["players"][p2]["elo"]
            p_1_raw = get_prob(elo_1, elo_2)
            p_2_raw = 1 - p_1_raw
            
            if winner == p1: score_1, score_2 = 1, 0
            elif winner == p2: score_1, score_2 = 0, 1
            else: score_1, score_2 = 0.5, 0.5
            
            db["players"][p1]["elo"] += K * (score_1 - p_1_raw)
            db["players"][p2]["elo"] += K * (score_2 - p_2_raw)
            db["players"][p1]["stats_played"] += 1
            db["players"][p2]["stats_played"] += 1
            if winner == p1: db["players"][p1]["stats_won"] += 1
            elif winner == p2: db["players"][p2]["stats_won"] += 1
            
        else: # doubles
            t1, t2 = m["t1"], m["t2"]
            elo_t1 = (db["players"][t1[0]]["elo"] + db["players"][t1[1]]["elo"]) / 2
            elo_t2 = (db["players"][t2[0]]["elo"] + db["players"][t2[1]]["elo"]) / 2
            p_1_raw = get_prob(elo_t1, elo_t2)
            p_2_raw = 1 - p_1_raw
            
            if winner == "t1": score_1, score_2 = 1, 0
            elif winner == "t2": score_1, score_2 = 0, 1
            else: score_1, score_2 = 0.5, 0.5
            
            for pid in t1:
                db["players"][pid]["elo"] += K * (score_1 - p_1_raw)
                db["players"][pid]["stats_played"] += 1
                if winner == "t1": db["players"][pid]["stats_won"] += 1
            for pid in t2:
                db["players"][pid]["elo"] += K * (score_2 - p_2_raw)
                db["players"][pid]["stats_played"] += 1
                if winner == "t2": db["players"][pid]["stats_won"] += 1
        
        for bet in m.get("bets", []):
            if bet["predicted"] == winner:
                db["players"][bet["bettor"]]["prono_points"] += int(bet["odds"] * 10)

def get_elo_history_df(db):
    records = []
    base_date = datetime(2026, 8, 10)
    
    states = {pid: {"elo": 1000.0, "played": 0, "won": 0} for pid in db["players"]}
    for pid, p in db["players"].items():
        records.append({"Joueur": p["name"], "Date": base_date, "ELO": 1000.0, "Matchs": 0, "Victoires": 0})
        
    completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
    completed_matches.sort(key=lambda x: x["datetime"])
    
    for m in completed_matches:
        dt = datetime.fromisoformat(m["datetime"])
        match_type = m.get("type", "singles")
        winner = m["winner"]
        K = 32
        
        if match_type == "singles":
            p1, p2 = m["p1"], m["p2"]
            elo_1, elo_2 = states[p1]["elo"], states[p2]["elo"]
            p_1_raw = get_prob(elo_1, elo_2)
            p_2_raw = 1 - p_1_raw
            
            if winner == p1: score_1, score_2 = 1, 0
            elif winner == p2: score_1, score_2 = 0, 1
            else: score_1, score_2 = 0.5, 0.5
            
            states[p1]["elo"] += K * (score_1 - p_1_raw)
            states[p2]["elo"] += K * (score_2 - p_2_raw)
            states[p1]["played"] += 1
            states[p2]["played"] += 1
            if winner == p1: states[p1]["won"] += 1
            elif winner == p2: states[p2]["won"] += 1
            
        else: # doubles
            t1, t2 = m["t1"], m["t2"]
            elo_t1 = (states[t1[0]]["elo"] + states[t1[1]]["elo"]) / 2
            elo_t2 = (states[t2[0]]["elo"] + states[t2[1]]["elo"]) / 2
            p_1_raw = get_prob(elo_t1, elo_t2)
            p_2_raw = 1 - p_1_raw
            
            if winner == "t1": score_1, score_2 = 1, 0
            elif winner == "t2": score_1, score_2 = 0, 1
            else: score_1, score_2 = 0.5, 0.5
            
            for pid in t1:
                states[pid]["elo"] += K * (score_1 - p_1_raw)
                states[pid]["played"] += 1
                if winner == "t1": states[pid]["won"] += 1
            for pid in t2:
                states[pid]["elo"] += K * (score_2 - p_2_raw)
                states[pid]["played"] += 1
                if winner == "t2": states[pid]["won"] += 1
                
        for pid, p in db["players"].items():
            records.append({
                "Joueur": p["name"], "Date": dt, "ELO": states[pid]["elo"],
                "Matchs": states[pid]["played"], "Victoires": states[pid]["won"]
            })
            
    now = datetime.now()
    for pid, p in db["players"].items():
        records.append({
            "Joueur": p["name"], "Date": now, "ELO": states[pid]["elo"],
            "Matchs": states[pid]["played"], "Victoires": states[pid]["won"]
        })
        
    df = pd.DataFrame(records)
    df["Ratio"] = (df["Victoires"] / df["Matchs"] * 100).fillna(0)
    df = df.sort_values(by=["Joueur", "Date"], key=lambda col: col.str.lower() if col.name == "Joueur" else col)
    return df

# --- INITIALISATION SESSION & COOKIES ---
db = init_db()
cookie_controller = CookieController()

if "user_id" not in st.session_state:
    st.session_state.user_id = cookie_controller.get("user_id")
if "is_admin" not in st.session_state:
    st.session_state.is_admin = (cookie_controller.get("is_admin") == "true")

# --- SYSTÈME D'AUTHENTIFICATION ---
if st.session_state.user_id is None and not st.session_state.is_admin:
    st.title("🔒 Connexion - Tennis Pronos & ELO")
    tab_login, tab_admin = st.tabs(["Joueur", "Administrateur"])
    
    with tab_login:
        if not db["players"]:
            st.info("Aucun joueur n'est inscrit. Connectez-vous en tant qu'administrateur pour en créer.")
        else:
            player_names = {p_id: p_data["name"] for p_id, p_data in db["players"].items()}
            sorted_names = sorted(list(player_names.values()), key=lambda x: x.lower())
            
            with st.form(key="login_player_form"):
                selected_name = st.selectbox("Qui êtes-vous ?", sorted_names)
                pwd = st.text_input("Mot de passe", type="password")
                submit_login = st.form_submit_button("Se connecter")
                
                if submit_login:
                    p_id = next(uid for uid, name in player_names.items() if name == selected_name)
                    if pwd == db["players"][p_id]["password"]:
                        st.session_state.user_id = p_id
                        cookie_controller.set("user_id", p_id)
                        st.rerun()
                    else:
                        st.error("Mot de passe incorrect")
                    
    with tab_admin:
        with st.form(key="login_admin_form"):
            admin_pwd_input = st.text_input("Mot de passe administrateur", type="password")
            submit_admin = st.form_submit_button("Accès Admin")
            if submit_admin:
                if admin_pwd_input == ADMIN_PWD:
                    st.session_state.is_admin = True
                    cookie_controller.set("is_admin", "true")
                    st.rerun()
                else:
                    st.error("Mot de passe administrateur incorrect")
    st.stop() 

# --- BARRE LATÉRALE (DASHBOARD UTILISATEUR) ---
with st.sidebar:
    if st.session_state.is_admin:
        st.write("👤 **Connecté en tant que : ADMIN GLOBALE**")
        st.divider()
    else:
        uid = st.session_state.user_id
        user_data = db["players"][uid]
        nom_joueur = user_data["name"]
        
        st.write(f"👤 **Connecté : {nom_joueur}**")
        st.divider()
        
        all_players_elo = sorted(db["players"].keys(), key=lambda x: (-db["players"][x]["elo"], db["players"][x]["name"].lower()))
        all_players_prono = sorted(db["players"].keys(), key=lambda x: (-db["players"][x].get("prono_points", 0), db["players"][x]["name"].lower()))
        
        rank_elo = all_players_elo.index(uid) + 1
        rank_prono = all_players_prono.index(uid) + 1
        total_players = len(db["players"])
        
        pts_prono = user_data.get("prono_points", 0)
        user_elo = int(user_data["elo"])
        played = user_data["stats_played"]
        won = user_data["stats_won"]
        
        completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
        user_matches = []
        for m in completed_matches:
            m_type = m.get("type", "singles")
            if m_type == "singles" and (m["p1"] == uid or m["p2"] == uid): user_matches.append(m)
            elif m_type == "doubles" and (uid in m["t1"] or uid in m["t2"]): user_matches.append(m)
        user_matches.sort(key=lambda x: x["datetime"], reverse=True)
        
        draws = len([m for m in user_matches if m["winner"] == "draw"])
        losses = played - won - draws
        
        st.markdown("#### 🎯 Pronostics")
        st.write(f"**Points :** {pts_prono}")
        st.write(f"**Classement :** {rank_prono} / {total_players}")
        
        st.markdown("#### 🏆 Score ELO")
        st.write(f"**Points :** {user_elo}")
        st.write(f"**Classement :** {rank_elo} / {total_players}")
        
        st.markdown("#### 🎾 Mes Matchs")
        st.write(f"**Joués :** {played}")
        col_v, col_n, col_d = st.columns(3)
        with col_v: st.markdown(f"<div style='text-align:center;'>✅<br><b>{won}</b></div>", unsafe_allow_html=True)
        with col_n: st.markdown(f"<div style='text-align:center;'>🤝<br><b>{draws}</b></div>", unsafe_allow_html=True)
        with col_d: st.markdown(f"<div style='text-align:center;'>❌<br><b>{losses}</b></div>", unsafe_allow_html=True)
            
        st.markdown("<br>#### 📅 Dernier résultat", unsafe_allow_html=True)
        if user_matches:
            last_m = user_matches[0]
            dt_last = datetime.fromisoformat(last_m["datetime"]).strftime('%d/%m/%Y')
            m_type = last_m.get("type", "singles")
            
            if m_type == "singles":
                opp_id = last_m["p2"] if last_m["p1"] == uid else last_m["p1"]
                opp_name = db["players"][opp_id]["name"]
                is_win = (last_m["winner"] == uid)
            else:
                if uid in last_m["t1"]:
                    opp_team = last_m["t2"]
                    is_win = (last_m["winner"] == "t1")
                else:
                    opp_team = last_m["t1"]
                    is_win = (last_m["winner"] == "t2")
                opp_names = sorted([db['players'][opp_team[0]]['name'], db['players'][opp_team[1]]['name']], key=str.lower)
                opp_name = " & ".join(opp_names)

            if last_m["winner"] == "draw":
                res_txt, res_col = "Match Nul 🤝", "#9CA3AF"
            elif is_win:
                res_txt, res_col = "Victoire ✅", "#10B981"
            else:
                res_txt, res_col = "Défaite ❌", "#EF4444"
                
            st.markdown(f"""
            <div style="background-color: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px; border-left: 4px solid {res_col};">
                <p style="margin:0; font-size: 13px; color: #9CA3AF;">{dt_last}</p>
                <p style="margin:5px 0; font-weight: bold; font-size: 15px;">🆚 {opp_name}</p>
                <p style="margin:0; color: {res_col}; font-weight: bold;">{res_txt}</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Aucun match joué")
        st.divider()

    if st.button("Se déconnecter", use_container_width=True):
        st.session_state.user_id = None
        st.session_state.is_admin = False
        try: cookie_controller.remove("user_id")
        except KeyError: pass
        try: cookie_controller.remove("is_admin")
        except KeyError: pass
        st.rerun()

# --- INTERFACE PRINCIPALE ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🏆 Classement ELO", "📅 Matchs & Pronos", "🎯 Classement Pronos", "📜 Historique", "📊 Dashboard", "🛠️ Admin"])

# --- TAB 1 : CLASSEMENT ELO VISUEL ---
with tab1:
    st.header("🏆 Classement ELO des Joueurs")
    players_items = list(db["players"].items())
    players_items.sort(key=lambda x: (-x[1]["elo"], x[1]["name"].lower()))
    
    if not players_items:
        st.info("Aucun joueur n'est inscrit.")
    else:
        completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
        df_data = []
        for i, (pid, p) in enumerate(players_items, 1):
            draws = 0
            for m in completed_matches:
                if m["winner"] == "draw":
                    if m.get("type", "singles") == "singles" and (m["p1"] == pid or m["p2"] == pid): draws += 1
                    elif m.get("type", "singles") == "doubles" and (pid in m["t1"] or pid in m["t2"]): draws += 1
            losses = p["stats_played"] - p["stats_won"] - draws
            win_rate = (p["stats_won"] / p["stats_played"] * 100) if p["stats_played"] > 0 else 0
            
            df_data.append({
                "Rang": i, "Joueur": p["name"], "ELO": int(p["elo"]),
                "Matchs": p["stats_played"], "Victoires": p["stats_won"], 
                "Nuls": draws, "Défaites": losses, "Taux de Victoire": win_rate
            })
            
        df = pd.DataFrame(df_data)
        st.dataframe(
            df,
            column_config={
                "Rang": st.column_config.NumberColumn("Rang", format="%d 🏅"),
                "ELO": st.column_config.ProgressColumn("Points ELO", min_value=800, max_value=max(int(df["ELO"].max()) + 50, 1200), format="%d pts"),
                "Matchs": st.column_config.NumberColumn("Matchs"),
                "Victoires": st.column_config.NumberColumn("V", help="Victoires"),
                "Nuls": st.column_config.NumberColumn("N", help="Matchs Nuls"),
                "Défaites": st.column_config.NumberColumn("D", help="Défaites"),
                "Taux de Victoire": st.column_config.ProgressColumn("Taux de Victoire", min_value=0, max_value=100, format="%d %%")
            }, hide_index=True, use_container_width=True
        )
        
        st.divider()
        st.subheader("📈 Historique des leaders et évolution ELO")
        time_filter = st.radio("Filtre temporel :", ["Depuis le début", "30 derniers jours", "7 derniers jours"], horizontal=True)
        df_hist = get_elo_history_df(db)
        
        if time_filter == "30 derniers jours": df_hist = df_hist[df_hist["Date"] >= datetime.now() - timedelta(days=30)]
        elif time_filter == "7 derniers jours": df_hist = df_hist[df_hist["Date"] >= datetime.now() - timedelta(days=7)]

        if not df_hist.empty:
            df_hist["Info_Joueur"] = df_hist.apply(lambda x: f"• <b>{x['Joueur']}</b> (M: {x['Matchs']} | V: {x['Victoires']})", axis=1)
            df_hist["Infos_Combinees"] = df_hist.groupby(["Date", "ELO"])["Info_Joueur"].transform(lambda x: "<br>".join(x))
            fig = px.line(df_hist, x="Date", y="ELO", color="Joueur", markers=True, hover_data={"Date": "|%d/%m/%Y %H:%M", "Infos_Combinees": True})
            fig.update_traces(mode="lines+markers", line=dict(width=3), marker=dict(size=6), hovertemplate="Date : <b>%{x}</b><br>Score ELO : <b>%{y:.0f} pts</b><br><br>%{customdata[0]}<extra></extra>")
            fig.update_layout(hovermode="closest", legend_title="Joueurs", xaxis_title="", yaxis_title="Score ELO", margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            fig.update_yaxes(showgrid=True, gridcolor='rgba(255,255,255,0.1)')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune donnée disponible pour cette période.")

# --- TAB 2 : MATCHS ET PRONOS ---
with tab2:
    st.header("📅 Matchs & Pronostics")
    
    with st.expander("➕ Créer un nouveau match", expanded=False):
        match_format = st.radio("Format du match", ["Simple (1v1)", "Double (2v2)"], horizontal=True)
        all_players_sorted = sorted(list(db["players"].keys()), key=lambda x: db["players"][x]["name"].lower())
        
        with st.form("form_create_match"):
            if match_format == "Simple (1v1)":
                c1, c2 = st.columns(2)
                with c1:
                    p1 = st.selectbox("Joueur 1", all_players_sorted, format_func=lambda x: db["players"][x]["name"])
                    d = st.date_input("Date du match")
                with c2:
                    p2 = st.selectbox("Joueur 2", all_players_sorted, format_func=lambda x: db["players"][x]["name"], index=1 if len(all_players_sorted)>1 else 0)
                    t = st.time_input("Heure du match")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Équipe 1**")
                    t1_p1 = st.selectbox("Joueur 1 (Éq 1)", all_players_sorted, format_func=lambda x: db["players"][x]["name"])
                    t1_p2 = st.selectbox("Joueur 2 (Éq 1)", all_players_sorted, format_func=lambda x: db["players"][x]["name"], index=1 if len(all_players_sorted)>1 else 0)
                    d = st.date_input("Date du match")
                with c2:
                    st.markdown("**Équipe 2**")
                    t2_p1 = st.selectbox("Joueur 1 (Éq 2)", all_players_sorted, format_func=lambda x: db["players"][x]["name"], index=2 if len(all_players_sorted)>2 else 0)
                    t2_p2 = st.selectbox("Joueur 2 (Éq 2)", all_players_sorted, format_func=lambda x: db["players"][x]["name"], index=3 if len(all_players_sorted)>3 else 0)
                    t = st.time_input("Heure du match")

            if st.form_submit_button("Programmer le match"):
                if match_format == "Simple (1v1)" and p1 == p2:
                    st.error("Les joueurs doivent être différents.")
                elif match_format == "Double (2v2)" and len({t1_p1, t1_p2, t2_p1, t2_p2}) < 4:
                    st.error("Les 4 joueurs doivent être distincts pour un match en double.")
                else:
                    dt_str = datetime.combine(d, t).isoformat()
                    m_id = str(uuid.uuid4())
                    if match_format == "Simple (1v1)":
                        db["matches"][m_id] = {"type": "singles", "p1": p1, "p2": p2, "datetime": dt_str, "status": "pending", "winner": None, "bets": []}
                    else:
                        db["matches"][m_id] = {"type": "doubles", "t1": [t1_p1, t1_p2], "t2": [t2_p1, t2_p2], "datetime": dt_str, "status": "pending", "winner": None, "bets": []}
                    save_db(db)
                    st.success("Match programmé !")
                    st.rerun()
            
    st.divider()
    st.subheader("🔥 Matchs à venir & Pronostics")
    pending_matches = {k: v for k, v in db["matches"].items() if v["status"] == "pending"}
    pending_matches = dict(sorted(pending_matches.items(), key=lambda item: item[1]["datetime"]))
    
    if not pending_matches:
        st.info("Aucun match prévu pour le moment.")
        
    for m_id, m in pending_matches.items():
        m_type = m.get("type", "singles")
        dt = datetime.fromisoformat(m["datetime"])
        
        if m_type == "singles":
            name1, name2 = db["players"][m["p1"]]["name"], db["players"][m["p2"]]["name"]
            elo_1, elo_2 = db["players"][m["p1"]]["elo"], db["players"][m["p2"]]["elo"]
            opt_1, opt_2 = m["p1"], m["p2"]
            is_playing = st.session_state.user_id in [m["p1"], m["p2"]]
        else:
            team1_names = sorted([db['players'][pid]['name'] for pid in m['t1']], key=str.lower)
            team2_names = sorted([db['players'][pid]['name'] for pid in m['t2']], key=str.lower)
            name1 = " & ".join(team1_names)
            name2 = " & ".join(team2_names)
            
            elo_1 = (db["players"][m["t1"][0]]["elo"] + db["players"][m["t1"][1]]["elo"]) / 2
            elo_2 = (db["players"][m["t2"][0]]["elo"] + db["players"][m["t2"][1]]["elo"]) / 2
            opt_1, opt_2 = "t1", "t2"
            is_playing = st.session_state.user_id in m["t1"] or st.session_state.user_id in m["t2"]

        prob_p1, prob_p2, prob_draw = get_probs_with_draw(elo_1, elo_2)
        odds_p1, odds_p2, odds_draw = get_odds(prob_p1), get_odds(prob_p2), get_odds(prob_draw)
        
        format_badge = "👤 1v1" if m_type == "singles" else "👥 2v2"
        st.markdown(f"### {format_badge} | {name1} 🆚 {name2}")
        st.caption(f"🕒 Prévu le {dt.strftime('%d/%m/%Y à %H:%M')}")
        st.write(f"Cotes indicatives : **{name1} ({odds_p1})** | **Nul ({odds_draw})** | **{name2} ({odds_p2})**")
        
        st.markdown("#### 👥 Pronostics enregistrés :")
        if m["bets"]:
            cols_bets = st.columns(len(m["bets"]))
            for idx, bet in enumerate(sorted(m["bets"], key=lambda b: db["players"][b["bettor"]]["name"].lower())):
                b_name = db["players"][bet["bettor"]]["name"]
                if bet["predicted"] == "draw": c_text = "Match Nul 🤝"
                elif bet["predicted"] == opt_1: c_text = f"Victoire {name1}"
                else: c_text = f"Victoire {name2}"
                with cols_bets[idx % len(cols_bets)]: st.info(f"**{b_name}**\n\n🎯 *{c_text}*\n\n📈 Cote : {bet['odds']}")
        else:
            st.info("Aucun pronostic validé.")
        
        is_started = datetime.now() > dt
        my_bet = next((b for b in m["bets"] if b["bettor"] == st.session_state.user_id), None)
        
        if my_bet:
            if my_bet['predicted'] == "draw": pred_name = "Match Nul"
            elif my_bet['predicted'] == opt_1: pred_name = name1
            else: pred_name = name2
            st.success(f"✅ Ton pronostic : **{pred_name}** (Cote: {my_bet['odds']})")
        elif is_playing:
            st.warning("Tu ne peux pas pronostiquer sur ton propre match.")
        elif is_started:
            st.error("Match commencé, les pronostics sont fermés.")
        else:
            with st.form(key=f"bet_form_{m_id}"):
                options_pari = {opt_1: f"Victoire {name1}", "draw": "Match Nul", opt_2: f"Victoire {name2}"}
                pred = st.radio("Ton pronostic ?", list(options_pari.keys()), format_func=lambda x: options_pari[x])
                if st.form_submit_button("Valider mon pronostic"):
                    odds_locked = odds_p1 if pred == opt_1 else (odds_p2 if pred == opt_2 else odds_draw)
                    m["bets"] = [b for b in m["bets"] if b["bettor"] != st.session_state.user_id]
                    m["bets"].append({"bettor": st.session_state.user_id, "predicted": pred, "odds": odds_locked})
                    save_db(db)
                    st.success("Pronostic enregistré !")
                    st.rerun()
                    
        with st.expander("🏁 Terminer ce match (Saisir le résultat)"):
            options_result = {opt_1: f"Victoire {name1}", "draw": "Match Nul", opt_2: f"Victoire {name2}"}
            winner = st.radio("Résultat final", list(options_result.keys()), format_func=lambda x: options_result[x], key=f"win_{m_id}")
            if st.button("Valider le résultat et distribuer les points", key=f"btn_{m_id}"):
                m["status"], m["winner"] = "completed", winner
                w_str = f"🤝 Nul entre {name1} et {name2}" if winner == "draw" else f"🏆 {name1 if winner == opt_1 else name2} gagne."
                db["history"].append({"date": datetime.now().isoformat(), "desc": w_str})
                recalculate_all_stats(db)
                save_db(db)
                st.success("Match terminé !")
                st.rerun()
        st.divider()

# --- TAB 3 : CLASSEMENT PRONOS VISUEL (Podium) ---
with tab3:
    st.header("🎯 Classement des Pronostiqueurs")
    seven_days_ago = datetime.now() - timedelta(days=7)
    recent_prono_gains = {pid: 0 for pid in db["players"]}
    
    for m in [m for m in db["matches"].values() if m["status"] == "completed"]:
        if datetime.fromisoformat(m["datetime"]) >= seven_days_ago:
            for bet in m.get("bets", []):
                if bet["predicted"] == m["winner"]:
                    recent_prono_gains[bet["bettor"]] += int(bet["odds"] * 10)

    players_prono = sorted(list(db["players"].items()), key=lambda x: (-x[1].get("prono_points", 0), x[1]["name"].lower()))
    
    if not players_prono:
        st.info("Aucun joueur inscrit.")
    else:
        if len(players_prono) >= 3:
            p1, p2, p3 = players_prono[0], players_prono[1], players_prono[2]
            col_pod2, col_pod1, col_pod3 = st.columns([1, 1.1, 1])
            def draw_podium_card(p_tuple, border, bg, emoji):
                pid, p = p_tuple
                pts = p.get("prono_points", 0)
                rec = recent_prono_gains[pid]
                st.markdown(f"""
                <div style="border: 2px solid {border}; background-color: {bg}; padding: 15px; border-radius: 12px; text-align: center; margin-bottom: 20px;">
                    <div style="font-size: 35px; margin-bottom: 5px;">{emoji}</div>
                    <h3 style="margin: 0 0 5px 0;">{p['name']}</h3>
                    <h2 style="margin: 0; color: {border};">{pts} <span style="font-size: 16px; color: white;">pts</span></h2>
                    <p style="margin: 8px 0 0 0; font-size: 13px;"><span style="color: {'#10B981' if rec>0 else 'gray'}; font-weight: bold;">{'+'+str(rec) if rec>0 else '0'} pts</span> (7j)</p>
                </div>
                """, unsafe_allow_html=True)
                
            with col_pod2: st.write(""); draw_podium_card(p2, "#9CA3AF", "rgba(156, 163, 175, 0.1)", "🥈") 
            with col_pod1: draw_podium_card(p1, "#F59E0B", "rgba(245, 158, 11, 0.15)", "🥇") 
            with col_pod3: st.write(""); st.write(""); draw_podium_card(p3, "#B45309", "rgba(180, 83, 9, 0.1)", "🥉") 

            for i, (pid, p) in enumerate(players_prono[3:], 4):
                pts, rec = p.get("prono_points", 0), recent_prono_gains[pid]
                st.markdown(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background-color: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 15px;">
                        <h4 style="margin: 0; color: #9CA3AF; width: 25px;">{i}</h4><h4 style="margin: 0;">{p['name']}</h4>
                    </div>
                    <div style="text-align: right;">
                        <h4 style="margin: 0;">{pts} pts</h4>
                        <span style="font-size: 13px; color: {'#10B981' if rec>0 else '#9CA3AF'};">{'+'+str(rec) if rec>0 else '0'} pts (7j)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            for i, (pid, p) in enumerate(players_prono, 1): st.write(f"**{i}. {p['name']}** - {p.get('prono_points', 0)} pts")

# --- TAB 4 : HISTORIQUE ---
with tab4:
    st.header("📜 Historique des Matchs")
    completed = [m for m in db["matches"].values() if m["status"] == "completed"]
    completed.sort(key=lambda x: x["datetime"], reverse=True)
    if not completed: st.info("Aucun match terminé.")
    
    for m in completed:
        dt = datetime.fromisoformat(m["datetime"]).strftime('%d/%m/%Y')
        if m.get("type", "singles") == "singles":
            n1, n2 = db["players"][m["p1"]]["name"], db["players"][m["p2"]]["name"]
            opt1 = m["p1"]
        else:
            team1_names = sorted([db['players'][pid]['name'] for pid in m['t1']], key=str.lower)
            team2_names = sorted([db['players'][pid]['name'] for pid in m['t2']], key=str.lower)
            n1, n2 = " & ".join(team1_names), " & ".join(team2_names)
            opt1 = "t1"
            
        if m["winner"] == "draw":
            st.markdown(f"**{dt}** : 🤝 Match Nul entre **{n1}** et **{n2}** ({len(m['bets'])} pronos)")
        else:
            w_name = n1 if m["winner"] == opt1 else n2
            l_name = n2 if m["winner"] == opt1 else n1
            st.markdown(f"**{dt}** : 🏆 **{w_name}** a battu {l_name} ({len(m['bets'])} pronos)")

# --- TAB 5 : DASHBOARD STATS ---
with tab5:
    st.header("📊 Tableau de Bord Global")
    if db["players"]:
        cols = st.columns(2)
        max_prono = max([p.get("prono_points", 0) for p in db["players"].values()], default=0)
        rois = sorted([p["name"] for p in db["players"].values() if p.get("prono_points", 0) == max_prono], key=str.lower)
        
        max_active = max([p["stats_played"] for p in db["players"].values()], default=0)
        actifs = sorted([p["name"] for p in db["players"].values() if p["stats_played"] == max_active], key=str.lower)
        
        with cols[0]: st.metric(f"🎯 Rois des Pronos", f"{max_prono} pts", ", ".join(rois))
        with cols[1]: st.metric(f"🎾 Plus actifs", f"{max_active} matchs", ", ".join(actifs))
            
        st.divider()
        chart_data = [{"Joueur": p["name"], "Matchs Joués": p["stats_played"], "Taux de Victoire (%)": (p["stats_won"] / p["stats_played"] * 100) if p["stats_played"] > 0 else 0} for p in db["players"].values()]
        chart_data.sort(key=lambda x: x["Joueur"].lower())
        
        df_charts = pd.DataFrame(chart_data).set_index("Joueur")
        col_c1, col_c2 = st.columns(2)
        with col_c1: st.markdown("**Matchs joués**"); st.bar_chart(df_charts["Matchs Joués"], color="#4CAF50")
        with col_c2: st.markdown("**Taux victoire (%)**"); st.bar_chart(df_charts["Taux de Victoire (%)"], color="#2196F3")
    else:
        st.info("Ajoutez des joueurs.")

# --- TAB 6 : ACCÈS ADMIN ---
with tab6:
    st.header("🛠️ Panneau Administrateur")
    admin_match_pass = st.text_input("Mot de passe Admin", type="password", key="pwd_admin_match")
    
    if admin_match_pass == ADMIN_PWD:
        st.success("Accès administrateur déverrouillé.")
        
        st.subheader("👥 Gestion des Joueurs")
        tab_create, tab_edit = st.tabs(["➕ Créer un joueur", "✏️ Modifier / Supprimer"])
        
        with tab_create:
            with st.form("form_create_player"):
                new_p_name = st.text_input("Nom du joueur")
                new_p_pwd = st.text_input("Mot de passe", type="password")
                if st.form_submit_button("Créer le joueur"):
                    if new_p_name and new_p_pwd:
                        db["players"][str(uuid.uuid4())] = {"name": new_p_name, "password": new_p_pwd, "elo": 1000.0, "prono_points": 0, "stats_played": 0, "stats_won": 0}
                        save_db(db)
                        st.success(f"Joueur {new_p_name} créé !")
                        st.rerun()
                    else:
                        st.error("Remplissez tous les champs.")
                        
        with tab_edit:
            if db["players"]:
                sorted_player_keys = sorted(list(db["players"].keys()), key=lambda k: db["players"][k]["name"].lower())
                edit_p_id = st.selectbox("Sélectionner un joueur", sorted_player_keys, format_func=lambda x: db["players"][x]["name"])
                edit_p_name = st.text_input("Nouveau nom", value=db["players"][edit_p_id]["name"])
                edit_p_pwd = st.text_input("Nouveau mot de passe", value=db["players"][edit_p_id]["password"])
                
                c_edit, c_del = st.columns(2)
                with c_edit:
                    if st.button("💾 Enregistrer modifications"):
                        db["players"][edit_p_id]["name"] = edit_p_name
                        db["players"][edit_p_id]["password"] = edit_p_pwd
                        save_db(db)
                        st.success("Joueur modifié !")
                        st.rerun()
                with c_del:
                    if st.button("🗑️ Supprimer ce joueur"):
                        to_del = []
                        for mid, m in db["matches"].items():
                            if m.get("type", "singles") == "singles" and (m["p1"] == edit_p_id or m["p2"] == edit_p_id): to_del.append(mid)
                            elif m.get("type", "singles") == "doubles" and (edit_p_id in m["t1"] or edit_p_id in m["t2"]): to_del.append(mid)
                        for mid in to_del: del db["matches"][mid]
                        del db["players"][edit_p_id]
                        recalculate_all_stats(db)
                        save_db(db)
                        st.success("Joueur et ses matchs supprimés !")
                        st.rerun()
        
        st.divider()
        st.subheader("🎾 Gestion des Matchs")
        
        def format_match_label(m_id):
            m = db["matches"][m_id]
            dt = datetime.fromisoformat(m["datetime"]).strftime('%d/%m/%Y %H:%M')
            if m.get("type", "singles") == "singles":
                return f"[{dt}] - {db['players'][m['p1']]['name']} vs {db['players'][m['p2']]['name']}"
            else:
                t1_names = " & ".join(sorted([db['players'][p]['name'] for p in m['t1']], key=str.lower))
                t2_names = " & ".join(sorted([db['players'][p]['name'] for p in m['t2']], key=str.lower))
                return f"[{dt}] - 2v2 : {t1_names} vs {t2_names}"
            
        pending_ids = [m_id for m_id, m in db["matches"].items() if m["status"] == "pending"]
        if pending_ids:
            sel_p_id = st.selectbox("⏳ Matchs en attente", pending_ids, format_func=format_match_label)
            mp = db["matches"][sel_p_id]
            dt_obj_p = datetime.fromisoformat(mp["datetime"])
            col_dp1, col_dp2 = st.columns(2)
            with col_dp1: new_dp = st.date_input("Nouvelle date", dt_obj_p.date(), key=f"dp_{sel_p_id}")
            with col_dp2: new_tp = st.time_input("Nouvelle heure", dt_obj_p.time(), key=f"tp_{sel_p_id}")
            
            c_btn1, c_btn2 = st.columns(2)
            if c_btn1.button("Modifier la date", key=f"btn_p_{sel_p_id}"):
                mp["datetime"] = datetime.combine(new_dp, new_tp).isoformat(); save_db(db); st.rerun()
            if c_btn2.button("🗑️ Supprimer", key=f"del_p_{sel_p_id}"):
                del db["matches"][sel_p_id]; save_db(db); st.rerun()
                
        completed_ids = [m_id for m_id, m in db["matches"].items() if m["status"] == "completed"]
        completed_ids.sort(key=lambda x: db["matches"][x]["datetime"], reverse=True)
        if completed_ids:
            sel_c_id = st.selectbox("🏁 Matchs terminés", completed_ids, format_func=format_match_label)
            mc = db["matches"][sel_c_id]
            
            if mc.get("type", "singles") == "singles":
                opt_res = {mc["p1"]: f"Victoire {db['players'][mc['p1']]['name']}", "draw": "Match Nul", mc["p2"]: f"Victoire {db['players'][mc['p2']]['name']}"}
            else:
                opt_res = {"t1": "Victoire Équipe 1", "draw": "Match Nul", "t2": "Victoire Équipe 2"}
                
            new_winner = st.radio("Modifier résultat", list(opt_res.keys()), format_func=lambda x: opt_res[x], index=list(opt_res.keys()).index(mc["winner"]))
            c_btn1, c_btn2 = st.columns(2)
            if c_btn1.button("Sauvegarder et recalculer", key=f"btn_c_{sel_c_id}"):
                mc["winner"] = new_winner
                db["history"].append({"date": datetime.now().isoformat(), "desc": f"⚠️ Admin a modifié un ancien match."})
                recalculate_all_stats(db); save_db(db); st.rerun()
            if c_btn2.button("🗑️ Supprimer et recalculer", key=f"del_c_{sel_c_id}"):
                del db["matches"][sel_c_id]
                db["history"].append({"date": datetime.now().isoformat(), "desc": f"⚠️ Admin a supprimé un ancien match."})
                recalculate_all_stats(db); save_db(db); st.rerun()
                
            st.divider()
            st.markdown("#### 🎯 Ajouter un pronostic rétroactif")
            
            # Identifier les joueurs ayant déjà parié ou joué ce match
            already_bet = [b["bettor"] for b in mc.get("bets", [])]
            if mc.get("type", "singles") == "singles":
                players_in_match = [mc["p1"], mc["p2"]]
                opt_1_val, opt_2_val = mc["p1"], mc["p2"]
                opt_1_label = f"Victoire {db['players'][mc['p1']]['name']}"
                opt_2_label = f"Victoire {db['players'][mc['p2']]['name']}"
            else:
                players_in_match = mc["t1"] + mc["t2"]
                opt_1_val, opt_2_val = "t1", "t2"
                t1_names = " & ".join(sorted([db['players'][p]['name'] for p in mc['t1']], key=str.lower))
                t2_names = " & ".join(sorted([db['players'][p]['name'] for p in mc['t2']], key=str.lower))
                opt_1_label = f"Victoire {t1_names}"
                opt_2_label = f"Victoire {t2_names}"
                
            eligible_bettors = [pid for pid in db["players"] if pid not in already_bet and pid not in players_in_match]
            eligible_bettors.sort(key=lambda x: db["players"][x]["name"].lower())
            
            if eligible_bettors:
                retro_bettor = st.selectbox("Sélectionner un joueur retardataire", eligible_bettors, format_func=lambda x: db["players"][x]["name"])
                
                # Récupérer les cotes au moment exact où le match a été joué
                odds_1, odds_2, odds_d = get_match_odds_at_time(db, sel_c_id)
                st.info(f"Cotes d'avant-match reconstituées : **{opt_1_label} ({odds_1})** | **Nul ({odds_d})** | **{opt_2_label} ({odds_2})**")
                
                retro_options = {
                    opt_1_val: f"{opt_1_label} ({odds_1})",
                    "draw": f"Match Nul ({odds_d})",
                    opt_2_val: f"{opt_2_label} ({odds_2})"
                }
                
                retro_pred = st.radio("Pronostic effectué par le joueur", list(retro_options.keys()), format_func=lambda x: retro_options[x])
                
                if st.button("Ajouter ce pronostic et recalculer les points"):
                    retro_odds = odds_1 if retro_pred == opt_1_val else (odds_2 if retro_pred == opt_2_val else odds_d)
                    if "bets" not in mc:
                        mc["bets"] = []
                    mc["bets"].append({
                        "bettor": retro_bettor,
                        "predicted": retro_pred,
                        "odds": retro_odds
                    })
                    recalculate_all_stats(db)
                    save_db(db)
                    st.success("Pronostic ajouté avec succès ! Les points de tous les joueurs ont été mis à jour.")
                    st.rerun()
            else:
                st.info("Tous les joueurs éligibles ont déjà pronostiqué ce match.")
    elif admin_match_pass:
        st.error("Mot de passe incorrect.")
