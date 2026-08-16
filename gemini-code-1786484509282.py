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
DATA_FILE = "joueurs_v3.json"  # Fichier conservé, AUCUNE DONNÉE altérée.
ADMIN_PWD = "Admin2026"

# --- GESTION DE LA BASE DE DONNÉES (CLOUD) ---

# On récupère les clés depuis les secrets Streamlit
JSONBIN_ID = st.secrets["6a823c7cda38895dfeecbde8"]
JSONBIN_KEY = st.secrets["$2a$10$zXh/GVbjDl2EIJ1nFyl/Eeyf7PZ/K9nOHILwYvyoDdglml2GTYHye "]
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/6a823c7cda38895dfeecbde8"
HEADERS = {
    "X-Master-Key": JSONBIN_KEY,
    "Content-Type": "application/json"
}

def init_db():
    # Avec JSONBin, la base est déjà initialisée en ligne, on a juste à la lire.
    return load_db()

def load_db():
    try:
        response = requests.get(JSONBIN_URL, headers=HEADERS)
        # JSONBin renvoie les données sous la clé "record"
        return response.json()["record"]
    except Exception as e:
        st.error(f"Erreur lors du chargement de la base de données : {e}")
        # Sécurité au cas où l'API est injoignable, pour ne pas faire planter l'app
        return {"players": {}, "matches": {}, "history": []} 

def save_db(db):
    try:
        # On remplace le fichier en ligne par notre dictionnaire mis à jour
        requests.put(JSONBIN_URL, json=db, headers=HEADERS)
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")

# --- FONCTIONS MATHÉMATIQUES, ELO & RECALCUL ---
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

def recalculate_all_stats(db):
    for pid in db["players"]:
        db["players"][pid]["elo"] = 1000.0
        db["players"][pid]["prono_points"] = 0
        db["players"][pid]["stats_played"] = 0
        db["players"][pid]["stats_won"] = 0

    completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
    completed_matches.sort(key=lambda x: x["datetime"])

    for m in completed_matches:
        p1, p2, winner = m["p1"], m["p2"], m["winner"]
        elo_p1, elo_p2 = db["players"][p1]["elo"], db["players"][p2]["elo"]
        p_1_raw = get_prob(elo_p1, elo_p2)
        p_2_raw = 1 - p_1_raw
        
        K = 32
        if winner == p1:
            score_p1, score_p2 = 1, 0
            db["players"][p1]["stats_won"] += 1
        elif winner == p2:
            score_p1, score_p2 = 0, 1
            db["players"][p2]["stats_won"] += 1
        else: 
            score_p1, score_p2 = 0.5, 0.5
            
        db["players"][p1]["elo"] += K * (score_p1 - p_1_raw)
        db["players"][p2]["elo"] += K * (score_p2 - p_2_raw)
        db["players"][p1]["stats_played"] += 1
        db["players"][p2]["stats_played"] += 1
        
        for bet in m.get("bets", []):
            if bet["predicted"] == winner:
                db["players"][bet["bettor"]]["prono_points"] += int(bet["odds"] * 10)

