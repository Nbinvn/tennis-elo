import json
import os
import uuid
from datetime import datetime
import streamlit as st
import pandas as pd

# --- CONFIGURATION ---
DATA_FILE = "joueurs_v3.json"  # Conserve le fichier existant pour ne pas perdre les données
ADMIN_PWD = "admin"  # Mot de passe administrateur par défaut

# --- GESTION DE LA BASE DE DONNÉES (JSON) ---
def init_db():
    if not os.path.exists(DATA_FILE):
        db = {
            "players": {},
            "matches": {},
            "history": []
        }
        save_db(db)
    return load_db()

def load_db():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DATA_FILE, "w") as f:
        json.dump(db, f, indent=4)

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

# --- INITIALISATION SESSION ---
db = init_db()
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- SYSTÈME D'AUTHENTIFICATION ---
if st.session_state.user_id is None and not st.session_state.is_admin:
    st.title("🔒 Connexion - Tennis Pronos & ELO")
    
    tab_login, tab_admin = st.tabs(["Joueur", "Administrateur"])
    
    with tab_login:
        if not db["players"]:
            st.info("Aucun joueur n'est inscrit. Connectez-vous en tant qu'administrateur pour en créer.")
        else:
            player_names = {p_id: p_data["name"] for p_id, p_data in db["players"].items()}
            selected_name = st.selectbox("Qui êtes-vous ?", list(player_names.values()))
            pwd = st.text_input("Mot de passe", type="password", key="pwd_player")
            
            if st.button("Se connecter"):
                p_id = next(uid for uid, name in player_names.items() if name == selected_name)
                if pwd == db["players"][p_id]["password"]:
                    st.session_state.user_id = p_id
                    st.rerun()
                else:
                    st.error("Mot de passe incorrect")
                    
    with tab_admin:
        admin_pwd_input = st.text_input("Mot de passe administrateur", type="password", key="pwd_admin")
        if st.button("Accès Admin"):
            if admin_pwd_input == ADMIN_PWD:
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Mot de passe administrateur incorrect")
                
    st.stop() 

# --- BARRE LATÉRALE (DÉCONNEXION) ---
with st.sidebar:
    if st.session_state.is_admin:
        st.write("👤 **Connecté en tant que : ADMIN**")
    else:
        nom_joueur = db["players"][st.session_state.user_id]["name"]
        st.write(f"👤 **Connecté : {nom_joueur}**")
        pts_prono = db["players"][st.session_state.user_id].get("prono_points", 0)
        st.metric("Mes Points Prono", f"{pts_prono} pts")
        
    if st.button("Se déconnecter"):
        st.session_state.user_id = None
        st.session_state.is_admin = False
        st.rerun()

# --- INTERFACE ADMINISTRATEUR ---
if st.session_state.is_admin:
    st.title("⚙️ Panneau d'Administration")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Ajouter un joueur")
        new_name = st.text_input("Nom du joueur")
        new_pwd = st.text_input("Mot de passe du joueur")
        if st.button("Créer le joueur"):
            if new_name and new_pwd:
                uid = str(uuid.uuid4())
                db["players"][uid] = {
                    "name": new_name,
                    "password": new_pwd,
                    "elo": 1000.0,
                    "prono_points": 0,
                    "stats_played": 0,
                    "stats_won": 0
                }
                save_db(db)
                st.success(f"Joueur {new_name} créé !")
                st.rerun()
                
    with col2:
        st.subheader("Modifier / Supprimer")
        if db["players"]:
            p_to_edit = st.selectbox("Sélectionner un joueur", list(db["players"].keys()), format_func=lambda x: db["players"][x]["name"])
            new_p_name = st.text_input("Nouveau nom", value=db["players"][p_to_edit]["name"])
            new_p_pwd = st.text_input("Nouveau mot de passe", value=db["players"][p_to_edit]["password"])
            if st.button("Mettre à jour"):
                db["players"][p_to_edit]["name"] = new_p_name
                db["players"][p_to_edit]["password"] = new_p_pwd
                save_db(db)
                st.success("Mise à jour réussie !")
                st.rerun()
    st.stop()

# --- INTERFACE JOUEUR PRINCIPALE ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏆 Classement ELO", "📅 Matchs & Pronos", "🎯 Classement Pronos", "📜 Historique", "📊 Dashboard"])

