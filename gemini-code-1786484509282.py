import json
import os
import uuid
from datetime import datetime
import streamlit as st
import pandas as pd

# --- CONFIGURATION ---
DATA_FILE = "joueurs_v3.json"  # Fichier conservé, aucune donnée ne sera perdue !
ADMIN_PWD = "Admin2026"  # Nouveau mot de passe administrateur

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
    """Recalcule intégralement l'ELO et les pronos de tous les joueurs en rejouant l'historique chronologique."""
    # 1. Remise à zéro des statistiques calculables
    for pid in db["players"]:
        db["players"][pid]["elo"] = 1000.0
        db["players"][pid]["prono_points"] = 0
        db["players"][pid]["stats_played"] = 0
        db["players"][pid]["stats_won"] = 0

    # 2. Récupérer et trier les matchs terminés par ordre chronologique
    completed_matches = [m for m in db["matches"].values() if m["status"] == "completed"]
    completed_matches.sort(key=lambda x: x["datetime"])

    # 3. Rejouer mathématiquement chaque match
    for m in completed_matches:
        p1 = m["p1"]
        p2 = m["p2"]
        winner = m["winner"]
        
        elo_p1 = db["players"][p1]["elo"]
        elo_p2 = db["players"][p2]["elo"]
        
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
            
        gain_elo_p1 = K * (score_p1 - p_1_raw)
        gain_elo_p2 = K * (score_p2 - p_2_raw)
        
        db["players"][p1]["elo"] += gain_elo_p1
        db["players"][p2]["elo"] += gain_elo_p2
        db["players"][p1]["stats_played"] += 1
        db["players"][p2]["stats_played"] += 1
        
        # Recalcul des pronos
        for bet in m.get("bets", []):
            if bet["predicted"] == winner:
                points_gained = int(bet["odds"] * 10)
                db["players"][bet["bettor"]]["prono_points"] += points_gained


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
            # Ordre alphabétique pour la sélection du joueur
            sorted_names = sorted(list(player_names.values()), key=lambda x: x.lower())
            selected_name = st.selectbox("Qui êtes-vous ?", sorted_names)
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
        st.write("👤 **Connecté en tant que : ADMIN GLOBALE**")
    else:
        nom_joueur = db["players"][st.session_state.user_id]["name"]
        st.write(f"👤 **Connecté : {nom_joueur}**")
        pts_prono = db["players"][st.session_state.user_id].get("prono_points", 0)
        st.metric("Mes Points Prono", f"{pts_prono} pts")
        
    if st.button("Se déconnecter"):
        st.session_state.user_id = None
        st.session_state.is_admin = False
        st.rerun()

# --- INTERFACE ADMINISTRATEUR GLOBALE ---
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
        st.subheader("Modifier / Supprimer un joueur")
        if db["players"]:
            # Ordre alphabétique pour la modification de joueur
            sorted_player_ids = sorted(list(db["players"].keys()), key=lambda x: db["players"][x]["name"].lower())
            p_to_edit = st.selectbox("Sélectionner un joueur", sorted_player_ids, format_func=lambda x: db["players"][x]["name"])
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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🏆 Classement ELO", "📅 Matchs & Pronos", "🎯 Classement Pronos", "📜 Historique", "📊 Dashboard", "🛠️ Admin Matchs"])

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
        # Liste triée alphabétiquement
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
    # Tri des matchs en attente par date
    pending_matches = dict(sorted(pending_matches.items(), key=lambda item: item[1]["datetime"]))
    
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
        
        st.markdown("#### 👥 Pronostics enregistrés :")
        if m["bets"]:
            cols_bets = st.columns(len(m["bets"]))
            # Tri alphabétique des pronostiqueurs pour affichage
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
                m["status"] = "completed"
                m["winner"] = winner
                
                if winner == "draw":
                    desc = f"🤝 Match Nul entre {name1} et {name2} a été enregistré."
                else:
                    w_name = name1 if winner == m["p1"] else name2
                    l_name = name2 if winner == m["p1"] else name1
                    desc = f"🏆 {w_name} a battu {l_name}."
                    
                db["history"].append({
                    "date": datetime.now().isoformat(),
                    "desc": desc
                })
                
                # Au lieu de calculer uniquement pour ce match, on recalcule tout pour s'assurer que le système est robuste
                recalculate_all_stats(db)
                save_db(db)
                st.success("Match terminé et points distribués !")
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

# --- TAB 6 : ACCÈS ADMIN MATCHS (Intégré interface Joueur) ---
with tab6:
    st.header("🛠️ Gestion Administrateur des Matchs")
    st.info("Cette section est réservée pour corriger des erreurs (dates, résultats, suppressions).")
    
    admin_match_pass = st.text_input("Mot de passe Admin", type="password", key="pwd_admin_match")
    
    if admin_match_pass == ADMIN_PWD:
        st.success("Accès administrateur déverrouillé.")
        
        def format_match_label(m_id):
            m = db["matches"][m_id]
            p1_name = db["players"][m["p1"]]["name"]
            p2_name = db["players"][m["p2"]]["name"]
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
        # Trier par date chronologique inversée pour l'affichage
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
                    "Modifier le résultat", 
                    list(options_result.keys()), 
                    format_func=lambda x: options_result[x], 
                    index=idx_winner, 
                    key=f"res_{sel_c_id}"
                )
                
                st.warning("⚠️ Toute modification entraînera un recalcul automatique de l'historique ELO et des points de pronostics.")
                
                col_btn_c1, col_btn_c2 = st.columns(2)
                with col_btn_c1:
                    if st.button("Sauvegarder les modifications et recalculer", key=f"btn_update_c_{sel_c_id}"):
                        mc["datetime"] = datetime.combine(new_dc, new_tc).isoformat()
                        mc["winner"] = new_winner
                        
                        db["history"].append({
                            "date": datetime.now().isoformat(),
                            "desc": f"⚠️ Admin a modifié un ancien match (nouveau résultat/date enregistré) - Classement recalculé."
                        })
                        
                        recalculate_all_stats(db)
                        save_db(db)
                        st.success("Match mis à jour et classements recalculés avec succès !")
                        st.rerun()
                with col_btn_c2:
                    if st.button("🗑️ Supprimer ce match et recalculer", key=f"btn_del_c_{sel_c_id}"):
                        del db["matches"][sel_c_id]
                        
                        db["history"].append({
                            "date": datetime.now().isoformat(),
                            "desc": f"⚠️ Admin a supprimé un ancien match - Classement recalculé."
                        })
                        
                        recalculate_all_stats(db)
                        save_db(db)
                        st.success("Match supprimé et classements recalculés avec succès !")
                        st.rerun()
        else:
            st.write("Aucun match terminé.")

    elif admin_match_pass:
        st.error("Mot de passe incorrect.")
