import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import json
from pydantic import BaseModel
import pandas as pd
import io

# Struttura dei dati per l'IA
class DatiContabili(BaseModel):
    fornitore: str
    paese_provenienza: str
    data_documento: str
    imponibile_valuta_originale: float
    valuta: str
    applicazione_reverse_charge: bool

st.set_page_config(page_title="Convertitore Fatture Estere", page_icon="📊", layout="centered")

st.title("📊 Convertitore Automatico Fatture Estere")
st.write("Trascina la tua fattura estera (PDF o Immagine) e scarica il file Excel pronto per la contabilità.")
st.write("---")

api_key = st.sidebar.text_input("Inserisci la tua Gemini API Key", type="password")

if not api_key:
    st.warning("👈 Per fare il test inserisci la tua API Key nella barra laterale.")
else:
    client = genai.Client(api_key=api_key)
    
    file_caricato = st.file_uploader("Carica la foto o lo screenshot della fattura", type=["png", "jpg", "jpeg"])
    
    if file_caricato is not None:
        immagine = Image.open(file_caricato)
        st.image(immagine, caption="Documento caricato", use_container_width=True)
        
        if st.button("🧠 Converti Documento"):
            with st.spinner("L'IA sta analizzando la fattura..."):
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[immagine, "Estrai i dati contabili da questa fattura estera per la contabilità italiana."],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=DatiContabili,
                        ),
                    )
                    
                    risultato = json.loads(response.text)
                    st.success("Conversione completata!")
                    
                    # 1. Mostra i dati puliti a schermo
                    st.write("### 📋 Dati Estratti:")
                    st.json(risultato)
                    
                    # 2. Converti i dati in un formato leggibile da Excel (Tabella)
                    df = pd.DataFrame([risultato])
                    
                    # 3. Crea il file Excel temporaneo in memoria
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Dati Contabili')
                    buffer.seek(0)
                    
                    # 4. Attiva il bottone di download reale per l'utente
                    st.write("---")
                    st.download_button(
                        label="📥 Scarica file Excel",
                        data=buffer,
                        file_name="fattura_estera_convertita.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                except Exception as e:
                    st.error(f"Errore durante l'analisi: {e}")
