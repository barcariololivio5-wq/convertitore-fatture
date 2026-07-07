import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import json
from pydantic import BaseModel

# Definiamo la struttura dei dati che l'IA deve estrarre
class DatiContabili(BaseModel):
    fornitore: str
    paese_provenienza: str
    data_documento: str
    imponibile_valuta_originale: float
    valuta: str
    applicazione_reverse_charge: bool

st.set_page_config(page_title="Convertitore Fatture Estere", page_icon="📊", layout="centered")

st.title("📊 Convertitore Automatico Fatture Estere")
st.write("Trascina la tua fattura estera (PDF o Immagine) e ottieni i dati pronti per la contabilità italiana.")
st.write("---")

# Barra laterale per inserire la chiave API di Google
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
                    
                    st.write("### 📋 Dati Estratti:")
                    st.json(risultato)
                    
                    st.button("📥 Scarica file Excel (Pronto nella prossima versione)")
                    
                except Exception as e:
                    st.error(f"Errore durante l'analisi: {e}")