# --- GÉNÉRATION D'HISTORIQUE DYNAMIQUE (POUR LES GRAPHIQUES) ---
def get_elo_history_df(db):
    records = []
    base_date = datetime(2026, 8, 10)
    
    states = {pid: {"elo": 1000.0, "played": 0, "won": 0} for pid in db["players"]}
    for pid, p in db["players"].items():
        records.append({"Joueur": p["name"], "Date": base_date, "ELO": 1000.0, "Matchs": 0, "Victoires": 0})
        
    completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
    completed_matches.sort(key=lambda x: x["datetime"])
    
    for m in completed_matches:
        p1, p2, winner = m["p1"], m["p2"], m["winner"]
        dt = datetime.fromisoformat(m["datetime"])
        
        elo_p1, elo_p2 = states[p1]["elo"], states[p2]["elo"]
        p_1_raw = get_prob(elo_p1, elo_p2)
        p_2_raw = 1 - p_1_raw
        
        K = 32
        if winner == p1:
            score_p1, score_p2 = 1, 0
            states[p1]["won"] += 1
        elif winner == p2:
            score_p1, score_p2 = 0, 1
            states[p2]["won"] += 1
        else: 
            score_p1, score_p2 = 0.5, 0.5
            
        states[p1]["elo"] += K * (score_p1 - p_1_raw)
        states[p2]["elo"] += K * (score_p2 - p_2_raw)
        states[p1]["played"] += 1
        states[p2]["played"] += 1
        
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
        
        # --- CALCULS À LA VOLÉE POUR LA SIDEBAR ---
        # 1. Classements globaux
        all_players_elo = sorted(db["players"].keys(), key=lambda x: db["players"][x]["elo"], reverse=True)
        all_players_prono = sorted(db["players"].keys(), key=lambda x: db["players"][x].get("prono_points", 0), reverse=True)
        
        rank_elo = all_players_elo.index(uid) + 1
        rank_prono = all_players_prono.index(uid) + 1
        total_players = len(db["players"])
        
        # 2. Statistiques individuelles
        pts_prono = user_data.get("prono_points", 0)
        user_elo = int(user_data["elo"])
        played = user_data["stats_played"]
        won = user_data["stats_won"]
        
        completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
        user_matches = [m for m in completed_matches if m["p1"] == uid or m["p2"] == uid]
        user_matches.sort(key=lambda x: x["datetime"], reverse=True)
        
        draws = len([m for m in user_matches if m["winner"] == "draw"])
        losses = played - won - draws
        
        # --- AFFICHAGE SIDEBAR ---
        st.markdown("#### 🎯 Pronostics")
        st.write(f"**Points :** {pts_prono}")
        st.write(f"**Classement :** {rank_prono} / {total_players}")
        
        st.markdown("#### 🏆 Score ELO")
        st.write(f"**Points :** {user_elo}")
        st.write(f"**Classement :** {rank_elo} / {total_players}")
        
        st.markdown("#### 🎾 Mes Matchs")
        st.write(f"**Joués :** {played}")
        col_v, col_n, col_d = st.columns(3)
        with col_v:
            st.markdown(f"<div style='text-align:center;'>✅<br><b>{won}</b></div>", unsafe_allow_html=True)
        with col_n:
            st.markdown(f"<div style='text-align:center;'>🤝<br><b>{draws}</b></div>", unsafe_allow_html=True)
        with col_d:
            st.markdown(f"<div style='text-align:center;'>❌<br><b>{losses}</b></div>", unsafe_allow_html=True)
            
        st.markdown("<br>#### 📅 Dernier résultat", unsafe_allow_html=True)
        if user_matches:
            last_m = user_matches[0]
            dt_last = datetime.fromisoformat(last_m["datetime"]).strftime('%d/%m/%Y')
            opp_id = last_m["p2"] if last_m["p1"] == uid else last_m["p1"]
            opp_name = db["players"][opp_id]["name"]
            
            if last_m["winner"] == "draw":
                res_txt = "Match Nul 🤝"
                res_col = "#9CA3AF" # Gris
            elif last_m["winner"] == uid:
                res_txt = "Victoire ✅"
                res_col = "#10B981" # Vert
            else:
                res_txt = "Défaite ❌"
                res_col = "#EF4444" # Rouge
                
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

    # Bouton de déconnexion pour tous
    if st.button("Se déconnecter", use_container_width=True):
        st.session_state.user_id = None
        st.session_state.is_admin = False
        
        # On essaie de supprimer le cookie joueur s'il existe
        try:
            cookie_controller.remove("user_id")
        except KeyError:
            pass
            
        # On essaie de supprimer le cookie admin s'il existe
        try:
            cookie_controller.remove("is_admin")
        except KeyError:
            pass
            
        st.rerun()

# --- INTERFACE JOUEUR PRINCIPALE ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🏆 Classement ELO", "📅 Matchs & Pronos", "🎯 Classement Pronos", "📜 Historique", "📊 Dashboard", "🛠️ Admin Matchs"])

