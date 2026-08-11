import json
import os
import uuid
from datetime import datetime
import streamlit as st

# --- CONFIGURATION ---
DATA_FILE = "joueurs_v2.json"
ADMIN_PWD = "admin"  # Mot de passe administrateur par défaut

# --- GESTION DE LA BASE DE DONNÉES (JSON) ---
def init_db():
    if not os.path.exists(DATA_FILE):
        db = {
            "bank": 0.0,
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
    """Calcule la probabilité brute de victoire (Formule ELO standard)"""
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))

def get_probs_with_draw(elo_a, elo_b):
    """Calcule les probabilités en incluant le Match Nul"""
    p_a_raw = get_prob(elo_a, elo_b)
    p_b_raw = 1 - p_a_raw
    
    # La probabilité de match nul est max (15%) si les ELO sont égaux
    prob_draw = 0.15 * (1 - abs(p_a_raw - p_b_raw))
    
    # On ajuste les chances de victoire en soustrayant la probabilité du nul
    prob_a = p_a_raw * (1 - prob_draw)
    prob_b = p_b_raw * (1 - prob_draw)
    
    return prob_a, prob_b, prob_draw

def get_odds(prob):
    return round(1 / prob, 2) if prob > 0 else 1.01

def format_elo(real_elo):
    return int(real_elo - 1000)

# --- INITIALISATION SESSION ---
db = init_db()
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- SYSTÈME D'AUTHENTIFICATION ---
if st.session_state.user_id is None and not st.session_state.is_admin:
    st.title("🔒 Connexion - Tennis Bet & ELO")
    
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
        solde = db["players"][st.session_state.user_id]["balance"]
        st.metric("Mon Solde", f"{solde:.2f} CAD")
        
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
                    "balance": 0.0,
                    "stats_played": 0,
                    "stats_won": 0,
                    "max_win": 0.0
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
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏆 Classement", "📅 Matchs & Paris", "💸 Tricount", "📜 Historique", "📊 Stats"])

# --- TAB 1 : CLASSEMENT ---
with tab1:
    st.header("🏆 Classement ELO")
    players_list = list(db["players"].values())
    players_list.sort(key=lambda x: x["elo"], reverse=True)
    
    for i, p in enumerate(players_list, 1):
        win_rate = (p["stats_won"] / p["stats_played"] * 100) if p["stats_played"] > 0 else 0
        st.write(f"**#{i} {p['name']}** — **{format_elo(p['elo'])} pts** *(Victoires: {win_rate:.0f}%)*")

