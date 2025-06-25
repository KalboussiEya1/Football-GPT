import streamlit as st
import pandas as pd
import re
import json
from io import BytesIO
from openai import OpenAI
from fuzzywuzzy import process

# --- CONFIG
st.set_page_config(layout="wide", page_title="Sélection intelligente des Joueurs")

# --- OPENAI CLIENT
client = OpenAI(api_key=st.secrets["openai"]["api_key"])

# --- TITRE
st.title("Sélection intelligente des Joueurs")

# --- FICHIER UPLOAD
uploaded_file = st.file_uploader("Importer un fichier Excel", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")

    # --- POSITION NORMALIZATION
    def get_best_match(value, choices, threshold=80):
        if not isinstance(value, str):
            return value
        match, score = process.extractOne(value.strip(), choices)
        return match if score >= threshold else value

    def normalize_position(value):
        if not isinstance(value, str):
            return value
        return get_best_match(value.strip(), [str(v).strip() for v in df['Position'].unique()])

    # --- PROMPT
    PROMPT_TEMPLATE = """
    Tu es un assistant qui extrait des conditions de filtrage à partir d'une requête utilisateur.
    Colonnes disponibles : {columns}
    Valeurs exactes pour la colonne 'Position' : {position_values}

    Réponds uniquement en JSON :
    {{
      "conditions": [
        ["colonne", "opérateur", "valeur"]
      ]
    }}
    """

    def extract_json_from_response(text):
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        return match.group(1) if match else text

    def get_conditions(query):
        position_values = df['Position'].unique().tolist() if 'Position' in df.columns else []
        prompt = PROMPT_TEMPLATE.format(
            columns=list(df.columns),
            position_values=position_values
        )

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": query}
            ],
            temperature=0.1
        )

        content = response.choices[0].message.content
        json_str = extract_json_from_response(content)

        try:
            return json.loads(json_str).get("conditions", [])
        except Exception as e:
            st.error(f"Erreur JSON: {e}\nRéponse brute: {content}")
            return []

    def apply_filters(df, conditions):
        df_filtered = df.copy()

        for col, op, val in conditions:
            if col not in df.columns:
                continue

            op = op.replace("&gt;", ">").replace("&lt;", "<").replace("&ge;", ">=").replace("&le;", "<=")

            if col.lower() == 'position':
                val = normalize_position(val)

            try:
                series = df_filtered[col]

                if op == ">":
                    df_filtered = df_filtered[series > float(val)]
                elif op == "<":
                    df_filtered = df_filtered[series < float(val)]
                elif op == ">=":
                    df_filtered = df_filtered[series >= float(val)]
                elif op == "<=":
                    df_filtered = df_filtered[series <= float(val)]
                elif op in ["==", "="]:
                    if pd.api.types.is_numeric_dtype(series):
                        df_filtered = df_filtered[series == float(val)]
                    else:
                        df_filtered = df_filtered[series.astype(str).str.strip().str.lower() == str(val).strip().lower()]
                elif op == "contient":
                    df_filtered = df_filtered[series.astype(str).str.contains(str(val), case=False, na=False)]

            except:
                continue

        return df_filtered

    # --- INTERFACE MINIMALE
    query = st.text_input("Saisir votre requête en langage naturel")

    if query:
        with st.spinner("Analyse de la requête..."):
            conditions = get_conditions(query)
            st.code(json.dumps(conditions, ensure_ascii=False, separators=(',', ':')), language="json")


            if conditions:
                filtered = apply_filters(df, conditions)

                if not filtered.empty:
                    st.dataframe(filtered, use_container_width=True)

                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        filtered.to_excel(writer, index=False)

                    st.download_button(
                        "📥 Télécharger les résultats",
                        output.getvalue(),
                        file_name="resultats_filtres.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Aucun résultat trouvé.")
else:
    st.info("Veuillez importer un fichier Excel.")