# --- TAB 1 : CLASSEMENT ELO VISUEL ---
with tab1:
    st.header("🏆 Classement ELO des Joueurs")
    
    players_items = list(db["players"].items())
    players_items.sort(key=lambda x: x[1]["elo"], reverse=True)
    
    if not players_items:
        st.info("Aucun joueur n'est inscrit pour le moment.")
    else:
        completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
        
        df_data = []
        for i, (pid, p) in enumerate(players_items, 1):
            draws = len([m for m in completed_matches if m["winner"] == "draw" and (m["p1"] == pid or m["p2"] == pid)])
            losses = p["stats_played"] - p["stats_won"] - draws
            win_rate = (p["stats_won"] / p["stats_played"] * 100) if p["stats_played"] > 0 else 0
            
            df_data.append({
                "Rang": i, 
                "Joueur": p["name"], 
                "ELO": int(p["elo"]),
                "Matchs": p["stats_played"], 
                "Victoires": p["stats_won"], 
                "Nuls": draws,
                "Défaites": losses,
                "Taux de Victoire": win_rate
            })
            
        df = pd.DataFrame(df_data)
        max_elo_val = int(df["ELO"].max()) if not df.empty else 1000
        
        st.dataframe(
            df,
            column_config={
                "Rang": st.column_config.NumberColumn("Rang", format="%d 🏅"),
                "ELO": st.column_config.ProgressColumn("Points ELO", min_value=800, max_value=max(max_elo_val + 50, 1200), format="%d pts"),
                "Matchs": st.column_config.NumberColumn("Matchs"),
                "Victoires": st.column_config.NumberColumn("V", help="Victoires"),
                "Nuls": st.column_config.NumberColumn("N", help="Matchs Nuls"),
                "Défaites": st.column_config.NumberColumn("D", help="Défaites"),
                "Taux de Victoire": st.column_config.ProgressColumn("Taux de Victoire", min_value=0, max_value=100, format="%d %%")
            },
            hide_index=True, use_container_width=True
        )
        
        st.divider()
        st.subheader("📈 Historique des leaders et évolution ELO")
        
        col_filtre, _ = st.columns([1, 2])
        with col_filtre:
            time_filter = st.radio("Filtre temporel :", ["Depuis le début", "30 derniers jours", "7 derniers jours"], horizontal=True)
            
        df_hist = get_elo_history_df(db)
        
        if time_filter == "30 derniers jours":
            cutoff = datetime.now() - timedelta(days=30)
            df_hist = df_hist[df_hist["Date"] >= cutoff]
        elif time_filter == "7 derniers jours":
            cutoff = datetime.now() - timedelta(days=7)
            df_hist = df_hist[df_hist["Date"] >= cutoff]

        if not df_hist.empty:
            df_hist["Info_Joueur"] = df_hist.apply(
                lambda x: f"• <b>{x['Joueur']}</b> (M: {x['Matchs']} | V: {x['Victoires']} | Ratio: {x['Ratio']:.0f}%)", 
                axis=1
            )
            df_hist["Infos_Combinees"] = df_hist.groupby(["Date", "ELO"])["Info_Joueur"].transform(lambda x: "<br>".join(x))

            fig = px.line(
                df_hist, x="Date", y="ELO", color="Joueur", markers=True,
                hover_data={"Date": "|%d/%m/%Y %H:%M", "Infos_Combinees": True}
            )
            
            fig.update_traces(
                mode="lines+markers",
                line=dict(width=3), 
                marker=dict(size=6),
                hovertemplate="Date : <b>%{x}</b><br>Score ELO : <b>%{y:.0f} pts</b><br><br>%{customdata[0]}<extra></extra>"
            )
            
            fig.update_layout(
                hovermode="closest", 
                legend_title="Joueurs",
                xaxis_title="",
                yaxis_title="Score ELO",
                margin=dict(l=0, r=0, t=30, b=0),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                hoverlabel=dict(bgcolor="rgba(30, 30, 30, 0.95)", font_size=13)
            )
            
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)')
            fig.update_xaxes(showgrid=False)

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune donnée disponible pour cette période.")