# --- TAB 2 : MATCHS ET PARIS ---
with tab2:
    st.header("📅 Gestion des Matchs")
    
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
    st.subheader("🔥 Matchs à venir & Paris")
    
    pending_matches = {k: v for k, v in db["matches"].items() if v["status"] == "pending"}
    if not pending_matches:
        st.info("Aucun match prévu pour le moment.")
        
    for m_id, m in pending_matches.items():
        name1 = db["players"][m["p1"]]["name"]
        name2 = db["players"][m["p2"]]["name"]
        dt = datetime.fromisoformat(m["datetime"])
        
        # Calcul des 3 cotes (P1, P2 et Nul)
        prob_p1, prob_p2, prob_draw = get_probs_with_draw(db["players"][m["p1"]]["elo"], db["players"][m["p2"]]["elo"])
        odds_p1 = get_odds(prob_p1)
        odds_p2 = get_odds(prob_p2)
        odds_draw = get_odds(prob_draw)
        
        st.markdown(f"### {name1} 🆚 {name2}")
        st.caption(f"🕒 Prévu le {dt.strftime('%d/%m/%Y à %H:%M')}")
        st.write(f"Cotes actuelles : **{name1} ({odds_p1})** | **Nul ({odds_draw})** | **{name2} ({odds_p2})**")
        
        is_playing = st.session_state.user_id in [m["p1"], m["p2"]]
        is_started = datetime.now() > dt
        my_bet = next((b for b in m["bets"] if b["bettor"] == st.session_state.user_id), None)
        
        if my_bet:
            pred_name = "Match Nul" if my_bet['predicted'] == "draw" else db["players"][my_bet['predicted']]['name']
            st.success(f"✅ Tu as parié {my_bet['amount']} CAD sur {pred_name} (Cote: {my_bet['odds']})")
        elif is_playing:
            st.warning("Tu ne peux pas parier sur ton propre match.")
        elif is_started:
            st.error("Match commencé, les paris sont fermés.")
        else:
            with st.form(key=f"bet_form_{m_id}"):
                options_pari = {m["p1"]: f"Victoire {name1}", "draw": "Match Nul", m["p2"]: f"Victoire {name2}"}
                pred = st.radio("Sur quel résultat parier ?", list(options_pari.keys()), format_func=lambda x: options_pari[x])
                amount = st.number_input("Montant de la mise (Max 5 CAD)", min_value=0.5, max_value=5.0, step=0.5)
                submit_bet = st.form_submit_button("Valider mon pari")
                
                if submit_bet:
                    if pred == m["p1"]: odds_locked = odds_p1
                    elif pred == m["p2"]: odds_locked = odds_p2
                    else: odds_locked = odds_draw
                    
                    db["players"][st.session_state.user_id]["balance"] -= amount
                    db["bank"] += amount
                    
                    m["bets"].append({
                        "bettor": st.session_state.user_id,
                        "predicted": pred,
                        "amount": amount,
                        "odds": odds_locked
                    })
                    save_db(db)
                    st.success("Pari enregistré !")
                    st.rerun()
                    
        # Clôture du match
        with st.expander("🏁 Terminer ce match (Saisir le résultat)"):
            options_result = {m["p1"]: f"Victoire {name1}", "draw": "Match Nul", m["p2"]: f"Victoire {name2}"}
            winner = st.radio("Résultat final", list(options_result.keys()), format_func=lambda x: options_result[x], key=f"win_{m_id}")
            
            if st.button("Valider le résultat et distribuer les gains", key=f"btn_{m_id}"):
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
                else: # Match Nul
                    score_p1, score_p2 = 0.5, 0.5
                    
                gain_elo_p1 = K * (score_p1 - p_1_raw)
                gain_elo_p2 = K * (score_p2 - p_2_raw)
                
                db["players"][m["p1"]]["elo"] += gain_elo_p1
                db["players"][m["p2"]]["elo"] += gain_elo_p2
                db["players"][m["p1"]]["stats_played"] += 1
                db["players"][m["p2"]]["stats_played"] += 1
                
                # Résolution des paris
                for bet in m["bets"]:
                    if bet["predicted"] == winner:
                        payout = bet["amount"] * bet["odds"]
                        profit = payout - bet["amount"]
                        tax = profit * 0.20
                        net_bettor = profit - tax
                        
                        db["players"][bet["bettor"]]["balance"] += (bet["amount"] + net_bettor)
                        db["bank"] -= payout
                        
                        # Distribution de la taxe
                        if winner == "draw":
                            db["players"][m["p1"]]["balance"] += tax / 2
                            db["players"][m["p2"]]["balance"] += tax / 2
                        else:
                            db["players"][winner]["balance"] += tax
                            
                        if net_bettor > db["players"][bet["bettor"]].get("max_win", 0):
                            db["players"][bet["bettor"]]["max_win"] = net_bettor
                
                m["status"] = "completed"
                m["winner"] = winner
                
                if winner == "draw":
                    desc = f"🤝 Match Nul entre {name1} et {name2} (Évol. ELO: {name1} {gain_elo_p1:+.0f}, {name2} {gain_elo_p2:+.0f})"
                else:
                    w_name = name1 if winner == m["p1"] else name2
                    l_name = name2 if winner == m["p1"] else name1
                    gain = gain_elo_p1 if winner == m["p1"] else gain_elo_p2
                    desc = f"🏆 {w_name} a battu {l_name} (+{int(gain)} ELO)"
                    
                db["history"].append({
                    "date": datetime.now().isoformat(),
                    "desc": desc
                })
                
                save_db(db)
                st.success("Match terminé et gains distribués !")
                st.rerun()

