import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import json
from pydantic import BaseModel, Field
import pandas as pd
import io
import requests

# Schema potenziato con le regole dell'Agenzia delle Entrate
class DatiFatturaEstera(BaseModel):
    fornitore: str = Field(description="Nome dell'azienda che ha emesso la fattura")
    paese_provenienza: str = Field(description="Paese del fornitore (es. USA, Irlanda, UK)")
    is_paese_ue: bool = Field(description="Vero se il paese di provenienza fa parte dell'Unione Europea, Falso se Extra-UE")
    data_documento: str = Field(description="Data della fattura nel formato YYYY-MM-DD")
    valuta_originale: str = Field(description="Codice ISO a 3 lettere (es. USD, GBP, JPY, EUR)")
    imponibile_valuta_originale: float = Field(description="Importo imponibile totale nella valuta originale")
    aliquota_iva_italiana: str = Field(description="Trattamento IVA per l'Italia (es. 'Reverse Charge', 'Art. 7-ter')")
    codice_autofattura_sdi: str = Field(description="Inserisci 'TD17' per servizi esteri, 'TD18' per acquisto beni UE, 'TD19' per beni ex art 17 c.2. Se non applicabile, scrivi 'Non richiesto'")
    obbligo_intrastat: str = Field(description="Scrivi 'SÌ (Acquisto UE)' se è un acquisto da paese UE, altrimenti 'NO (Extra-UE)'")
    nota_per_commercialista: str = Field(description="Spiegazione dettagliata sul trattamento IVA italiano")

st.set_page_config(page_title="Convertitore Fatture Automatizzato", page_icon="🏦", layout="centered")

st.title("🏦 Convertitore Fiscale di Fatture Estere")
st.write("Calcolo **cambio BCE**, generazione **Codice SDI (TD17/18/19)** e calcolo **F24 per Forfettari**.")
st.write("---")

# Interruttore per il calcolo speciale Forfettari
st.sidebar.title("Impostazioni Fiscali")
is_forfettario = st.sidebar.checkbox("🏢 Sono in Regime Forfettario", value=False, help="Seleziona questa spunta se sei un forfettario. Il sistema calcolerà l'IVA al 22% da versare tramite F24 per gli acquisti esteri.")

# Recupera la chiave dai Secrets
try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = None

if not api_key:
    st.error("Configurazione mancante: inserisci la chiave GEMINI_API_KEY nei Secrets di Streamlit.")
else:
    client = genai.Client(api_key=api_key)
    
    file_caricato = st.file_uploader("Carica la fattura (Immagine o Screenshot)", type=["png", "jpg", "jpeg"])
    
    if file_caricato is not None:
        immagine = Image.open(file_caricato)
        st.image(immagine, caption="Fattura caricata", use_container_width=True)
        
        if st.button("🧠 Elabora e Converti"):
            with st.spinner("Collegamento ai server bancari e analisi fiscale in corso..."):
                try:
                    prompt = """
                    Analizza questa fattura estera destinata a una Partita IVA Italiana:
                    1. Estrai fornitore, paese, importo, valuta e data (YYYY-MM-DD).
                    2. Identifica se il paese è in UE o Extra-UE.
                    3. Determina il codice di Autofattura Elettronica (TD17 per servizi, TD18 per beni UE, ecc.).
                    4. Indica se c'è obbligo Intrastat (obbligatorio per acquisti UE).
                    Compila accuratamente lo schema JSON.
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
                    
                    data_doc = risultato["data_documento"]
                    valuta_orig = risultato["valuta_originale"].upper()
                    importo_orig = risultato["imponibile_valuta_originale"]
                    
                    # API Cambio BCE
                    tasso_cambio_bce = 1.0
                    nota_cambio = "Valuta originaria in Euro."
                    if valuta_orig != "EUR":
                        try:
                            url_api = f"https://api.frankfurter.app/{data_doc}?from={valuta_orig}&to=EUR"
                            risposta_bce = requests.get(url_api, timeout=5).json()
                            if "rates" in risposta_bce and "EUR" in risposta_bce["rates"]:
                                tasso_cambio_bce = risposta_bce["rates"]["EUR"]
                                nota_cambio = f"Tasso ufficiale BCE al {data_doc}."
                        except Exception:
                            tasso_cambio_bce = 1.0
                            nota_cambio = "Connessione fallita. Usato tasso 1:1."
                    
                    imponibile_in_euro = importo_orig * tasso_cambio_bce
                    risultato["cambio_ufficiale_bce"] = tasso_cambio_bce
                    risultato["imponibile_calcolato_in_euro"] = round(imponibile_in_euro, 2)
                    
                    # Calcolo F24 per Forfettari
                    iva_da_versare_f24 = 0.0
                    if is_forfettario:
                        iva_da_versare_f24 = imponibile_in_euro * 0.22
                        risultato["iva_22_da_versare_f24"] = round(iva_da_versare_f24, 2)
                    else:
                        risultato["iva_22_da_versare_f24"] = "Non applicabile (Regime Ordinario)"
                    
                    st.success("✨ Analisi fiscale completata!")
                    
                    # Creazione Tabella Visiva
                    voci_tabella = [
                        "Fornitore", "Paese di Origine", "Data Fattura", 
                        "Totale Imponibile (€)", "Codice Autofattura SDI", 
                        "Obbligo Intrastat"
                    ]
                    
                    valori_tabella = [
                        risultato["fornitore"], risultato["paese_provenienza"], data_doc,
                        f"{imponibile_in_euro:.2f} €", risultato["codice_autofattura_sdi"],
                        risultato["obbligo_intrastat"]
                    ]
                    
                    if is_forfettario:
                        voci_tabella.append("🚨 IVA da versare (F24)")
                        valori_tabella.append(f"{iva_da_versare_f24:.2f} €")
                        
                    voci_tabella.append("Nota Tecnica")
                    valori_tabella.append(risultato["nota_per_commercialista"])
                    
                    df_visivo = pd.DataFrame({"Dato Fiscale": voci_tabella, "Valore": valori_tabella})
                    st.table(df_visivo)
                    
                    # Excel Download
                    df_excel = pd.DataFrame([risultato])
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_excel.to_excel(writer, index=False, sheet_name='Registrazione Fiscale')
                    buffer.seek(0)
                    
                    st.write("---")
                    st.download_button(
                        label="📥 Scarica Report Excel Fiscale",
                        data=buffer,
                        file_name=f"fiscale_estero_{risultato['fornitore']}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                except Exception as e:
                    st.error(f"Errore tecnico: {e}")