# --- TAB 2 : MATCHS ET PRONOS ---
with tab2:
    st.header("📅 Matchs & Pronostics")
    
    with st.expander("➕ Créer un nouveau match", expanded=False):
        c1, c2 = st.columns(2)
        all_players_sorted = sorted(list(db["players"].keys()), key=lambda x: db["players"][x]["name"].lower())
        
        with c1:
            p1 = st.selectbox("Joueur 1", all_players_sorted, format_func=lambda x: db["players"][x]["name"])
            d = st.date_input("Date du match")
        with c2:
            p2_options = [p for p in all_players_sorted if p != p1]
            p2 = st.selectbox("Joueur 2", p2_options, format_func=lambda x: db["players"][x]["name"])
            t = st.time_input("Heure du match")
            
        if st.button("Programmer le match"):
            dt_str = datetime.combine(d, t).isoformat()
            m_id = str(uuid.uuid4())
            db["matches"][m_id] = {
                "p1": p1, "p2": p2, "datetime": dt_str,
                "status": "pending", "winner": None, "bets": []
            }
            save_db(db)
            st.success("Match programmé !")
            st.rerun()
            
    st.divider()
    st.subheader("🔥 Matchs à venir & Pronostics de la communauté")
    
    pending_matches = {k: v for k, v in db["matches"].items() if v["status"] == "pending"}
    pending_matches = dict(sorted(pending_matches.items(), key=lambda item: item[1]["datetime"]))
    
    if not pending_matches:
        st.info("Aucun match prévu pour le moment.")
        
    for m_id, m in pending_matches.items():
        name1 = db["players"][m["p1"]]["name"]
        name2 = db["players"][m["p2"]]["name"]
        dt = datetime.fromisoformat(m["datetime"])
        
        prob_p1, prob_p2, prob_draw = get_probs_with_draw(db["players"][m["p1"]]["elo"], db["players"][m["p2"]]["elo"])
        odds_p1, odds_p2, odds_draw = get_odds(prob_p1), get_odds(prob_p2), get_odds(prob_draw)
        
        st.markdown(f"### 🎾 {name1} 🆚 {name2}")
        st.caption(f"🕒 Prévu le {dt.strftime('%d/%m/%Y à %H:%M')}")
        st.write(f"Cotes indicatives : **{name1} ({odds_p1})** | **Nul ({odds_draw})** | **{name2} ({odds_p2})**")
        
        st.markdown("#### 👥 Pronostics enregistrés :")
        if m["bets"]:
            cols_bets = st.columns(len(m["bets"]))
            sorted_bets = sorted(m["bets"], key=lambda b: db["players"][b["bettor"]]["name"].lower())
            for idx, bet in enumerate(sorted_bets):
                bettor_name = db["players"][bet["bettor"]]["name"]
                pred_val = bet["predicted"]
                if pred_val == "draw": choice_text = "Match Nul 🤝"
                elif pred_val == m["p1"]: choice_text = f"Victoire {name1}"
                else: choice_text = f"Victoire {name2}"
                
                with cols_bets[idx % len(cols_bets)]:
                    st.info(f"**{bettor_name}**\n\n🎯 *{choice_text}*\n\n📈 Cote : {bet['odds']}")
        else:
            st.info("Aucun pronostic validé pour l'instant sur ce match. Soyez le premier !")
        
        is_playing = st.session_state.user_id in [m["p1"], m["p2"]]
        is_started = datetime.now() > dt
        my_bet = next((b for b in m["bets"] if b["bettor"] == st.session_state.user_id), None)
        
        if my_bet:
            pred_name = "Match Nul" if my_bet['predicted'] == "draw" else db["players"][my_bet['predicted']]['name']
            st.success(f"✅ Ton pronostic enregistré : **{pred_name}** (Cote: {my_bet['odds']})")
        elif is_playing:
            st.warning("Tu ne peux pas pronostiquer sur ton propre match.")
        elif is_started:
            st.error("Match commencé, les pronostics sont fermés.")
        else:
            with st.form(key=f"bet_form_{m_id}"):
                options_pari = {m["p1"]: f"Victoire {name1}", "draw": "Match Nul", m["p2"]: f"Victoire {name2}"}
                pred = st.radio("Ton pronostic ?", list(options_pari.keys()), format_func=lambda x: options_pari[x])
                submit_prono = st.form_submit_button("Valider mon pronostic")
                
                if submit_prono:
                    if pred == m["p1"]: odds_locked = odds_p1
                    elif pred == m["p2"]: odds_locked = odds_p2
                    else: odds_locked = odds_draw
                    
                    m["bets"] = [b for b in m["bets"] if b["bettor"] != st.session_state.user_id]
                    m["bets"].append({"bettor": st.session_state.user_id, "predicted": pred, "odds": odds_locked})
                    save_db(db)
                    st.success("Pronostic enregistré avec succès !")
                    st.rerun()
                    
        with st.expander("🏁 Terminer ce match (Saisir le résultat)"):
            options_result = {m["p1"]: f"Victoire {name1}", "draw": "Match Nul", m["p2"]: f"Victoire {name2}"}
            winner = st.radio("Résultat final", list(options_result.keys()), format_func=lambda x: options_result[x], key=f"win_{m_id}")
            
            if st.button("Valider le résultat et distribuer les points", key=f"btn_{m_id}"):
                m["status"], m["winner"] = "completed", winner
                if winner == "draw":
                    desc = f"🤝 Match Nul entre {name1} et {name2} a été enregistré."
                else:
                    w_name, l_name = (name1, name2) if winner == m["p1"] else (name2, name1)
                    desc = f"🏆 {w_name} a battu {l_name}."
                    
                db["history"].append({"date": datetime.now().isoformat(), "desc": desc})
                recalculate_all_stats(db)
                save_db(db)
                st.success("Match terminé et points distribués !")
                st.rerun()
        st.divider()

