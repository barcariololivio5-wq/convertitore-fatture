import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import json
from pydantic import BaseModel, Field
import pandas as pd
import io
import requests

# Schema dei dati che Gemini deve estrarre obbligatoriamente
class DatiFatturaEstera(BaseModel):
    fornitore: str = Field(description="Nome dell'azienda che ha emesso la fattura")
    paese_provenienza: str = Field(description="Paese del fornitore (es. USA, Irlanda, UK)")
    data_documento: str = Field(description="Data della fattura TASSATIVAMENTE nel formato ANNO-MESE-GIORNO (es. 2026-07-07)")
    valuta_originale: str = Field(description="Codice ISO a 3 lettere della valuta originale (es. USD, GBP, CHF, JPY, EUR)")
    imponibile_valuta_originale: float = Field(description="Importo imponibile totale nella valuta originale")
    aliquota_iva_italiana: str = Field(description="Trattamento IVA per l'Italia (es. 'Reverse Charge - Servizi UE', 'Fuori Ambito IVA Art. 7-ter', 'Esente')")
    nota_per_commercialista: str = Field(description="Spiegazione dettagliata sul trattamento IVA italiano (es. autofattura, integrazione registro, ecc.)")

st.set_page_config(page_title="Convertitore Fatture Automatizzato", page_icon="🏦", layout="centered")

st.title("🏦 Convertitore Fiscale di Fatture Estere")
st.write("Strumento professionale con calcolo del **cambio ufficiale della Banca Centrale Europea** e regole di **Reverse Charge**.")
st.write("---")

api_key = st.sidebar.text_input("Inserisci la tua Gemini API Key", type="password")

if not api_key:
    st.warning("👈 Inserisci la tua API Key nella barra laterale sinistra per sbloccare il software.")
else:
    client = genai.Client(api_key=api_key)
    
    file_caricato = st.file_uploader("Carica la fattura (Immagine o Screenshot)", type=["png", "jpg", "jpeg"])
    
    if file_caricato is not None:
        immagine = Image.open(file_caricato)
        st.image(immagine, caption="Fattura caricata nel sistema", use_container_width=True)
        
        if st.button("🧠 Elabora, Converti e Applica Leggi Fiscali"):
            with st.spinner("Lettura documento e collegamento ai server BCE per il tasso di cambio..."):
                try:
                    # Chiediamo a Gemini di leggere e contestualizzare fiscalmente
                    prompt = """
                    Analizza questa fattura estera destinata a una Partita IVA Italiana:
                    1. Trova il fornitore, paese, l'importo e la valuta originale.
                    2. Converti la data nel formato ISO YYYY-MM-DD.
                    3. Determina se si applica il Reverse Charge (es. Servizi da paesi dell'Unione Europea come Google/Meta/Zoom Irlanda) 
                       oppure l'Art. 7-ter del DPR 633/72 per servizi Extra-UE.
                    Compila accuratamente lo schema JSON fornito.
                    """
                    
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[immagine, prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=DatiFatturaEstera,
                        ),
                    )
                    
                    risultato = json.loads(response.text)
                    
                    # --- INTEGRAZIONE API ESTERNA PER IL CAMBIO VALUTA UFFICIALE ---
                    data_doc = risultato["data_documento"]
                    valuta_orig = risultato["valuta_originale"].upper()
                    importo_orig = risultato["imponibile_valuta_originale"]
                    
                    tasso_cambio_bce = 1.0
                    nota_cambio = "Nessuna conversione necessaria (Valuta originaria in Euro)."
                    
                    if valuta_orig != "EUR":
                        try:
                            # Interroghiamo l'API pubblica Frankfurter (dati BCE) per la data esatta della fattura
                            url_api = f"https://api.frankfurter.app/{data_doc}?from={valuta_orig}&to=EUR"
                            risposta_bce = requests.get(url_api, timeout=5).json()
                            
                            if "rates" in risposta_bce and "EUR" in risposta_bce["rates"]:
                                tasso_cambio_bce = risposta_bce["rates"]["EUR"]
                                nota_cambio = f"Tasso ufficiale BCE al {data_doc} per la valuta {valuta_orig}."
                            else:
                                tasso_cambio_bce = 1.0
                                nota_cambio = "Attenzione: Impossibile trovare il cambio esatto per questa data. Usato tasso 1:1 di riserva."
                        except Exception:
                            tasso_cambio_bce = 1.0
                            nota_cambio = "Connessione ai server di cambio fallita. Usato tasso di riserva 1:1."
                    
                    # Calcolo matematico preciso dell'imponibile convertito in Euro
                    imponibile_in_euro = importo_orig * tasso_cambio_bce
                    
                    st.success("✨ Elaborazione e verifiche fiscali completate!")
                    
                    # --- CREAZIONE DEL REPORT VISIVO ---
                    st.write("### 📋 Report Contabile e Fiscale")
                    
                    tabella_dati = {
                        "Elemento Fiscale": [
                            "Fornitore", "Paese di Origine", "Data Fattura", 
                            "Valuta Originale", "Importo Originale", 
                            "Tasso di Cambio BCE", "Totale Imponibile in EURO (€)", 
                            "Trattamento IVA Italia", "Nota per la Dichiarazione / Registro"
                        ],
                        "Dati Rilevati ed Elaborati": [
                            risultato["fornitore"], risultato["paese_provenienza"], data_doc,
                            valuta_orig, f"{importo_orig:.2f} {valuta_orig}",
                            f"{tasso_cambio_bce:.4f} ({nota_cambio})", f"{imponibile_in_euro:.2f} €",
                            risultato["aliquota_iva_italiana"], risultato["nota_per_commercialista"]
                        ]
                    }
                    df_visivo = pd.DataFrame(tabella_dati)
                    st.table(df_visivo)
                    
                    # --- PREPARAZIONE DEL FILE EXCEL CON I DATI ARRICCHITI ---
                    # Aggiungiamo i dati calcolati via Python all'oggetto finale
                    risultato["cambio_ufficiale_bce"] = tasso_cambio_bce
                    risultato["imponibile_calcolato_in_euro"] = round(imponibile_in_euro, 2)
                    
                    df_excel = pd.DataFrame([risultato])
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_excel.to_excel(writer, index=False, sheet_name='Nota di Registrazione')
                    buffer.seek(0)
                    
                    st.write("---")
                    st.download_button(
                        label="📥 Scarica Report Excel Certificato",
                        data=buffer,
                        file_name=f"registrazione_bce_{risultato['fornitore']}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                except Exception as e:
                    st.error(f"Errore tecnico durante l'elaborazione: {e}")