# --- TAB 3 : TRICOUNT (DETTES) ---
with tab3:
    st.header("💸 Tricount & Règlements")
    
    balances = {db["players"][pid]["name"]: db["players"][pid]["balance"] for pid in db["players"]}
    balances["🏦 La Banque (Cagnotte)"] = db["bank"]
    
    st.subheader("Soldes actuels")
    for nom, solde in balances.items():
        if abs(solde) > 0.01:
            color = "green" if solde > 0 else "red"
            st.markdown(f"**{nom}** : :{color}[{solde:+.2f} CAD]")
            
    st.divider()
    
    st.info("💡 Pour solder les comptes, la banque (qui accumule les pertes des joueurs) doit être partagée équitablement.")
    if abs(db["bank"]) > 0.01:
        if st.button("🔄 Partager la Banque entre tous les joueurs"):
            nb_players = len(db["players"])
            part = db["bank"] / nb_players
            for pid in db["players"]:
                db["players"][pid]["balance"] += part
            db["bank"] = 0.0
            save_db(db)
            st.success("Banque répartie avec succès !")
            st.rerun()
            
    st.divider()
    st.subheader("🔁 Remboursements Simplifiés")
    
    crediteurs = [[k, v] for k, v in balances.items() if v > 0.01]
    debiteurs = [[k, abs(v)] for k, v in balances.items() if v < -0.01]
    
    crediteurs.sort(key=lambda x: x[1], reverse=True)
    debiteurs.sort(key=lambda x: x[1], reverse=True)
    
    transactions = []
    i, j = 0, 0
    while i < len(crediteurs) and j < len(debiteurs):
        c_name, c_amount = crediteurs[i]
        d_name, d_amount = debiteurs[j]
        
        montant = min(c_amount, d_amount)
        transactions.append(f"💸 **{d_name}** doit envoyer **{montant:.2f} CAD** à **{c_name}**")
        
        crediteurs[i][1] -= montant
        debiteurs[j][1] -= montant
        
        if crediteurs[i][1] < 0.01: i += 1
        if debiteurs[j][1] < 0.01: j += 1
        
    if transactions:
        for t in transactions:
            st.markdown(t)
            
        st.warning("⚠️ Marquer les dettes comme payées remettra tous les soldes financiers à ZÉRO.")
        if st.button("✅ Marquer toutes les dettes comme PAYÉES"):
            for pid in db["players"]:
                db["players"][pid]["balance"] = 0.0
            db["bank"] = 0.0
            save_db(db)
            st.success("Comptes remis à zéro !")
            st.rerun()
    else:
        st.success("✨ Tout le monde est à jour ! Aucune dette.")

# --- TAB 4 : HISTORIQUE ---
with tab4:
    st.header("📜 Historique des Matchs")
    completed = [m for m in db["matches"].values() if m["status"] == "completed"]
    completed.sort(key=lambda x: x["datetime"], reverse=True)
    
    for m in completed:
        dt = datetime.fromisoformat(m["datetime"]).strftime('%d/%m/%Y')
        if m["winner"] == "draw":
            p1_name = db["players"][m["p1"]]["name"]
            p2_name = db["players"][m["p2"]]["name"]
            st.markdown(f"**{dt}** : 🤝 Match Nul entre **{p1_name}** et **{p2_name}** ({len(m['bets'])} paris)")
        else:
            w_name = db["players"][m["winner"]]["name"]
            l_id = m["p2"] if m["winner"] == m["p1"] else m["p1"]
            l_name = db["players"][l_id]["name"]
            st.markdown(f"**{dt}** : 🏆 **{w_name}** a battu {l_name} ({len(m['bets'])} paris)")

# --- TAB 5 : STATS ---
with tab5:
    st.header("📊 Statistiques Globales")
    
    cols = st.columns(3)
    
    if db["players"]:
        best_bettor = max(db["players"].values(), key=lambda x: x.get("max_win", 0))
        most_active = max(db["players"].values(), key=lambda x: x["stats_played"])
        
        with cols[0]:
            st.metric("Plus gros gain (Net)", f"{best_bettor.get('max_win', 0):.2f} CAD", best_bettor['name'])
        with cols[1]:
            st.metric("Joueur le plus actif", f"{most_active['stats_played']} matchs", most_active['name'])
        with cols[2]:
            total_bets = sum(len(m["bets"]) for m in db["matches"].values())
            st.metric("Total des paris réalisés", f"{total_bets}")