# --- TAB 3 : CLASSEMENT PRONOS VISUEL (Podium) ---
with tab3:
    st.header("🎯 Classement des Pronostiqueurs")
    
    seven_days_ago = datetime.now() - timedelta(days=7)
    recent_prono_gains = {pid: 0 for pid in db["players"]}
    
    completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
    for m in completed_matches:
        dt = datetime.fromisoformat(m["datetime"])
        if dt >= seven_days_ago:
            winner = m["winner"]
            for bet in m.get("bets", []):
                if bet["predicted"] == winner:
                    recent_prono_gains[bet["bettor"]] += int(bet["odds"] * 10)

    players_prono = list(db["players"].items())
    players_prono.sort(key=lambda x: x[1].get("prono_points", 0), reverse=True)
    
    if not players_prono:
        st.info("Aucun joueur inscrit.")
    else:
        if len(players_prono) >= 3:
            p1, p2, p3 = players_prono[0], players_prono[1], players_prono[2]
            col_pod2, col_pod1, col_pod3 = st.columns([1, 1.1, 1])
            
            def draw_podium_card(player_tuple, border_color, bg_color, emoji):
                pid, p = player_tuple
                pts = p.get("prono_points", 0)
                rec = recent_prono_gains[pid]
                elo = int(p["elo"])
                rec_color = "#10B981" if rec > 0 else "gray"
                rec_str = f"+{rec}" if rec > 0 else "0"
                
                st.markdown(f"""
                <div style="border: 2px solid {border_color}; background-color: {bg_color}; padding: 15px; border-radius: 12px; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <div style="font-size: 35px; margin-bottom: 5px;">{emoji}</div>
                    <h3 style="margin: 0 0 5px 0;">{p['name']}</h3>
                    <h2 style="margin: 0; color: {border_color};">{pts} <span style="font-size: 16px; color: white;">pts</span></h2>
                    <p style="margin: 8px 0 0 0; font-size: 13px;"><span style="color: {rec_color}; font-weight: bold;">{rec_str} pts</span> (7j) | ELO: {elo}</p>
                </div>
                """, unsafe_allow_html=True)
                
            with col_pod2:
                st.write("") 
                draw_podium_card(p2, "#9CA3AF", "rgba(156, 163, 175, 0.1)", "🥈") 
            with col_pod1:
                draw_podium_card(p1, "#F59E0B", "rgba(245, 158, 11, 0.15)", "🥇") 
            with col_pod3:
                st.write("") 
                st.write("") 
                draw_podium_card(p3, "#B45309", "rgba(180, 83, 9, 0.1)", "🥉") 

            st.markdown("<br>", unsafe_allow_html=True)
            for i, (pid, p) in enumerate(players_prono[3:], 4):
                pts = p.get("prono_points", 0)
                rec = recent_prono_gains[pid]
                elo = int(p["elo"])
                rec_str = f"+{rec}" if rec > 0 else "0"
                color = "#10B981" if rec > 0 else "#9CA3AF"
                
                st.markdown(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background-color: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 15px;">
                        <h4 style="margin: 0; color: #9CA3AF; width: 25px;">{i}</h4>
                        <div>
                            <h4 style="margin: 0;">{p['name']}</h4>
                            <span style="font-size: 13px; color: #9CA3AF;">{elo} ELO</span>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <h4 style="margin: 0;">{pts} pts</h4>
                        <span style="font-size: 13px; color: {color};">{rec_str} pts (7j)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            for i, (pid, p) in enumerate(players_prono, 1):
                pts = p.get("prono_points", 0)
                st.write(f"**{i}. {p['name']}** - {pts} pts")

# --- TAB 4 : HISTORIQUE ---
with tab4:
    st.header("📜 Historique des Matchs")
    completed = [m for m in db["matches"].values() if m["status"] == "completed"]
    completed.sort(key=lambda x: x["datetime"], reverse=True)
    
    if not completed:
        st.info("Aucun match terminé pour l'instant.")
    for m in completed:
        dt = datetime.fromisoformat(m["datetime"]).strftime('%d/%m/%Y')
        if m["winner"] == "draw":
            p1_name, p2_name = db["players"][m["p1"]]["name"], db["players"][m["p2"]]["name"]
            st.markdown(f"**{dt}** : 🤝 Match Nul entre **{p1_name}** et **{p2_name}** ({len(m['bets'])} pronos)")
        else:
            w_name = db["players"][m["winner"]]["name"]
            l_id = m["p2"] if m["winner"] == m["p1"] else m["p1"]
            l_name = db["players"][l_id]["name"]
            st.markdown(f"**{dt}** : 🏆 **{w_name}** a battu {l_name} ({len(m['bets'])} pronos)")

# --- TAB 5 : DASHBOARD STATS ---
with tab5:
    st.header("📊 Tableau de Bord Global")
    
    if db["players"]:
        cols = st.columns(2)
        max_prono = max([p.get("prono_points", 0) for p in db["players"].values()], default=0)
        rois = [p["name"] for p in db["players"].values() if p.get("prono_points", 0) == max_prono]
        rois_text = " & ".join(rois) if len(rois) <= 2 else ", ".join(rois)
        
        max_active = max([p["stats_played"] for p in db["players"].values()], default=0)
        actifs = [p["name"] for p in db["players"].values() if p["stats_played"] == max_active]
        actifs_text = " & ".join(actifs) if len(actifs) <= 2 else ", ".join(actifs)
        
        with cols[0]:
            st.metric(f"🎯 Roi{'s' if len(rois)>1 else ''} des Pronos", f"{max_prono} pts", rois_text)
        with cols[1]:
            st.metric(f"🎾 Joueur{'s' if len(actifs)>1 else ''} le{'s' if len(actifs)>1 else ''} plus actif{'s' if len(actifs)>1 else ''}", f"{max_active} matchs", actifs_text)
            
        st.divider()
        st.subheader("🎯 Performances des joueurs (Matchs & Taux de victoire)")
        
        chart_data = []
        for p in db["players"].values():
            win_rate = (p["stats_won"] / p["stats_played"] * 100) if p["stats_played"] > 0 else 0
            chart_data.append({
                "Joueur": p["name"], "Matchs Joués": p["stats_played"], "Taux de Victoire (%)": win_rate
            })
            
        df_charts = pd.DataFrame(chart_data).set_index("Joueur")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("**Nombre de matchs joués**")
            st.bar_chart(df_charts["Matchs Joués"], color="#4CAF50")
            
        with col_c2:
            st.markdown("**Taux de victoire (%)**")
            st.bar_chart(df_charts["Taux de Victoire (%)"], color="#2196F3")
    else:
        st.info("Ajoutez des joueurs et jouez des matchs pour voir les statistiques apparaître !")

# --- TAB 6 : ACCÈS ADMIN MATCHS ---
with tab6:
    st.header("🛠️ Gestion Administrateur des Matchs")
    st.info("Cette section est réservée pour corriger des erreurs (dates, résultats, suppressions).")
    
    admin_match_pass = st.text_input("Mot de passe Admin", type="password", key="pwd_admin_match")
    
    if admin_match_pass == ADMIN_PWD:
        st.success("Accès administrateur déverrouillé.")
        
        def format_match_label(m_id):
            m = db["matches"][m_id]
            p1_name, p2_name = db["players"][m["p1"]]["name"], db["players"][m["p2"]]["name"]
            dt = datetime.fromisoformat(m["datetime"]).strftime('%d/%m/%Y %H:%M')
            return f"[{dt}] - {p1_name} vs {p2_name}"
            
        st.subheader("⏳ Matchs en attente (Non joués)")
        pending_ids = [m_id for m_id, m in db["matches"].items() if m["status"] == "pending"]
        pending_ids.sort(key=lambda x: db["matches"][x]["datetime"])
        
        if pending_ids:
            sel_p_id = st.selectbox("Sélectionner un match en attente", pending_ids, format_func=format_match_label)
            if sel_p_id:
                mp = db["matches"][sel_p_id]
                dt_obj_p = datetime.fromisoformat(mp["datetime"])
                
                col_dp1, col_dp2 = st.columns(2)
                with col_dp1:
                    new_dp = st.date_input("Nouvelle date", dt_obj_p.date(), key=f"dp_{sel_p_id}")
                with col_dp2:
                    new_tp = st.time_input("Nouvelle heure", dt_obj_p.time(), key=f"tp_{sel_p_id}")
                
                col_btn_p1, col_btn_p2 = st.columns(2)
                with col_btn_p1:
                    if st.button("Modifier la date", key=f"btn_update_p_{sel_p_id}"):
                        mp["datetime"] = datetime.combine(new_dp, new_tp).isoformat()
                        save_db(db)
                        st.success("Date du match mise à jour !")
                        st.rerun()
                with col_btn_p2:
                    if st.button("🗑️ Supprimer ce match", key=f"btn_del_p_{sel_p_id}"):
                        del db["matches"][sel_p_id]
                        save_db(db)
                        st.success("Match supprimé !")
                        st.rerun()
        else:
            st.write("Aucun match en attente.")
            
        st.divider()
        st.subheader("🏁 Matchs terminés (Joués)")
        completed_ids = [m_id for m_id, m in db["matches"].items() if m["status"] == "completed"]
        completed_ids.sort(key=lambda x: db["matches"][x]["datetime"], reverse=True)
        
        if completed_ids:
            sel_c_id = st.selectbox("Sélectionner un match terminé", completed_ids, format_func=format_match_label)
            if sel_c_id:
                mc = db["matches"][sel_c_id]
                dt_obj_c = datetime.fromisoformat(mc["datetime"])
                
                col_dc1, col_dc2 = st.columns(2)
                with col_dc1:
                    new_dc = st.date_input("Nouvelle date", dt_obj_c.date(), key=f"dc_{sel_c_id}")
                with col_dc2:
                    new_tc = st.time_input("Nouvelle heure", dt_obj_c.time(), key=f"tc_{sel_c_id}")
                
                options_result = {
                    mc["p1"]: f"Victoire {db['players'][mc['p1']]['name']}", 
                    "draw": "Match Nul", 
                    mc["p2"]: f"Victoire {db['players'][mc['p2']]['name']}"
                }
                
                idx_winner = list(options_result.keys()).index(mc["winner"])
                new_winner = st.radio(
                    "Modifier le résultat", list(options_result.keys()), 
                    format_func=lambda x: options_result[x], index=idx_winner, key=f"res_{sel_c_id}"
                )
                
                st.warning("⚠️ Toute modification entraînera un recalcul automatique de l'historique ELO et des points de pronostics.")
                
                col_btn_c1, col_btn_c2 = st.columns(2)
                with col_btn_c1:
                    if st.button("Sauvegarder les modifications et recalculer", key=f"btn_update_c_{sel_c_id}"):
                        mc["datetime"] = datetime.combine(new_dc, new_tc).isoformat()
                        mc["winner"] = new_winner
                        db["history"].append({"date": datetime.now().isoformat(), "desc": f"⚠️ Admin a modifié un ancien match."})
                        recalculate_all_stats(db)
                        save_db(db)
                        st.success("Match mis à jour et classements recalculés !")
                        st.rerun()
                with col_btn_c2:
                    if st.button("🗑️ Supprimer ce match et recalculer", key=f"btn_del_c_{sel_c_id}"):
                        del db["matches"][sel_c_id]
                        db["history"].append({"date": datetime.now().isoformat(), "desc": f"⚠️ Admin a supprimé un ancien match."})
                        recalculate_all_stats(db)
                        save_db(db)
                        st.success("Match supprimé et classements recalculés !")
                        st.rerun()
        else:
            st.write("Aucun match terminé.")
    elif admin_match_pass:
        st.error("Mot de passe incorrect.")