# --- TAB 1 : CLASSEMENT ELO VISUEL ---
with tab1:
    st.header("🏆 Classement ELO des Joueurs")
    players_list = list(db["players"].values())
    players_list.sort(key=lambda x: x["elo"], reverse=True)
    
    if not players_list:
        st.info("Aucun joueur n'est inscrit pour le moment.")
    else:
        df_data = []
        for i, p in enumerate(players_list, 1):
            win_rate = (p["stats_won"] / p["stats_played"] * 100) if p["stats_played"] > 0 else 0
            df_data.append({
                "Rang": i,
                "Joueur": p["name"],
                "ELO": int(p["elo"]),
                "Matchs": p["stats_played"],
                "Victoires": p["stats_won"],
                "Taux de Victoire": win_rate
            })
            
        df = pd.DataFrame(df_data)
        max_elo_val = int(df["ELO"].max())
        
        st.dataframe(
            df,
            column_config={
                "Rang": st.column_config.NumberColumn("Rang", format="%d 🏅"),
                "ELO": st.column_config.ProgressColumn(
                    "Points ELO", 
                    min_value=800, 
                    max_value=max(max_elo_val + 50, 1200), 
                    format="%d pts"
                ),
                "Taux de Victoire": st.column_config.ProgressColumn(
                    "Taux de Victoire", 
                    min_value=0, 
                    max_value=100, 
                    format="%d %%"
                )
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.divider()
        st.subheader("📈 Écarts de niveau (Graphique ELO)")
        chart_data = df[["Joueur", "ELO"]].set_index("Joueur")
        st.bar_chart(chart_data)

# --- TAB 2 : MATCHS ET PRONOS ---
with tab2:
    st.header("📅 Matchs & Pronostics")
    
    with st.expander("➕ Créer un nouveau match", expanded=False):
        c1, c2 = st.columns(2)
        all_players = list(db["players"].keys())
        with c1:
            p1 = st.selectbox("Joueur 1", all_players, format_func=lambda x: db["players"][x]["name"])
            d = st.date_input("Date du match")
        with c2:
            p2 = st.selectbox("Joueur 2", [p for p in all_players if p != p1], format_func=lambda x: db["players"][x]["name"])
            t = st.time_input("Heure du match")
            
        if st.button("Programmer le match"):
            dt_str = datetime.combine(d, t).isoformat()
            m_id = str(uuid.uuid4())
            db["matches"][m_id] = {
                "p1": p1,
                "p2": p2,
                "datetime": dt_str,
                "status": "pending",
                "winner": None,
                "bets": []
            }
            save_db(db)
            st.success("Match programmé !")
            st.rerun()
            
    st.divider()
    st.subheader("🔥 Matchs à venir & Pronostics de la communauté")
    
    pending_matches = {k: v for k, v in db["matches"].items() if v["status"] == "pending"}
    if not pending_matches:
        st.info("Aucun match prévu pour le moment.")
        
    for m_id, m in pending_matches.items():
        name1 = db["players"][m["p1"]]["name"]
        name2 = db["players"][m["p2"]]["name"]
        dt = datetime.fromisoformat(m["datetime"])
        
        prob_p1, prob_p2, prob_draw = get_probs_with_draw(db["players"][m["p1"]]["elo"], db["players"][m["p2"]]["elo"])
        odds_p1 = get_odds(prob_p1)
        odds_p2 = get_odds(prob_p2)
        odds_draw = get_odds(prob_draw)
        
        st.markdown(f"### 🎾 {name1} 🆚 {name2}")
        st.caption(f"🕒 Prévu le {dt.strftime('%d/%m/%Y à %H:%M')}")
        st.write(f"Cotes indicatives : **{name1} ({odds_p1})** | **Nul ({odds_draw})** | **{name2} ({odds_p2})**")
        
        # --- BLOC VISUEL : Qui a parié sur quoi ? ---
        st.markdown("#### 👥 Pronostics enregistrés :")
        if m["bets"]:
            cols_bets = st.columns(len(m["bets"]))
            for idx, bet in enumerate(m["bets"]):
                bettor_name = db["players"][bet["bettor"]]["name"]
                pred_val = bet["predicted"]
                
                if pred_val == "draw":
                    choice_text = "Match Nul 🤝"
                    badge_color = "orange"
                elif pred_val == m["p1"]:
                    choice_text = f"Victoire {name1}"
                    badge_color = "green"
                else:
                    choice_text = f"Victoire {name2}"
                    badge_color = "blue"
                
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
                    
                    # On retire l'ancien prono si l'utilisateur en avait déjà mis un
                    m["bets"] = [b for b in m["bets"] if b["bettor"] != st.session_state.user_id]
                    
                    m["bets"].append({
                        "bettor": st.session_state.user_id,
                        "predicted": pred,
                        "odds": odds_locked
                    })
                    save_db(db)
                    st.success("Pronostic enregistré avec succès !")
                    st.rerun()
                    
        with st.expander("🏁 Terminer ce match (Saisir le résultat)"):
            options_result = {m["p1"]: f"Victoire {name1}", "draw": "Match Nul", m["p2"]: f"Victoire {name2}"}
            winner = st.radio("Résultat final", list(options_result.keys()), format_func=lambda x: options_result[x], key=f"win_{m_id}")
            
            if st.button("Valider le résultat et distribuer les points", key=f"btn_{m_id}"):
                elo_p1 = db["players"][m["p1"]]["elo"]
                elo_p2 = db["players"][m["p2"]]["elo"]
                p_1_raw = get_prob(elo_p1, elo_p2)
                p_2_raw = 1 - p_1_raw
                
                K = 32
                if winner == m["p1"]:
                    score_p1, score_p2 = 1, 0
                    db["players"][m["p1"]]["stats_won"] += 1
                elif winner == m["p2"]:
                    score_p1, score_p2 = 0, 1
                    db["players"][m["p2"]]["stats_won"] += 1
                else: 
                    score_p1, score_p2 = 0.5, 0.5
                    
                gain_elo_p1 = K * (score_p1 - p_1_raw)
                gain_elo_p2 = K * (score_p2 - p_2_raw)
                
                db["players"][m["p1"]]["elo"] += gain_elo_p1
                db["players"][m["p2"]]["elo"] += gain_elo_p2
                db["players"][m["p1"]]["stats_played"] += 1
                db["players"][m["p2"]]["stats_played"] += 1
                
                # Distribution des points de pronostic (Façon MonPetitProno)
                for bet in m["bets"]:
                    if bet["predicted"] == winner:
                        points_gained = int(bet["odds"] * 10)
                        if "prono_points" not in db["players"][bet["bettor"]]:
                            db["players"][bet["bettor"]]["prono_points"] = 0
                        db["players"][bet["bettor"]]["prono_points"] += points_gained
                
                m["status"] = "completed"
                m["winner"] = winner
                
                if winner == "draw":
                    desc = f"🤝 Match Nul entre {name1} et {name2} (Évol. ELO: {name1} {gain_elo_p1:+.0f}, {name2} {gain_elo_p2:+.0f})"
                else:
                    w_name = name1 if winner == m["p1"] else name2
                    l_name = name2 if winner == m["p1"] else name1
                    gain = gain_elo_p1 if winner == m["p1"] else gain_elo_p2
                    desc = f"🏆 {w_name} a battu {l_name} ({int(gain):+d} ELO)"
                    
                db["history"].append({
                    "date": datetime.now().isoformat(),
                    "desc": desc
                })
                
                save_db(db)
                st.success("Match terminé et points de pronos distribués !")
                st.rerun()
        st.divider()

# --- TAB 3 : CLASSEMENT PRONOS ---
with tab3:
    st.header("🎯 Classement des Pronostiqueurs")
    
    players_prono = list(db["players"].values())
    if not players_prono:
        st.info("Aucun joueur inscrit.")
    else:
        players_prono.sort(key=lambda x: x.get("prono_points", 0), reverse=True)
        
        prono_data = []
        for i, p in enumerate(players_prono, 1):
            prono_data.append({
                "Rang": i,
                "Joueur": p["name"],
                "Points Prono": p.get("prono_points", 0)
            })
            
        df_prono = pd.DataFrame(prono_data)
        
        st.dataframe(
            df_prono,
            column_config={
                "Rang": st.column_config.NumberColumn("Rang", format="%d 🎯"),
                "Points Prono": st.column_config.ProgressColumn(
                    "Score",
                    min_value=0,
                    max_value=max(df_prono["Points Prono"].max() + 10, 50),
                    format="%d pts"
                )
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.divider()
        st.subheader("📊 Comparatif des points")
        chart_prono = df_prono.set_index("Joueur")["Points Prono"]
        st.bar_chart(chart_prono, color="#FF9800")

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
            p1_name = db["players"][m["p1"]]["name"]
            p2_name = db["players"][m["p2"]]["name"]
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
        
        best_prono_player = max(db["players"].values(), key=lambda x: x.get("prono_points", 0))
        most_active = max(db["players"].values(), key=lambda x: x["stats_played"])
        
        with cols[0]:
            st.metric("🎯 Roi des Pronos", f"{best_prono_player.get('prono_points', 0)} pts", best_prono_player['name'])
        with cols[1]:
            st.metric("🎾 Joueur le plus actif", f"{most_active['stats_played']} matchs", most_active['name'])
            
        st.divider()
        st.subheader("🎯 Performances des joueurs (Matchs & Taux de victoire)")
        
        chart_data = []
        for p in db["players"].values():
            win_rate = (p["stats_won"] / p["stats_played"] * 100) if p["stats_played"] > 0 else 0
            chart_data.append({
                "Joueur": p["name"],
                "Matchs Joués": p["stats_played"],
                "Taux de Victoire (%)": win_rate
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
