import streamlit as st
import pandas as pd
import openai
import toml
import re
import json
from pathlib import Path
from io import BytesIO

# --- CONFIGURATION DE LA PAGE
st.set_page_config(
    layout="wide",
    page_title="Recrutement des joueurs de football avec IA"
)

# --- CHARGER LA CLE API
secrets_path = Path.home() / ".streamlit" / "secrets.toml"

openai.api_key = st.secrets["openai"]["api_key"]

# --- DICTIONNAIRE DES SYNONYMES DE COLONNES
COLUMN_SYNONYMS = {
    "passes réussies": "Passes réussies",
    "buts": "Buts",
    "tacles": "Tacles réussis",
    "centres réussis": "Centres réussis",
    "passes décisives": "Passes décisives",
    "dribbles réussis": "Dribbles réussis",
    "interceptions": "Interceptions",
    "tacles réussis": "Tacles réussis",
    "duels gagnés": "Duels gagnés",
    "centres bloqués": "Centres bloqués",
    "dégagements": "Dégagements",
    "pressings réussis": "Pressings Réussis",
    "arrêts": "Arrêts",
    "sorties aériennes réussies": "Sorties aériennes réussies",
    "passes manquées": "Passes manquées",
    "taux de conversion des tirs": "Taux de conversion des tirs (%)",
    "expected goals": "Expected Goals (xG)",
    "expected assists": "Expected Assists (xA)",
    "pression exercée": "Pression exercée",
    "position moyenne x": "Position moyenne des joueurs X",
    "position moyenne y": "Position moyenne des joueurs Y",
    "efficacité des contres": "Efficacité des contres (%)",
    "tiers défensif": "Tiers défensif (%)",
    "tiers central": "Tiers central (%)",
    "tiers offensif": "Tiers offensif (%)",
    "distance parcourue": "Distance parcourue",
    "vitesse maximale": "Vitesse maximale",
    "sprints réalisés": "Sprints réalisés",
    "ballons touchés": "Ballons touchés",
    "passes vers l'avant": "Passes vers l'avant",
    "ballons perdus": "Ballons perdus",
    "tirs cadrés": "Tirs cadrés",
    "tirs non cadrés": "Tirs non cadrés",
    "tirs bloqués": "Tirs bloqués",
    "numéro de maillot": "Numéro de maillot",
    "id match": "ID Match",
    "id joueur": "ID Joueur",
    "joueur": "Joueur",
    "position": "Position",
    "équipe": "Équipe",
}

# --- DICTIONNAIRE DES POSITIONS FRANÇAISES VERS ANGLAISES
POSITION_SYNONYMS = {
    "attaquant": "Striker",
    "milieu": "Midfielder",
    "défenseur": "Defender",
    "gardien": "Goalkeeper",
    "remplaçant": "Substitute",
}

POSITIONS = list(POSITION_SYNONYMS.keys())

# --- INTERFACE
st.title("Recrutement intelligent des joueurs de football")

uploaded_file = st.file_uploader("1 - Importer votre fichier Excel", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.success(f"Données chargées : {df.shape[0]} lignes | {df.shape[1]} colonnes")

    PROMPT_TEMPLATE = f"""
    Tu es un assistant qui aide à extraire des conditions de filtrage sur une base de données de football.
    Voici les colonnes disponibles : {list(df.columns)}.
    Voici les positions possibles : {POSITIONS}.
    Une requête peut contenir des conditions numériques (ex: supérieur à 3) ET une position.
    Réponds uniquement sous la forme JSON pur, sans balises Markdown :
    {{
      "conditions": [ ["colonne", "opérateur", valeur] ],
      "position": "Nom de la position si précisée ou null"
    }}
    Ne réponds rien d'autre.
    """

    def extract_json_from_response(text):
        pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
        return text

    def get_conditions(query):
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": PROMPT_TEMPLATE},
                {"role": "user", "content": query}
            ]
        )
        content = response.choices[0].message.content
        # Ligne supprimée: on n'affiche plus la réponse brute
        json_str = extract_json_from_response(content)
        try:
            parsed = json.loads(json_str)
            return parsed.get("conditions", []), parsed.get("position", None)
        except Exception as e:
            st.error(f"Erreur JSON GPT : {e}")
            st.json(content)
            return [], None

    def standardize_column(name):
        name = name.lower().strip()
        return COLUMN_SYNONYMS.get(name, name)

    def apply_filters(df, conditions, position):
        df_filtered = df.copy()

        for col, op, val in conditions:
            col_std = standardize_column(col)
            if col_std not in df_filtered.columns:
                st.warning(f"Colonne inconnue : {col_std}")
                continue
            try:
                if op == ">":
                    df_filtered = df_filtered[df_filtered[col_std] > val]
                elif op == "<":
                    df_filtered = df_filtered[df_filtered[col_std] < val]
                elif op == ">=":
                    df_filtered = df_filtered[df_filtered[col_std] >= val]
                elif op == "<=":
                    df_filtered = df_filtered[df_filtered[col_std] <= val]
                elif op == "==":
                    df_filtered = df_filtered[df_filtered[col_std] == val]
                else:
                    st.warning(f"Opérateur inconnu : {op}")
            except Exception as e:
                st.warning(f"Erreur filtre {col_std}: {e}")

        if position:
            pos_lower = position.lower().strip()
            pos_en = POSITION_SYNONYMS.get(pos_lower, position)
            st.write(f"Position demandée : {position} -> Traduite en : {pos_en}")

            col_position = [c for c in df_filtered.columns if c.lower() == "position"]
            if col_position:
                df_filtered = df_filtered[
                    df_filtered[col_position[0]].str.contains(pos_en, case=False, na=False)
                ]
            else:
                st.warning("Colonne 'Position' non trouvée.")

        return df_filtered

    st.markdown("2 - Posez votre requête en langage naturel")
    query = st.text_input("")

    if query:
        conditions, position = get_conditions(query)
        st.info(f"Conditions extraites : {conditions} | Position : {position}")

        filtered = apply_filters(df, conditions, position)
        st.success(f"Nombre de joueurs trouvés : {len(filtered)}")

        st.dataframe(filtered, use_container_width=True)

        if not filtered.empty:
            st.header("3 - Télécharger les résultats en Excel")

            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                filtered.to_excel(writer, index=False, sheet_name='Joueurs_Filtrés')
                
            output.seek(0)

            st.download_button(
                "Télécharger Excel",
                output,
                file_name="joueurs_filtrés.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
else:
    st.info("Veuillez importer un fichier Excel pour commencer.")

