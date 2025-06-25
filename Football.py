import streamlit as st
import pandas as pd
import re
import json
from io import BytesIO
from openai import OpenAI
from rapidfuzz import process, fuzz

# --- CONFIGURATION DE LA PAGE
st.set_page_config(
    layout="wide",
    page_title="Filtrage intelligent des données Excel avec IA"
)

# --- CRÉER LE CLIENT OPENAI
client = OpenAI(api_key=st.secrets["openai"]["api_key"])

# --- INTERFACE
st.title("Analyse intelligente de vos données Excel")

uploaded_file = st.file_uploader("1 - Importer votre fichier Excel", type=["xlsx"])


# --- UTILITAIRES
def extract_json_from_response(text):
    pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    return text


def get_best_match(input_col, columns, threshold=80):
    match = process.extractOne(input_col, columns, scorer=fuzz.ratio)
    if match and match[1] >= threshold:
        return match[0]
    return None


def get_best_value_match(value, possible_values, threshold=80):
    match = process.extractOne(str(value), list(map(str, possible_values)), scorer=fuzz.ratio)
    if match and match[1] >= threshold:
        return match[0]
    return value


def apply_filters(df, conditions):
    df_filtered = df.copy()
    colnames = list(df.columns)

    for col, op, val in conditions:
        # Correspondance du nom de colonne
        col_matched = next((c for c in colnames if c.lower().strip() == col.lower().strip()), None)
        if not col_matched:
            col_matched = get_best_match(col, colnames)

        if not col_matched:
            st.warning(f"Colonne inconnue : {col}")
            continue

        try:
            # Correction de la valeur si applicable
            if op.lower() in ["==", "!=", "contient"] and df_filtered[col_matched].dtype == object:
                unique_vals = df_filtered[col_matched].dropna().unique()
                corrected_val = get_best_value_match(val, unique_vals)
                if corrected_val != val:
                    st.info(f"Correction de la valeur : '{val}' → '{corrected_val}'")
                    val = corrected_val

            if op in [">", "<", ">=", "<=", "==", "!="]:
                df_filtered = df_filtered.query(f"`{col_matched}` {op} @val")
            elif op.lower() == "contient":
                df_filtered = df_filtered[df_filtered[col_matched].astype(str).str.contains(str(val), case=False, na=False)]
            else:
                st.warning(f"Opérateur inconnu : {op}")
        except Exception as e:
            st.warning(f"Erreur lors du filtrage sur '{col_matched}' : {e}")

    return df_filtered


# --- TRAITEMENT PRINCIPAL
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.success(f"Données chargées : {df.shape[0]} lignes | {df.shape[1]} colonnes")

    PROMPT_TEMPLATE = f"""
    Tu es un assistant qui extrait des conditions de filtrage pour une base de données Excel.
    Voici les colonnes disponibles : {list(df.columns)}.
    L'utilisateur va poser une requête en langage naturel pour filtrer ces données.
    La requête peut contenir plusieurs conditions numériques ou de texte.

    Réponds uniquement sous forme JSON pur, sans balises Markdown :
    {{
      "conditions": [ ["nom_colonne", "opérateur", valeur] ]
    }}
    """

    st.markdown("2 - Posez votre requête en langage naturel")
    query = st.text_input("", label_visibility="collapsed")

    def get_conditions(query):
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": PROMPT_TEMPLATE},
                {"role": "user", "content": query}
            ]
        )
        content = response.choices[0].message.content
        json_str = extract_json_from_response(content)
        try:
            parsed = json.loads(json_str)
            return parsed.get("conditions", [])
        except Exception as e:
            st.error(f"Erreur JSON GPT : {e}")
            st.json(content)
            return []

    if query:
        conditions = get_conditions(query)
        st.info(f"Conditions extraites : {conditions}")

        filtered = apply_filters(df, conditions)
        st.success(f"{len(filtered)} lignes trouvées après filtrage.")

        st.dataframe(filtered, use_container_width=True)

        if not filtered.empty:
            st.header("3 - Télécharger les résultats en Excel")

            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                filtered.to_excel(writer, index=False, sheet_name='Résultats_Filtrés')

            output.seek(0)

            st.download_button(
                "Télécharger Excel",
                output,
                file_name="resultats_filtres.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
else:
    st.info("Veuillez importer un fichier Excel pour commencer.")
