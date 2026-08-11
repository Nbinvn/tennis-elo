import json
import os
import streamlit as st

# --- CONFIGURATION ET BASE DE DONNÉES SIMPLIFIÉE ---
DATA_FILE = "joueurs.json"
MOT_DE_PASSE_GROUPE = "tennis2026"  # <--- Change ton mot de passe ici

# Chargement / Sauvegarde des données
def charger_joueurs():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    # Joueurs par défaut avec un ELO initial de 1000
    return {"Alex": 1000, "Thomas": 1000, "Maxime": 1000, "Julien": 1000}

def sauvegarder_joueurs(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- FORMULES MATHÉMATIQUES (ELO & COTES) ---
def calcul_probabilite(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))

def calculer_cote(probabilite):
    return round(1 / probabilite, 2)

def maj_elo(elo_a, elo_b, gagnant_est_a, k=32):
    prob_a = calcul_probabilite(elo_a, elo_b)
    score_a = 1 if gagnant_est_a else 0
    nouveau_a = elo_a + k * (score_a - prob_a)
    nouveau_b = elo_b + k * ((1 - score_a) - (1 - prob_a))
    return round(nouveau_a), round(nouveau_b)

# --- PROTECTION PAR MOT DE PASSE ---
if "authentifie" not in st.session_state:
    st.session_state.authentifie = False

if not st.session_state.authentifie:
    st.title("🔒 Accès Groupe Tennis")
    pwd = st.text_input("Mot de passe du groupe", type="password")
    if st.button("Se connecter"):
        if pwd == MOT_DE_PASSE_GROUPE:
            st.session_state.authentifie = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect")
    st.stop()

# --- INTERFACE PRINCIPALE ---
st.title("🎾 Classement & Paris Tennis")
joueurs = charger_joueurs()

# 1. CLASSEMENT
st.header("🏆 Classement ELO")
classement = sorted(joueurs.items(), key=lambda x: x[1], reverse=True)
for rang, (nom, elo) in enumerate(classement, 1):
    st.write(f"**#{rang} {nom}** — {elo} pts")

st.divider()

# 2. CALCULATEUR DE COTES POUR LES PARIS
st.header("🎲 Préparer un pari")
col1, col2 = st.columns(2)
with col1:
    j1 = st.selectbox("Joueur 1", list(joueurs.keys()), index=0)
with col2:
    j2_options = [j for j in joueurs.keys() if j != j1]
    j2 = st.selectbox("Joueur 2", j2_options, index=0)

prob_j1 = calcul_probabilite(joueurs[j1], joueurs[j2])
prob_j2 = 1 - prob_j1

st.info(f"**Cotes du match :**\n* {j1} : **{calculer_cote(prob_j1)}**\n* {j2} : **{calculer_cote(prob_j2)}**")

st.divider()

# 3. ENREGISTRER UN RÉSULTAT
st.header("📝 Enregistrer un résultat")
gagnant = st.radio("Qui a gagné le match ?", [j1, j2])

if st.button("Valider le résultat"):
    gagnant_est_j1 = (gagnant == j1)
    nouv_j1, nouv_j2 = maj_elo(joueurs[j1], joueurs[j2], gagnant_est_j1)
    
    joueurs[j1] = nouv_j1
    joueurs[j2] = nouv_j2
    sauvegarder_joueurs(joueurs)
    
    st.success("Résultat enregistré et ELO mis à jour !")
    st.rerun()