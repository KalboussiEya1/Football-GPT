import streamlit as st
import pandas as pd
import re
import json
from io import BytesIO
from openai import OpenAI
from rapidfuzz import process, fuzz

st.set_page_config(layout="wide", page_title="Filtrage intelligent des joueurs")

client = OpenAI(api_key=st.secrets["openai"]["api_key"])

st.title("Analyse intelligente des joueurs")
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

    operator_map = {
        "=": "==", "==": "==", "!=": "!=", ">": ">", "<": "<", ">=": ">=", "<=": "<=", "contient": "contient"
    }

    for col, op, val in conditions:
        op = operator_map.get(op.strip(), op)
        col_matched = next((c for c in colnames if c.lower().strip() == col.lower().strip()), None)
        if not col_matched:
            col_matched = get_best_match(col, colnames)
        if not col_matched:
            st.warning(f"Colonne inconnue : {col}")
            continue
        try:
            if op in ["==", "!=", "contient"] and df_filtered[col_matched].dtype == object:
                unique_vals = df_filtered[col_matched].dropna().unique()
                corrected_val = get_best_value_match(val, unique_vals)
                if corrected_val != val:
                    st.info(f"Correction de la valeur : '{val}' → '{corrected_val}'")
                    val = corrected_val

            if op in [">", "<", ">=", "<=", "==", "!="]:
                df_filtered = df_filtered.query(f"`{col_matched}` {op} @val")
            elif op == "contient":
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

    tab1, tab2 = st.tabs(["🔍 Filtrage intelligent", "🛠️ Filtrage manuel"])

    with tab1:
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

    with tab2:
        st.subheader("2 - Filtrage manuel via interface graphique")

        df_manual = df.copy()
        numeric_cols = df_manual.select_dtypes(include=["int64", "float64"]).columns
        categorical_cols = df_manual.select_dtypes(include=["object", "category", "bool"]).columns

        filters = {}

        with st.form("manual_filter_form"):
            # Colonnes catégorielles - maintenant toutes avec selectbox simple
            for col in categorical_cols:
                unique_values = df_manual[col].dropna().unique().tolist()
                selected_value = st.selectbox(
                    f"{col} :",
                    options=["Choose an option"] + sorted(unique_values),
                    index=0,
                    key=f"select_{col}"
                )
                if selected_value != "Choose an option":
                    filters[col] = selected_value

            # Colonnes numériques (inchangé)
            for col in numeric_cols:
                min_val, max_val = float(df_manual[col].min()), float(df_manual[col].max())
                if min_val == max_val:
                    st.info(f"La colonne '{col}' a une seule valeur : {min_val}")
                    filters[col] = (min_val, max_val)
                else:
                    selected_range = st.slider(
                        f"{col} :", 
                        min_value=min_val, 
                        max_value=max_val, 
                        value=(min_val, max_val)
                    )
                    filters[col] = selected_range

            submitted = st.form_submit_button("Appliquer les filtres")

        if submitted:
            for col in filters:
                if col in categorical_cols:
                    df_manual = df_manual[df_manual[col] == filters[col]]
                elif col in numeric_cols:
                    min_val, max_val = filters[col]
                    df_manual = df_manual[(df_manual[col] >= min_val) & (df_manual[col] <= max_val)]

            st.success(f"{len(df_manual)} lignes trouvées après filtrage.")
            st.dataframe(df_manual, use_container_width=True)

            if not df_manual.empty:
                st.header("3 - Télécharger les résultats filtrés")
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_manual.to_excel(writer, index=False, sheet_name='Filtres_Manuels')
                output.seek(0)
                st.download_button(
                    "Télécharger Excel",
                    output,
                    file_name="resultats_filtres_manuels.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

else:
    st.info("Veuillez importer un fichier Excel pour commencer.")